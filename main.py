import discord
import json
import datetime
from discord.ext import tasks, commands
from discord import app_commands
from keep_alive import keep_alive
import logging
from datetime import time
import os

logging.basicConfig(level=logging.INFO)
print("💡 main.py is running")

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN environment variable not set!")

CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_CHANNEL_ID = int(os.getenv('DISCORD_ADMIN_CHANNEL_ID', CHANNEL_ID))

QUESTIONS_FILE = 'questions.json'
START_DATE = datetime.date(2025, 6, 25)

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

@client.event
async def on_ready():
    print("✅ Discord bot connected")
    print(f"Logged in as {client.user}")
    await tree.sync()
    post_daily_message.start()
    purge_channel_before_post.start()

def load_question_for_today():
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        days_since = (datetime.date.today() - START_DATE).days
        index = min(days_since, len(questions) - 1)
        return questions[index]
    except Exception as e:
        logging.error(f"❌ Error reading question file: {e}")
        return None

@tasks.loop(time=time(hour=12, minute=0))
async def post_daily_message():
    logging.info("⏰ Attempting to send scheduled daily message")
    question_obj = load_question_for_today()
    if not question_obj:
        logging.error("❌ No question available to post.")
        return

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        try:
            submitter = question_obj.get("submitter")
            submitter_text = f"Submitted by <@{submitter}>" if submitter else "Submitted by Question of the Day bot"
            await channel.send(f"@everyone {question_obj['question']}\n_{submitter_text}_")
            logging.info(f"✅ Posted question: {question_obj['question']}")
        except Exception as e:
            logging.error(f"❌ Failed to send message: {e}")
    else:
        logging.error("❌ Channel not found. Check CHANNEL_ID.")

@tasks.loop(time=time(hour=11, minute=59))
async def purge_channel_before_post():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        try:
            deleted = await channel.purge(limit=1000)
            logging.info(f"🧹 Purged {len(deleted)} messages from channel {channel.name}")
        except Exception as e:
            logging.error(f"❌ Failed to purge messages: {e}")
    else:
        logging.error("❌ Channel not found. Check CHANNEL_ID.")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.guild is None:
        admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            try:
                await admin_channel.send(f"📩 Anonymous answer received:\n{message.content}")
                await message.channel.send("Thanks! Your answer was received anonymously.")
                logging.info(f"📩 Relayed DM from {message.author}")
            except Exception as e:
                logging.error(f"❌ Failed to send anonymous answer: {e}")
                await message.channel.send("Sorry, couldn't deliver your answer right now.")
        else:
            logging.error("❌ Admin channel not found.")
            await message.channel.send("Sorry, couldn't deliver your answer right now.")

keep_alive()
client.run(TOKEN)
