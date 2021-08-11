from peewee import Model
from peewee import SqliteDatabase
from peewee import CharField, IntegerField, ForeignKeyField, CompositeKey

db = SqliteDatabase("db_data/devzen.db")


class BaseModel(Model):
    class Meta(type):
        database = db


class SubscibedUsers(BaseModel):
    user = IntegerField(unique=True)


class SuggestedTopics(BaseModel):
    # hash(title+body). We should be able to uniquely identyfy topic for voting
    # We don't really care about collisions, we'll use non-cryptographic hash
    uid = IntegerField(primary_key=True)
    user = IntegerField()
    title = CharField()
    body = CharField()
    username = CharField()


class ArchivedTopics(BaseModel):
    user = IntegerField()
    title = CharField()
    body = CharField()
    username = CharField()
    votes = IntegerField()
    episode = IntegerField()


class Votes(Model):
    user = IntegerField()
    topic = ForeignKeyField(SuggestedTopics)

    class Meta:
        database = db
        primary_key = CompositeKey('user', 'topic')
