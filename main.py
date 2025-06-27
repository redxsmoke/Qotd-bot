import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button
from keep_alive import keep_alive  # Comment out if unused
import logging
from datetime import time
import os

logging.basicConfig(level=logging.INFO)
print("💡 main.py is running")  # Startup log

# Load token and channel IDs from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN environment variable not set!")

CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_CHANNEL_ID = int(os.getenv('DISCORD_ADMIN_CHANNEL_ID', CHANNEL_ID))

QUESTIONS_FILE = 'questions.json'
START_DATE = datetime.date(2025, 6, 25)

# Enable intents including message content intent (CRITICAL for reading DMs)
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def load_questions():
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"❌ Error reading questions file: {e}")
        return []

def save_questions(questions):
    try:
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(questions, f, indent=2)
    except Exception as e:
        logging.error(f"❌ Error saving questions file: {e}")

def load_question_for_today():
    questions = load_questions()
    if not questions:
        return None, None, None

    days_since = (datetime.date.today() - START_DATE).days
    index = min(days_since, len(questions) - 1)
    q = questions[index]
    return q.get("question"), q.get("submitter"), q.get("submitter_name")

class AnswerAnonView(View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout, buttons stay active

    @discord.ui.button(label="Answer Anonymously", style=discord.ButtonStyle.primary, custom_id="answer_anon")
    async def answer_anon_button(self, interaction: discord.Interaction, button: Button):
        # Ephemeral response telling user to DM the bot their anonymous answer
        await interaction.response.send_message(
            "Please send me a direct message (DM) with your anonymous answer. Your response will be forwarded anonymously to the admins.",
            ephemeral=True
        )

@client.event
async def on_ready():
    print("✅ Discord bot connected")
    print(f"Logged in as {client.user}")
    await tree.sync()
    post_daily_message.start()
    purge_channel_before_post.start()

@tasks.loop(time=time(hour=12, minute=0))  # Post once daily at 12:00 PM
async def post_daily_message():
    logging.info("⏰ Attempting to send scheduled daily message")
    question, submitter_id, submitter_name = load_question_for_today()
    if not question:
        logging.error("❌ No question available to post.")
        return

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        logging.error("❌ Channel not found. Check CHANNEL_ID.")
        return

    # Format submitter name
    if submitter_id is None:
        submitter_text = "Question of the Day bot"
    else:
        submitter_text = submitter_name or f"<@{submitter_id}>"

    try:
        view = AnswerAnonView()
        await channel.send(f"@everyone {question}\n\n*Submitted by: {submitter_text}*", view=view)
        logging.info(f"✅ Posted question: {question} (submitted by {submitter_text})")
    except Exception as e:
        logging.error(f"❌ Failed to send message: {e}")

@tasks.loop(time=time(hour=11, minute=59))  # Purge channel daily at 11:59 AM
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

# Your existing commands go here, e.g., /submitquestion, /removequestion, /questionqueue etc.
# [Omitted for brevity since you already have them.]

# Keep the bot alive on hosting platforms that require it
keep_alive()

client.run(TOKEN)
