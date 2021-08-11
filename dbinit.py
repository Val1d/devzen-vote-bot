from models import db
from models import SubscibedUsers, SuggestedTopics, ArchivedTopics, Votes

db.create_tables([SubscibedUsers, SuggestedTopics,
                  ArchivedTopics, Votes], safe=True)
