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
print("💡 main.py is running")

# Load token and channel IDs from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ DISCORD_BOT_TOKEN not set!")
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_CHANNEL_ID = int(os.getenv('DISCORD_ADMIN_CHANNEL_ID', CHANNEL_ID))

QUESTIONS_FILE = 'questions.json'
SCORES_FILE = 'user_scores.json'
START_DATE = datetime.date(2025, 6, 25)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Helper Functions ---
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

# --- Post Question with Buttons ---
async def post_question():
    q = get_today_question()
    if not q: return
    question = q["question"]
    submitter = q.get("submitter")
    submitter_text = f"🧠 Question submitted by <@{submitter}>" if submitter else "🤖 Question submitted by the Question of the Day Bot"

    class QuestionView(View):
        def __init__(self, qid):
            super().__init__(timeout=None)
            self.qid = qid

        @discord.ui.button(label="Answer Freely 🧠 (+1 Insight)", style=discord.ButtonStyle.success, custom_id="freely")
        async def free_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnswerFreelyModal(qid=self.qid, user=interaction.user))

        @discord.ui.button(label="Answer Anonymously (0 Insight)", style=discord.ButtonStyle.secondary, custom_id="anon")
        async def anon_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnswerAnonymouslyModal(qid=self.qid, user=interaction.user))

    class AnswerFreelyModal(Modal, title="Answer Freely"):
        answer = TextInput(label="Your answer", style=discord.TextStyle.paragraph)

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
                msg = f"🔣 Answer from <@{uid}>:\n{self.answer}\n\n🌟 +1 Insight Point!"
            else:
                msg = f"🔣 Answer from <@{uid}>:\n{self.answer}\n\n(You've already earned a point for this one!)"

            await interaction.response.send_message(msg)

    class AnswerAnonymouslyModal(Modal, title="Answer Anonymously"):
        answer = TextInput(label="Your anonymous answer", style=discord.TextStyle.paragraph)

        def __init__(self, qid, user):
            super().__init__()
            self.qid = qid
            self.user = user

        async def on_submit(self, interaction: discord.Interaction):
            admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                await admin_channel.send(f"📬 Anonymous answer:\n{self.answer}")
                await interaction.response.send_message("✅ Received anonymously.", ephemeral=True)

    channel = client.get_channel(CHANNEL_ID)
    await channel.send(f"@everyone {question}\n\n{submitter_text}", view=QuestionView(q["id"]))

# --- Events & Loops ---
@client.event
async def on_ready():
    print("✅ Discord bot connected")
    await tree.sync()
    purge_channel_before_post.start()
    post_daily_message.start()
    await post_question()

@tasks.loop(time=time(hour=11, minute=59))
async def purge_channel_before_post():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.purge(limit=1000)

@tasks.loop(time=time(hour=12, minute=0))
async def post_daily_message():
    await post_question()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.guild is None:
        admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
        await admin_channel.send(f"📬 Anonymous answer:\n{message.content}")
        await message.channel.send("✅ Received anonymously.")

# --- Slash Commands ---
@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message("Available commands:\n/submitquestion\n/score\n/leaderboard", ephemeral=True)

@tree.command(name="submitquestion", description="Submit a new question")
@app_commands.describe(question="Your question", type="plain or multiple choice", choice1="Option 1", choice2="Option 2", choice3="Optional", choice4="Optional")
@app_commands.choices(type=[
    app_commands.Choice(name="question", value="plain"),
    app_commands.Choice(name="question with answer (mult-choice)", value="multiple_choice")
])
async def submit_question(interaction: discord.Interaction, question: str, type: app_commands.Choice[str], choice1: str = None, choice2: str = None, choice3: str = None, choice4: str = None):
    questions = load_questions()
    new_id = max([q["id"] for q in questions], default=0) + 1
    q_obj = {"id": new_id, "question": question, "submitter": interaction.user.id}

    if type.value == "multiple_choice":
        if not choice1 or not choice2:
            await interaction.response.send_message("❌ You must provide at least 2 choices.", ephemeral=True)
            return
        q_obj["answers"] = [c for c in [choice1, choice2, choice3, choice4] if c]

    questions.append(q_obj)
    save_questions(questions)

    scores = load_scores()
    uid = str(interaction.user.id)
    scores.setdefault(uid, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
    scores[uid]["contribution_points"] += 1
    save_scores(scores)

    await interaction.response.send_message(f"✅ Question submitted (ID: {new_id}) — +1 Brain Fuel!", ephemeral=True)

@tree.command(name="score", description="View your points")
async def score(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    scores = load_scores().get(uid, {"insight_points": 0, "contribution_points": 0})
    await interaction.response.send_message(f"🧠 Insight Points: {scores['insight_points']}\n🔥 Brain Fuel: {scores['contribution_points']}", ephemeral=True)

@tree.command(name="leaderboard", description="See the leaderboard")
@app_commands.describe(category="Sort by: all, insight, brainfuel")
@app_commands.choices(category=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Insight", value="insight"),
    app_commands.Choice(name="Brain Fuel", value="brainfuel")
])
async def leaderboard(interaction: discord.Interaction, category: app_commands.Choice[str]):
    scores = load_scores()
    users = []
    for uid, data in scores.items():
        total = data["insight_points"] + data["contribution_points"]
        users.append({
            "id": uid,
            "insight": data["insight_points"],
            "fuel": data["contribution_points"],
            "total": total
        })

    key = "total" if category.value == "all" else ("insight" if category.value == "insight" else "fuel")
    sorted_users = sorted(users, key=itemgetter(key), reverse=True)
    pages = [sorted_users[i:i+10] for i in range(0, len(sorted_users), 10)]

    class LeaderboardView(View):
        def __init__(self):
            super().__init__()
            self.page = 0

        async def update(self, interaction):
            lines = [f"<@{u['id']}> — {u['insight']} Insight | {u['fuel']} Brain Fuel" for u in pages[self.page]]
            await interaction.response.edit_message(content=f"**Leaderboard - {category.name}**\n\n" + "\n".join(lines), view=self)

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
        async def previous(self, interaction, _):
            if self.page > 0:
                self.page -= 1
                await self.update(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
        async def next(self, interaction, _):
            if self.page < len(pages) - 1:
                self.page += 1
                await self.update(interaction)

    if not pages:
        await interaction.response.send_message("No scores yet!", ephemeral=True)
    else:
        lines = [f"<@{u['id']}> — {u['insight']} Insight | {u['fuel']} Brain Fuel" for u in pages[0]]
        await interaction.response.send_message(f"**Leaderboard - {category.name}**\n\n" + "\n".join(lines), view=LeaderboardView(), ephemeral=False)

# Keep alive & run
keep_alive()
client.run(TOKEN)
