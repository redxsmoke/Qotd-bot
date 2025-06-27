import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
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

def get_today_question():
    questions = load_questions()
    days_since = (datetime.date.today() - START_DATE).days
    if days_since < len(questions):
        return questions[days_since]
    return None

def get_rank(total):
    if total <= 10:
        return "\U0001F363 Rice Rookie"
    elif total <= 25:
        return "\U0001F364 Miso Mind"
    elif total <= 40:
        return "\U0001F363 Sashimi Scholar"
    elif total <= 75:
        return "\U0001F95A Wasabi Wizard"
    else:
        return "\U0001F371 Sushi Sensei"

def generate_unique_id():
    import uuid
    return str(uuid.uuid4())[:8]

async def post_question():
    q = get_today_question()
    if not q: return
    question = q["question"]
    submitter = q.get("submitter")
    submitter_text = f"\U0001F9E0 Question submitted by <@{submitter}>" if submitter else "\U0001F916 Question submitted by the Question of the Day Bot"

    class QuestionView(View):
        def __init__(self, qid):
            super().__init__(timeout=None)
            self.qid = qid

        @discord.ui.button(label="Answer Freely ⭐ 1 Insight Point", style=discord.ButtonStyle.primary, custom_id="freely")
        async def free_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnswerModal(qid=self.qid, user=interaction.user))

        @discord.ui.button(label="Answer Anonymously 🔋 0 Insight Points", style=discord.ButtonStyle.secondary, custom_id="anon")
        async def anon_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnonModal(qid=self.qid, user=interaction.user))

    class AnswerModal(discord.ui.Modal, title="Answer the Question"):
        answer = discord.ui.TextInput(label="Your answer", style=discord.TextStyle.paragraph)

        def __init__(self, qid, user):
            super().__init__()
            self.qid = qid
            self.user = user

        async def on_submit(self, interaction: discord.Interaction):
            scores = load_scores()
            uid = str(self.user.id)
            scores.setdefault(uid, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
            if self.qid not in scores[uid]["answered_questions"]:
                scores[uid]["insight_points"] += 1
                scores[uid]["answered_questions"].append(self.qid)
                save_scores(scores)
                total = scores[uid]["insight_points"] + scores[uid]["contribution_points"]
                msg = f"\U0001F5E3️ Answer from <@{uid}>:\n{self.answer}\n\n⭐ Insight Points: {scores[uid]['insight_points']} | 💡 Contribution: {scores[uid]['contribution_points']} | 🏆 Rank: {get_rank(total)}"
            else:
                msg = f"\U0001F5E3️ Answer from <@{uid}>:\n{self.answer}\n\n(You've already earned a point for this one!)"
            await interaction.response.send_message(msg)

    class AnonModal(discord.ui.Modal, title="Answer Anonymously"):
        answer = discord.ui.TextInput(label="Your anonymous answer", style=discord.TextStyle.paragraph)

        def __init__(self, qid, user):
            super().__init__()
            self.qid = qid
            self.user = user

        async def on_submit(self, interaction: discord.Interaction):
            admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
            await admin_channel.send(f"\U0001F4E9 Anonymous answer for Question ID {self.qid}:\n{self.answer}")
            await interaction.response.send_message("\u2705 Received anonymously.", ephemeral=True)

    channel = client.get_channel(CHANNEL_ID)
    await channel.send(f"@everyone {question}\n\n{submitter_text}", view=QuestionView(q["id"]))

class ModifyPointsModal(Modal):
    def __init__(self, user, field, operation):
        super().__init__(title=f"{operation.capitalize()} {field.replace('_', ' ').capitalize()}")
        self.field = field
        self.operation = operation
        self.user = user

        self.user_id_input = TextInput(label="User Mention (@username)", required=True)
        self.points_input = TextInput(label="Points to modify (positive integer)", required=True)

        self.add_item(self.user_id_input)
        self.add_item(self.points_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid_str = self.user_id_input.value.strip()
            uid = int(uid_str.strip("<@!>"))
            points = int(self.points_input.value.strip())
            if points < 0:
                raise ValueError("Points must be positive.")

            scores = load_scores()
            uid_key = str(uid)

            if uid_key not in scores:
                scores[uid_key] = {
                    "insight_points": 0,
                    "contribution_points": 0,
                    "answered_questions": [],
                    "last_contrib_award": None
                }

            if self.operation == "add":
                scores[uid_key][self.field] += points
                verb = "added to"
            else:
                scores[uid_key][self.field] = max(0, scores[uid_key][self.field] - points)
                verb = "removed from"

            save_scores(scores)
            await interaction.response.send_message(f"✅ {points} points {verb} <@{uid}>'s {self.field.replace('_', ' ')}.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

def admin_point_command(name, description, field, operation):
    @tree.command(name=name, description=description)
    async def command(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            return
        await interaction.response.send_modal(ModifyPointsModal(interaction.user, field, operation))

admin_point_command("addinsightpoints", "Add Insight Points to a user", "insight_points", "add")
admin_point_command("addcontributorpoints", "Add Contributor Points to a user", "contribution_points", "add")
admin_point_command("removeinsightpoints", "Remove Insight Points from a user", "insight_points", "remove")
admin_point_command("removecontributorpoints", "Remove Contributor Points from a user", "contribution_points", "remove")

@tree.command(name="leaderboard", description="View the leaderboard by category")
async def leaderboard(interaction: discord.Interaction):
    scores = load_scores()
    view = View(timeout=120)
    select = CategorySelect(interaction, scores)
    view.add_item(select)
    await interaction.response.send_message("Select leaderboard category:", view=view, ephemeral=False)

@client.event
async def on_ready():
    print("\u2705 Discord bot connected")
    await tree.sync()

client.run(TOKEN)
