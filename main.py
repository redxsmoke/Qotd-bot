import discord
import requests
import csv
import io
import datetime
from discord.ext import tasks
from keep_alive import keep_alive
import logging
from datetime import time
import os

logging.basicConfig(level=logging.INFO)

print("💡 main.py is running")  # Startup log

# ✅ Token loading with fallback warning
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN not found in environment variables!")

# ✅ Constants
CHANNEL_ID = 1387520693859782867
CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTzKsZYB9345dqSaz-y0r2P3ui0SqmibWLMPQgE5l5AV3fK0m0XconU5JBCEjtSEYa-hP7hrHikaZBC/pub?output=csv'
START_DATE = datetime.date(2025, 6, 25)

# ✅ Enable message content intent (CRITICAL)
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print("✅ Discord bot connected")
    print(f'Logged in as {client.user}')
    post_daily_message.start()

# Optional: Debug messages
# @client.event
# async def on_message(message):
#     print(f"👀 Message received: {message.content}")

@tasks.loop(time=time(hour=12, minute=0))
async def post_daily_message():
    logging.info("Attempting to send daily message")
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
                    logging.info(f"✅ Sent message: {message}")
                else:
                    logging.error("❌ Channel not found. Check CHANNEL_ID.")
            else:
                logging.warning("⚠️ No messages found in Google Sheet.")
        else:
            logging.error(f"❌ Failed to fetch Google Sheet: {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Error sending daily message: {e}")

# ✅ Keep-alive & run
keep_alive()
client.run(TOKEN)
