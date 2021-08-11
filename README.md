# DevZen Podcast Vote Bot

This bot is designed to replace the Disqus vote flow for weekly topic votes.

The bot is capable of:

- accepting user's topics and upvoting them
- notifying subscribed users to vote for topics
- archiving historical topics for past episodes
- deleting violating rules topics

It is not yet possible to:

- downvote topics

# Simple setup

```bash
git clone https://github.com/Val1d/devzen-vote-bot # To fetch sample configuration
cd devzen-vote-bot
# Don't forget to add Admins' Telegram IDs to config_example.yaml. Get them via https://t.me/getmyid_bot
docker run -v $(pwd)/db_data:/app/db_data -v $(pwd)/config_example.yaml:/app/config.yaml -e BOT_API_TOKEN=_YOUR_BOT_API_TOKEN_ -d val1d/devzen-bot
```
