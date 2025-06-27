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
        await channel.send(f"@everyone {question}\n\n*Submitted by: {submitter_text}*")
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


@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n/submitquestion\n/removequestion\n/questionqueue",
        ephemeral=True,
    )


@tree.command(name="submitquestion", description="Submit a question or a multiple-choice question")
@app_commands.describe(
    type="Type of question: question or multiple_choice",
    question="The question you want to ask",
    choice1="First choice (required for multiple choice questions)",
    choice2="Second choice (required for multiple choice questions)",
    choice3="Optional third choice",
    choice4="Optional fourth choice",
)
@app_commands.choices(
    type=[
        app_commands.Choice(name="question", value="question"),
        app_commands.Choice(name="question with answer (mult-choice)", value="multiple_choice"),
    ]
)
async def submit_question(
    interaction: discord.Interaction,
    type: app_commands.Choice[str],
    question: str,
    choice1: str = None,
    choice2: str = None,
    choice3: str = None,
    choice4: str = None,
):
    questions = load_questions()

    new_id = max([q["id"] for q in questions], default=0) + 1
    new_question = {
        "id": new_id,
        "question": question,
        "submitter": interaction.user.id,
        "submitter_name": str(interaction.user),
    }

    if type.value == "multiple_choice":
        if not (choice1 and choice2):
            await interaction.response.send_message(
                "You must provide at least two choices for a multiple-choice question.",
                ephemeral=True,
            )
            return
        answers = [choice for choice in [choice1, choice2, choice3, choice4] if choice]
        new_question["answers"] = answers

    questions.append(new_question)
    save_questions(questions)

    await interaction.response.send_message(f"✅ Question submitted with ID {new_id}!", ephemeral=True)


@tree.command(name="removequestion", description="Remove a question by ID (admin/mod only)")
@app_commands.describe(id="ID of the question to remove")
async def remove_question(interaction: discord.Interaction, id: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.", ephemeral=True
        )
        return

    questions = load_questions()

    original_len = len(questions)
    questions = [q for q in questions if q["id"] != id]

    if len(questions) == original_len:
        await interaction.response.send_message(f"❌ No question found with ID {id}.", ephemeral=True)
        return

    save_questions(questions)
    await interaction.response.send_message(f"✅ Question with ID {id} has been removed.", ephemeral=True)


@tree.command(name="questionqueue", description="Admin-only view of question queue with IDs")
async def question_queue(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.", ephemeral=True
        )
        return

    questions = load_questions()

    if not questions:
        await interaction.response.send_message("No questions in queue.", ephemeral=True)
        return

    lines = [
        f"`{q['id']}`: {q['question'][:80]}{'...' if len(q['question']) > 80 else ''}"
        for q in questions
    ]
    message = "📋 Question Queue:\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)


# Keep the bot alive on hosting platforms that require it
keep_alive()

client.run(TOKEN)
