import discord
import requests
import csv
import io
import datetime
from discord.ext import tasks
from keep_alive import keep_alive  # Comment out if unused
import logging
from datetime import time
import os

logging.basicConfig(level=logging.INFO)
print("💡 main.py is running")  # Startup log

# Load token from environment variable for security
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN environment variable not set!")

# Constants
CHANNEL_ID = 1387520693859782867      # Channel to post questions and purge messages
ADMIN_CHANNEL_ID = 1387520693859782867  # Admin channel to collect anonymous answers

CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTzKsZYB9345dqSaz-y0r2P3ui0SqmibWLMPQgE5l5AV3fK0m0XconU5JBCEjtSEYa-hP7hrHikaZBC/pub?output=csv'

START_DATE = datetime.date(2025, 6, 25)

# Enable intents including message content intent (CRITICAL for reading DMs)
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print("✅ Discord bot connected")
    print(f"Logged in as {client.user}")
    post_daily_message.start()
    purge_channel_before_post.start()

@tasks.loop(time=time(hour=12, minute=0))  # Post once daily at 12:00 PM
async def post_daily_message():
    logging.info("⏰ Attempting to send scheduled daily message")
    try:
        response = requests.get(CSV_URL)
        if response.status_code == 200:
            content = response.content.decode('utf-8')
            reader = csv.reader(io.StringIO(content))
            next(reader)  # Skip header
            messages = [row[0] for row in reader if row]
            if messages:
                days_since = (datetime.date.today() - START_DATE).days
                index = min(days_since, len(messages) - 1)
                message = messages[index]
                channel = client.get_channel(CHANNEL_ID)
                if channel:
                    await channel.send(message)
                    logging.info(f"✅ Sent daily message: {message}")
                else:
                    logging.error("❌ Channel not found. Check CHANNEL_ID.")
            else:
                logging.warning("⚠️ No messages found in Google Sheet.")
        else:
            logging.error(f"❌ Failed to fetch Google Sheet: {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Error sending daily message: {e}")

@tasks.loop(seconds=30)  # Purge channel every 30 seconds (testing)
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

    # Relay anonymous DM answers to admin channel
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

# Keep the bot alive on hosting platforms that require it
keep_alive()

client.run(TOKEN)
