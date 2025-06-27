import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button
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

def get_rank(points):
    if points <= 10:
        return "🍙 Sticky Rice"
    elif points <= 25:
        return "🥢 Rolling Rookie"
    elif points <= 40:
        return "🍣 Nigiri Novice"
    elif points <= 75:
        return "🐟 Sashimi Strategist"
    elif points <= 100:
        return "🠂 Wasabi Warrior"
    else:
        return "👨‍🍳 Master Sushi Chef"

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

        @discord.ui.button(label="Answer Anonymously (0 Insight)", style=discord.ButtonStyle.secondary)
        async def anon_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnonModal())

        @discord.ui.button(label="Answer Freely (🧠 +1 Insight)", style=discord.ButtonStyle.primary)
        async def free_button(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(AnswerModal(qid=self.qid, user=interaction.user))

    class AnonModal(discord.ui.Modal, title="Anonymous Answer"):
        response = discord.ui.TextInput(label="Your anonymous answer", style=discord.TextStyle.paragraph)

        async def on_submit(self, interaction: discord.Interaction):
            admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                await admin_channel.send(f"📩 Anonymous answer:\n{self.response}")
            await interaction.response.send_message("✅ Received anonymously.", ephemeral=True)

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
                rank = get_rank(total)

                msg = f"🗣️ Answer from <@{uid}>:\n{self.answer}\n\n🔝 +1 Insight Point\n🧮 Insight: {scores[uid]['insight_points']} | 💡 Contribution: {scores[uid]['contribution_points']}\n🌟 Rank: {rank}"
            else:
                msg = f"🗣️ Answer from <@{uid}>:\n{self.answer}\n\n(You've already earned a point for this one!)"

            await interaction.response.send_message(msg)

    channel = client.get_channel(CHANNEL_ID)
    await channel.send(f"@everyone {question}\n\n{submitter_text}", view=QuestionView(q["id"]))

# --- Events & Loops ---
@client.event
async def on_ready():
    print("✅ Discord bot connected")
    await tree.sync()
    purge_channel_before_post.start()
    post_daily_message.start()
    await post_question()  # For testing

@tasks.loop(time=time(hour=11, minute=59))
async def purge_channel_before_post():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.purge(limit=1000)

@tasks.loop(time=time(hour=12, minute=0))
async def post_daily_message():
    await post_question()

# --- Slash Commands ---
@tree.command(name="questionofthedaycommands", description="List of all available question commands")
async def qotd_commands(interaction: discord.Interaction):
    await interaction.response.send_message("Commands:\n/submitquestion\n/score\n/leaderboard\n/questionlist (admin)\n/addpoints (admin)\n/removepoints (admin)", ephemeral=True)

@tree.command(name="submitquestion", description="Submit a new question")
@app_commands.describe(question="Your question")
async def submit_question(interaction: discord.Interaction, question: str):
    questions = load_questions()
    new_id = max([q["id"] for q in questions], default=0) + 1
    q_obj = {"id": new_id, "question": question, "submitter": interaction.user.id}

    questions.append(q_obj)
    save_questions(questions)

    scores = load_scores()
    uid = str(interaction.user.id)
    scores.setdefault(uid, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
    scores[uid]["contribution_points"] += 1
    save_scores(scores)

    await interaction.response.send_message(f"✅ Question submitted (ID: {new_id}) — +1 Contribution Point!", ephemeral=True)

@tree.command(name="score", description="View your score")
async def score(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    scores = load_scores().get(uid, {"insight_points": 0, "contribution_points": 0})
    total = scores['insight_points'] + scores['contribution_points']
    rank = get_rank(total)
    await interaction.response.send_message(f"🧮 Insight: {scores['insight_points']}\n💡 Contribution: {scores['contribution_points']}\n🌟 Rank: {rank}", ephemeral=True)

@tree.command(name="leaderboard", description="View the leaderboard")
@app_commands.describe(category="all, insight, or contributor")
@app_commands.choices(category=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Insight", value="insight"),
    app_commands.Choice(name="Contributor", value="contribution")
])
async def leaderboard(interaction: discord.Interaction, category: app_commands.Choice[str]):
    scores = load_scores()
    users = []
    for uid, data in scores.items():
        total = data["insight_points"] + data["contribution_points"]
        users.append({
            "id": uid,
            "insight": data["insight_points"],
            "contribution": data["contribution_points"],
            "total": total
        })

    key = "total" if category.value == "all" else category.value
    sorted_users = sorted(users, key=itemgetter(key), reverse=True)
    pages = [sorted_users[i:i+10] for i in range(0, len(sorted_users), 10)]

    class LeaderboardView(View):
        def __init__(self):
            super().__init__()
            self.page = 0

        async def update(self, interaction):
            lines = [f"<@{u['id']}> — 🧮 {u['insight']} | 💡 {u['contribution']} | 🌟 {get_rank(u['total'])}" for u in pages[self.page]]
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
        lines = [f"<@{u['id']}> — 🧮 {u['insight']} | 💡 {u['contribution']} | 🌟 {get_rank(u['total'])}" for u in pages[0]]
        await interaction.response.send_message(f"**Leaderboard - {category.name}**\n\n" + "\n".join(lines), view=LeaderboardView(), ephemeral=False)

@tree.command(name="questionlist", description="Admin only: View all questions")
async def question_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    questions = load_questions()
    lines = [f"`{q['id']}`: {q['question'][:80]}{'...' if len(q['question']) > 80 else ''}" for q in questions]
    message = "\n".join(lines) or "No questions found."
    await interaction.response.send_message("**Question List:**\n" + message, ephemeral=True)

# Keep Alive
keep_alive()
client.run(TOKEN)
