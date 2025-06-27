import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from keep_alive import keep_alive  # Comment out if unused
import logging
from datetime import time
import os

logging.basicConfig(level=logging.INFO)
print("\U0001F4A1 main.py is running")  # Startup log

# Load token and channel IDs from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("\u274C DISCORD_BOT_TOKEN environment variable not set!")

CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_CHANNEL_ID = int(os.getenv('DISCORD_ADMIN_CHANNEL_ID', CHANNEL_ID))

QUESTIONS_FILE = 'questions.json'
START_DATE = datetime.date(2025, 6, 25)

# Enable intents including message content intent (CRITICAL for reading DMs)
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Utility functions to manage questions

def load_questions():
    if not os.path.exists(QUESTIONS_FILE):
        return []
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_questions(questions):
    with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

def get_next_question_id(questions):
    if not questions:
        return 1
    return max(q["id"] for q in questions) + 1

@client.event
async def on_ready():
    print("\u2705 Discord bot connected")
    print(f"Logged in as {client.user}")
    await tree.sync()
    print("\u2705 Synced slash commands")
    post_daily_message.start()
    purge_channel_before_post.start()

def load_question_for_today():
    try:
        questions = load_questions()
        days_since = (datetime.date.today() - START_DATE).days
        index = min(days_since, len(questions) - 1)
        return questions[index]["question"]
    except Exception as e:
        logging.error(f"❌ Error reading question file: {e}")
        return None

@tasks.loop(time=time(hour=12, minute=0))  # Post once daily at 12:00 PM
async def post_daily_message():
    logging.info("⏰ Attempting to send scheduled daily message")
    question = load_question_for_today()
    if not question:
        logging.error("❌ No question available to post.")
        return

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        try:
            await channel.send(f"@everyone {question}")
            logging.info(f"✅ Posted question: {question}")
        except Exception as e:
            logging.error(f"❌ Failed to send message: {e}")
    else:
        logging.error("❌ Channel not found. Check CHANNEL_ID.")

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

# Slash commands
@tree.command(name="questionofthedaycommands", description="List all available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Available Commands:**\n"
        "• `/questionofthedaycommands` – List all available commands\n"
        "• `/submitquestion` – Submit a new question\n"
        "• `/removequestion` – Remove a question by ID (admin only)",
        ephemeral=True
    )

@tree.command(name="submitquestion", description="Submit a question for the Question of the Day")
@app_commands.describe(
    question_type="Choose 'question' or 'question with answer (multi-choice)'",
    question="Enter your question",
    choice1="Required (for multi-choice)",
    choice2="Required (for multi-choice)",
    choice3="Optional",
    choice4="Optional"
)
@app_commands.choices(question_type=[
    app_commands.Choice(name="Question only", value="plain"),
    app_commands.Choice(name="Question with answer (multi-choice)", value="mc")
])
async def submitquestion(
    interaction: discord.Interaction,
    question_type: app_commands.Choice[str],
    question: str,
    choice1: str = None,
    choice2: str = None,
    choice3: str = None,
    choice4: str = None
):
    questions = load_questions()
    question_id = get_next_question_id(questions)

    if question_type.value == "plain":
        new_entry = {"id": question_id, "question": question, "answer": None}
        questions.append(new_entry)
        save_questions(questions)
        await interaction.response.send_message(f"✅ Question submitted (ID: {question_id})", ephemeral=True)
    else:
        choices = [choice1, choice2]
        if choice3:
            choices.append(choice3)
        if choice4:
            choices.append(choice4)

        if not all(choices[:2]):
            await interaction.response.send_message("❌ At least two choices are required.", ephemeral=True)
            return

        new_entry = {"id": question_id, "question": question, "answer": choices}
        questions.append(new_entry)
        save_questions(questions)
        formatted_choices = "\n".join([f"{i+1}. {c}" for i, c in enumerate(choices)])
        await interaction.response.send_message(
            f"✅ Question with choices submitted (ID: {question_id})\n**Choices:**\n{formatted_choices}",
            ephemeral=True
        )

@tree.command(name="removequestion", description="Remove a question by ID (admin only)")
@app_commands.describe(question_id="The ID of the question to remove")
async def removequestion(interaction: discord.Interaction, question_id: int):
    if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    questions = load_questions()
    updated = [q for q in questions if q["id"] != question_id]
    if len(updated) == len(questions):
        await interaction.response.send_message(f"❌ No question found with ID {question_id}.", ephemeral=True)
    else:
        save_questions(updated)
        await interaction.response.send_message(f"✅ Question with ID {question_id} has been removed.", ephemeral=True)

# Keep the bot alive on hosting platforms that require it
keep_alive()
client.run(TOKEN)
