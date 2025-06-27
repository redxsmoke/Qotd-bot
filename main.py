import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
from keep_alive import keep_alive
import logging
from datetime import time
import os
from operator import itemgetter

logging.basicConfig(level=logging.INFO)
print("\U0001F4A1 main.py is running")

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("\u274C DISCORD_BOT_TOKEN not set!")
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_CHANNEL_ID = int(os.getenv('DISCORD_ADMIN_CHANNEL_ID', CHANNEL_ID))

QUESTIONS_FILE = 'questions.json'
SCORES_FILE = 'user_scores.json'
CONTRIB_DATES_FILE = 'contrib_dates.json'  # new file for tracking contributor points per day
START_DATE = datetime.date(2025, 6, 25)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def load_questions():
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_questions(questions):
    with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2)

def load_scores():
    try:
        with open(SCORES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_scores(scores):
    with open(SCORES_FILE, 'w', encoding='utf-8') as f:
        json.dump(scores, f, indent=2)

def load_contributor_dates():
    try:
        with open(CONTRIB_DATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # convert string dates back to date objects
            return {k: datetime.date.fromisoformat(v) for k,v in data.items()}
    except:
        return {}

def save_contributor_dates():
    # Convert dates to ISO string for json serialization
    data = {k: v.isoformat() for k,v in contributor_dates.items()}
    with open(CONTRIB_DATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def generate_unique_id():
    if (questions := load_questions()):
        try:
            last_id = max(int(q["id"]) for q in questions if q.get("id") and str(q["id"]).isdigit())
        except Exception:
            last_id = 0
    else:
        last_id = 0
    return str(last_id + 1)

# Load contributor dates on startup
contributor_dates = load_contributor_dates()

class SubmitQuestionModal(Modal, title="Submit a Question"):
    question_input = TextInput(label="Your question", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        question_text = self.question_input.value.strip()
        questions = load_questions()
        new_id = generate_unique_id()
        questions.append({"id": new_id, "question": question_text, "submitter": str(self.user.id)})
        save_questions(questions)

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("\u274C This command must be used in a server.", ephemeral=True)
            return

        admins_mods = [member for member in guild.members if member.guild_permissions.administrator or member.guild_permissions.manage_messages]
        dm_message = f"🧠 <@{self.user.id}> has submitted a new Question of the Day. Use /questionlist to view it and /removequestion if moderation is needed."

        for admin in admins_mods:
            try:
                await admin.send(dm_message)
            except Exception:
                pass

        scores = load_scores()
        uid_str = str(self.user.id)
        today = datetime.date.today()
        last_contrib_date = contributor_dates.get(uid_str)

        if last_contrib_date != today:
            scores.setdefault(uid_str, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
            scores[uid_str]["contribution_points"] += 1
            contributor_dates[uid_str] = today
            save_scores(scores)
            save_contributor_dates()
            contrib_msg = "\n🏅 You have been awarded **1 contributor point** for your submission!"
        else:
            contrib_msg = "\n⚠️ You can only earn **1 contributor point per day** for submitting questions."

        await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{new_id}`{contrib_msg}", ephemeral=True)

# ... rest of your existing code unchanged below ...

# (Make sure you replace your existing SubmitQuestionModal.on_submit with this updated code)

# Then at bottom

keep_alive()
client.run(TOKEN)
