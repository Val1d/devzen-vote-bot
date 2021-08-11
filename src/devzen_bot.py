#!/usr/bin/env python
# -*- coding: utf-8 -*-

import telegram
from time import sleep
from models import SubscibedUsers, SuggestedTopics, Votes, ArchivedTopics, db
from peewee import IntegrityError
from helpers import (_send_message, _parse_config, _format_topic,
                     isAdmin, logger, config, _get_sorted_topics_with_votes)
from telegram import (InlineKeyboardButton,
                      InlineKeyboardMarkup, ReplyKeyboardRemove)
from telegram.ext import (RegexHandler, Updater, CommandHandler, CallbackQueryHandler,
                          MessageHandler, Filters, ConversationHandler)

HELP_MESSAGE = '''Я поддерживаю следующие команды:

/propose – предложить тему для выпуска. Тема станет доступна всем для голосования.
/vote – проголосовать за тему. Вам будет предоставлен список тем, предложенных другими пользователями.
/list – посмотреть текущий список тем.
/list episode_number – посмотреть список тем к выпуску под номером episode_number.
/unsubscribe – отписаться от напоминаний проголосовать за выпуск.'''

ADMIN_HELP_MESSAGE = '''\n\nКоманды администраторов:

/archive – архивировать список тем прошедшего выпуска. Все темы переместятся в архив, за них больше нельзя будет голосовать, а список текущих тем обнулится.
/delete – удалить тему, предложенную пользователем. Например, если она нарушает правила.'''

state = {}
TITLE, BODY, CONFIRMATION = range(3)
VOTE = range(3, 4)
DELETE = range(4, 5)
EPISODE_NUMBER, ARCHIVE = range(5, 7)


@isAdmin
def start_archive(update, context):
    update.message.reply_text(
        'Вы собираетесь зафиксировать список тем для прошедшего выпуска.\n' +
        'Пожалуйста, ознакомьтесь со списком тем. Вы не сможете изменить ' +
        'его после архивации.')
    list_topics(update, context)
    update.message.reply_text(
        'К какому эпизоду предназначены эти темы? Пожалуйста, введите номер:')

    return EPISODE_NUMBER


@isAdmin
def set_episode_number(update, context):
    # Due to regex handler we expect no exceptions
    episode = int(update.message.text)

    # If we already have topics associated with this episode
    if ArchivedTopics.select().where(ArchivedTopics.episode == episode).count() > 0:
        update.message.reply_text(
            'Похоже, что к этому эпизоду уже были добавлены темы.\n' +
            'Вы точно уверены в том, что делаете?')

    update.message.reply_text(
        f'Вы точно хотите заархивировать темы для эпизода №{episode}?',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='Да', callback_data=f'{episode}_0'),
                 InlineKeyboardButton(text='Нет', callback_data=f'{episode}_1')]],
            one_time_keyboard=True))
    return ARCHIVE


@isAdmin
def confirm_archive(update, context):
    query = update.callback_query
    query.answer()
    (episode, choice) = query.data.split('_')
    # We should archive all the topics and delete them from list
    if choice == '0':
        try:
            with db.atomic():
                topics = _get_sorted_topics_with_votes()
                for topic in topics:
                    ArchivedTopics.create(
                        user=topic.user,
                        username=topic.username,
                        title=topic.title,
                        body=topic.body,
                        votes=topic.votes,
                        episode=episode)
                Votes.delete().execute()
                SuggestedTopics.delete().execute()

            query.edit_message_text('Темы архивированы')
        except IntegrityError:
            query.edit_message_text(
                'Тема с таким заголовком и текстом уже существует.')

    else:
        query.edit_message_text('Попробуйте снова.')

    return ConversationHandler.END


@isAdmin
def start_delete(update, context):
    # if there are no topics yet.
    if SuggestedTopics.select().count() == 0:
        update.message.reply_text('В настоящее время тем нет')
        return ConversationHandler.END

    keyboard = []
    for topic in SuggestedTopics.select():
        title = topic.title
        keyboard.append([InlineKeyboardButton(
            text=title, callback_data=str(topic.uid))])

    update.message.reply_text(
        'Вы можете удалить тему нажатием на кнопку с соответствующим названием\n' +
        'Осторожно, тема будет удалена навсегда! Вы можете внести пользователя в ' +
        'черный список в config.yaml.',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard +
            [[InlineKeyboardButton(text='Закончить', callback_data='STOP')]]))
    return DELETE


@isAdmin
def delete_topic(update, context):
    query = update.callback_query
    query.answer()
    topic = None

    try:
        topic = SuggestedTopics.get(uid=query.data)
    except:
        # Might happen when topic was already deleted (by another admin?)
        query.edit_message_text(
            'Вероятно, тема уже удалена, попробуйте снова.')
        return ConversationHandler.END

    with db.atomic():
        Votes.delete().where(Votes.topic == topic).execute()
        topic.delete_instance()

    query.edit_message_text('Тема удалена.')
    return ConversationHandler.END


def list_topics(update, context):
    # if the argument us present, user wants to get the list of topics assosiated
    # with the exact episode
    if len(context.args) == 1:
        topics = ArchivedTopics.select().where(
            ArchivedTopics.episode == context.args[0]).order_by(
            ArchivedTopics.votes.desc())
    else:
        topics = _get_sorted_topics_with_votes()

    if len(topics) == 0:
        update.message.reply_text(
            'К сожалению, пока никто не предложил тем, ' +
            'либо введен неверный номер выпуска.')

    for topic in topics:
        _send_message(update, _format_topic(
            topic.title, topic.username, topic.body, votes=topic.votes))


def start_vote(update, context):
    # if there are no topics yet.
    if SuggestedTopics.select().count() == 0:
        update.message.reply_text('К сожалению, пока никто не предложил тем.')
        return ConversationHandler.END

    update.message.reply_text(
        'Спасибо за то, что голосуете за темы!\nСедует помнить, ' +
        'что список тем может обновляться до выпуска. Текущий список тем:\n')

    keyboard = []

    for topic in SuggestedTopics.select():
        _send_message(update, _format_topic(
            topic.title, topic.username, topic.body))
        title = topic.title

        # Mark themes that already have votes from the current user
        if Votes.select().where(
                (Votes.user == update.message.from_user.id) &
                (Votes.topic == topic)).count() > 0:
            title = '✅ ' + title

        keyboard.append([InlineKeyboardButton(
            text=title, callback_data=str(topic.uid))])

    update.message.reply_text(
        'Вы можете проголосовать за тему нажатием на кнопку с соответствующим названием. ' +
        'Темы, за которые вы уже проголосовали, отмечены знаком ✅\n' +
        'Вы можете отозвать свой голос нажав на уже проголосованную тему.',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard +
            [[InlineKeyboardButton(text='Закончить', callback_data='STOP')]]))
    return VOTE


def vote(update, context):
    query = update.callback_query
    query.answer()
    topic = None

    try:
        topic = SuggestedTopics.get(uid=query.data)
    except:
        # Might happen when user requested /vote before /archive but voted after
        query.edit_message_text(
            'Данное голосование уже закончено или тема удалена, попробуйте снова.')
        return ConversationHandler.END

    # We should update the pressed button text. Let's find the corresponding button
    t = next(filter(lambda x: x[0]['callback_data'] == query.data,
                    query.message.reply_markup.inline_keyboard))[0]
    with db.atomic():
        # if user has already voted for this topic
        if Votes.select().where(
                (Votes.user == query.from_user.id) &
                (Votes.topic == topic)).count() > 0:
            Votes.delete().where((Votes.user == query.from_user.id) &
                                 (Votes.topic == topic)).execute()
            # There might be a little race here, but it's ok, isn't it? (:
            # It doesn't affect any business logic after all
            t.text = t.text[2:]
        else:
            Votes.create(user=query.from_user.id, topic=topic)
            t.text = '✅ ' + t.text

    query.edit_message_text(
        'Вы можете проголосовать за тему нажатием на кнопку с соответствующим названием. ' +
        'Темы, за которые вы уже проголосовали, отмечены знаком ✅\n' +
        'Вы можете отозвать свой голос нажав на уже проголосованную тему.',
        reply_markup=query.message.reply_markup)
    return VOTE


def stop_vote(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text('Спасибо!')
    return ConversationHandler.END


def start_propose(update, context):
    # Check if user was not banned
    if update.message.from_user.id in config['bannedUsers']:
        update.message.reply_text('Прошу прощения, вы заблокированы, обратитесь к администратору.')
        return ConversationHandler.END

    update.message.reply_text(
        'Спасибо за то, что предлагаете нам темы! ' +
        'Пожалуйста, введите короткий заголовок темы (максимум 140 символов)\n' +
        'Если вы нажали на кнопку случайно –– не волнуйтесь, это можно будет отменить на последнем шаге.')
    state[update.message.from_user.id] = {}
    return TITLE


def add_title(update, context):
    title = update.message.text

    if len(title) > 140:
        update.message.reply_text(
            'Заголовок темы слишком длинный. Пожалуйста, придумайте короткое предложение, ' +
            'характеризующее тему, чтобы слушателям было удобнее голосовать.\nПопробуйте снова.')
        return TITLE
    else:
        state[update.message.from_user.id]['title'] = title
        update.message.reply_text(
            'Спасибо! Теперь введите тело новости. Пожалуйста, избегайте излишне длинного текста.')
        return BODY


def add_body(update, context):
    state[update.message.from_user.id]['username'] = update.message.from_user.username \
        if update.message.from_user.username != '' else \
        update.message.from_user.first_name + " " + update.message.from_user.last_name

    state[update.message.from_user.id]['body'] = update.message.text

    text = _format_topic(state[update.message.from_user.id]['title'],
                         state[update.message.from_user.id]['username'],
                         state[update.message.from_user.id]['body'])

    _send_message(update, text)
    update.message.reply_text(
        'Спасибо! Тема выглядит так, как вы ожидали?',
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=value, callback_data=str(i))
                 for i, value in enumerate(['Да', 'Нет'])]],
            one_time_keyboard=True))
    return CONFIRMATION


def confirm_topic(update, context):
    query = update.callback_query
    query.answer()
    if query.data == '0':
        try:
            with db.atomic():
                SuggestedTopics.create(
                    uid=hash(state[query.from_user.id]['title'] +
                             state[query.from_user.id]['body']),
                    user=query.from_user.id,
                    username=state[query.from_user.id]['username'],
                    title=state[query.from_user.id]['title'],
                    body=state[query.from_user.id]['body'])
            query.edit_message_text('Ваша тема принята, спасибо.')
        except IntegrityError:
            query.edit_message_text(
                'Тема с таким заголовком и текстом уже существует.')

        del state[query.from_user.id]
    else:
        state[query.from_user.id] = {}
        query.edit_message_text('Попробуйте снова.')

    return ConversationHandler.END


def cancel(update, context):
    if update.message.from_user.id in state:
        del state[update.message.from_user.id]

    update.message.reply_text('Ввод отменен',
                              reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def unsubscribe(update, context):
    with db.atomic():
        SubscibedUsers.delete().where(SubscibedUsers.user ==
                                      update.message.from_user.id).execute()
    update.message.reply_text('Вы успешно отписаны от уведомлений. Однако, ' +
                              'вы все еще можете голосовать за темы слушателей.\n' +
                              'Для информации используйте /help')


def notify_subscribed_users(context):
    for user in SubscibedUsers.select():
        _send_message(context.bot,
                      'Время проголосовать за новости. Используйте /vote для голосования\n' +
                      'Если вы хотите отписаться от напоминаний, используйте /unsubscribe',
                      user.user)
        # The current rate limit is 30 messages per second (see https://core.telegram.org/bots/faq)
        # We will wate for 50 milliseconds (which makes approx 20 messages per second)
        sleep(0.05)


def start(update, context):
    update.message.reply_text(
        'Здравствуй! Я DevZen-бот для голосования за темы слушателей.\n' +
        'Я подписал вас на рассылку о голосовании. Раз в неделю я буду напоминать вам ' +
        'проголосовать за предложенные темы. Если вы хотите отписаться от рассылки и ' +
        'голосовать самостоятельно без напоминаний, используйте команду /unsubscribe\n' +
        'Для вызова инструкции по использованию, используйте команду /help')
    help(update, context)
    userId = update.message.from_user.id

    # Let's check if the user is not already subscribed
    if SubscibedUsers.select().where(SubscibedUsers.user == userId).count() > 0:
        return
    else:
        with db.atomic():
            SubscibedUsers.create(user=userId)


def help(update, context):
    # Send a message when the command /help is issued.
    text = HELP_MESSAGE
    if update.message.from_user.id in config['adminIds']:
        text += ADMIN_HELP_MESSAGE

    _send_message(update, text)


def error(update, context):
    # Log Errors caused by Updates.
    logger.warning('Update "%s" caused error "%s"', update, context.error)


# Start the bot.
def main():
    global config
    config = _parse_config()
    if config is None:
        logger.critical('Configuration error. Shutting down')
        return

    updater = Updater(config['botApiToken'])
    # Get the dispatcher to register handlers
    dp = updater.dispatcher
    suggest_handler = ConversationHandler(
        entry_points=[CommandHandler('propose', start_propose)],
        states={
            TITLE: [MessageHandler(Filters.all, add_title)],
            BODY: [MessageHandler(Filters.all, add_body)],
            CONFIRMATION: [CallbackQueryHandler(confirm_topic)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(suggest_handler)

    vote_handler = ConversationHandler(
        entry_points=[CommandHandler('vote', start_vote)],
        states={
            VOTE: [
                CallbackQueryHandler(stop_vote, pattern='^STOP$'),
                CallbackQueryHandler(vote, pattern='^[-]{0,1}\d+$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(vote_handler)

    delete_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', start_delete)],
        states={
            DELETE: [
                CallbackQueryHandler(stop_vote, pattern='^STOP$'),
                CallbackQueryHandler(delete_topic, pattern='^[-]{0,1}\d+$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(delete_handler)

    archive_handler = ConversationHandler(
        entry_points=[CommandHandler('archive', start_archive)],
        states={
            # Don't forget to add one digit to regex in 13 years (:
            EPISODE_NUMBER: [MessageHandler(Filters.regex(r'^\d{1,3}$'), set_episode_number)],
            ARCHIVE: [CallbackQueryHandler(confirm_archive)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(archive_handler)

    dp.add_handler(CommandHandler('start', start))

    dp.add_handler(CommandHandler('unsubscribe', unsubscribe))

    dp.add_handler(CommandHandler('list', list_topics))

    job = updater.job_queue.run_daily(notify_subscribed_users,
                                      time=config['votes']['notifyToVoteOnTime'],
                                      days=[config['votes']['notifyToVoteOnDay']])

    dp.add_handler(CommandHandler("help", help))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
