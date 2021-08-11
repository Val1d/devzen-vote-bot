import os
import logging
import yaml
import telegram
import datetime
import html
from functools import wraps
from time import sleep
from models import SuggestedTopics, Votes
from peewee import fn, JOIN

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 3000
config = {}


def isAdmin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if isinstance(args[0], telegram.Update):
            update = args[0]
            if update.message is None:
                sender = update.callback_query.from_user.id
            else:
                sender = update.message.from_user.id
            if sender not in config['adminIds']:
                update.message.reply_text(
                    f'Пользователю с ID {update.message.from_user.id} ' +
                    'не позволено использовать функции администратора')
                return
        return fn(*args, **kwargs)
    return wrapper


def _parse_config():
    global config
    try:
        with open('config.yaml', 'r') as c:
            config = yaml.safe_load(c)
    except FileNotFoundError:
        config = {}
    except Exception as e:
        logger.exception(e)
        return None

    # Override config values with environment ones
    if 'BOT_API_TOKEN' in os.environ:
        config['botApiToken'] = os.getenv('BOT_API_TOKEN')

    if 'adminIds' in config:
        # Just in case there're thousands of them
        config['adminIds'] = set(config['adminIds'])
    else:
        logger.error(
            'No admin users provided. My purpose now is only to pass butter. My life is pointless.')
        return None

    if 'bannedUsers' in config:
        config['bannedUsers'] = set(config['bannedUsers'])
    else:
        config['bannedUsers'] = set()

    if 'votes' in config:
        config['votes']['notifyToVoteOnTime'] = datetime.time.fromisoformat(
            config['votes']['notifyToVoteOnTime'])
    else:
        config['votes'] = {'notifyToVoteOnDay': 5,
                           'notifyToVoteOnTime': datetime.time.fromisoformat("10:00")}

    if config == {}:
        return None
    else:
        return config


# A helper function for sending potentially long messages
def _send_message(update, text, chat_id=None, isCode=False):
    if len(text) <= MAX_MESSAGE_LENGTH:
        if isCode:
            text = '```' + text + '```'
        if chat_id is not None:
            update.send_message(
                chat_id, text, parse_mode=telegram.ParseMode.HTML)
        else:
            update.message.reply_text(text, parse_mode=telegram.ParseMode.HTML)
        return
    parts = []
    while len(text) > 0:
        if len(text) > MAX_MESSAGE_LENGTH:
            part = text[:MAX_MESSAGE_LENGTH]
            first_lnbr = part.rfind('\n')
            if first_lnbr != -1:
                parts.append(part[:first_lnbr])
                text = text[first_lnbr:]
            else:
                parts.append(part)
                text = text[MAX_MESSAGE_LENGTH:]
        else:
            parts.append(text)
            break
    for part in parts:
        if isCode:
            part = '```' + part + '```'
        if chat_id:
            update.send_message(
                chat_id, part, parse_mode=telegram.ParseMode.HTML)
        else:
            update.message.reply_text(part, parse_mode=telegram.ParseMode.HTML)
        sleep(1)  # There are some limitations on messages per second


def _format_topic(title, username, body, votes=None):
    if votes is None:
        topic = f'*️⃣ <b>' + \
            f'{html.escape(title)}</b> (Предложена <i>{html.escape(username)}</i>)\n'
    else:
        topic = f'#️⃣ <i>Голосов:</i> {votes}\n*️⃣ <b>' + \
            f'{html.escape(title)}</b> (Предложена <i>{html.escape(username)}</i>)\n'
    topic += html.escape(body)

    return topic


def _get_sorted_topics_with_votes():
    # Since sqlite does not support full outer join,
    # we should use dirty UNION hack. Or maybe I just don't get SQL (:
    query = Votes.select(SuggestedTopics.username.alias('username'),
                         SuggestedTopics.user.alias('user'),
                         SuggestedTopics.title.alias('title'),
                         SuggestedTopics.body.alias('body'),
                         fn.COUNT(SuggestedTopics.title).alias(
                             'votes')
                         ).join(SuggestedTopics).group_by(SuggestedTopics.title) | \
        SuggestedTopics.select(SuggestedTopics.username,
                               SuggestedTopics.user,
                               SuggestedTopics.title,
                               SuggestedTopics.body,
                               0).join(Votes, JOIN.LEFT_OUTER).where(Votes.topic.is_null())
    # Let's sort topics by votes
    topics = sorted(list(query.namedtuples()),
                    key=lambda x: x.votes, reverse=True)
    return topics
