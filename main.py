import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
from keep_alive import keep_alive
import logging
from datetime import time
import os
from operator import itemgetter

logging.basicConfig(level=logging.INFO)
print("\U0001F4A1 main.py is running")

# Load token and channel IDs from environment variables
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

# --- Post Question with Buttons ---
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

# --- Events & Loops ---
@client.event
async def on_ready():
    print("\u2705 Discord bot connected")
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
        await admin_channel.send(f"\U0001F4E9 Anonymous answer:\n{message.content}")
        await message.channel.send("\u2705 Received anonymously.")

# --- Slash Commands ---

@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n/submitquestion\n/removequestion\n/questionlist\n/score\n/leaderboard\n/ranks\n/addpoints\n/removepoints",
        ephemeral=True
    )

@tree.command(name="ranks", description="View the sushi-themed ranking tiers")
async def ranks(interaction: discord.Interaction):
    await interaction.response.send_message(
        "\U0001F3C6 **Sushi Ranks**\n"
        "0-10: \U0001F363 Rice Rookie\n"
        "11-25: \U0001F364 Miso Mind\n"
        "26-40: \U0001F363 Sashimi Scholar\n"
        "41-75: \U0001F95A Wasabi Wizard\n"
        "76+: \U0001F371 Sushi Sensei",
        ephemeral=True
    )

@tree.command(name="questionlist", description="Admin-only view of questions with IDs")
async def question_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    questions = load_questions()
    if not questions:
        await interaction.response.send_message("\u26A0 No questions found.", ephemeral=True)
        return
    lines = [f"`{q['id']}`: {q['question'][:80]}{'...' if len(q['question']) > 80 else ''}" for q in questions]
    await interaction.response.send_message("\U0001F4CB Questions:\n" + "\n".join(lines), ephemeral=True)

# Submit Question with Modal prompt
class SubmitQuestionModal(Modal, title="Submit a Question"):
    question_input = TextInput(label="Question", style=discord.TextStyle.paragraph, required=True, max_length=500)
    has_answer = Select(
    placeholder="Does this question have an answer?",
    options=[
        discord.SelectOption(label="No, just a question", value="no"),
        discord.SelectOption(label="Yes, with answer", value="yes"),
    ]
)

    def __init__(self, user):
        super().__init__()
        self.user = user
        self.answer_input = None

    async def on_submit(self, interaction: discord.Interaction):
        question_text = self.question_input.value.strip()
        has_answer = self.has_answer.values[0]

        if has_answer == "yes":
            # Show modal to enter answer
            await interaction.response.send_modal(SubmitAnswerModal(self.user, question_text))
        else:
            # Save question only
            questions = load_questions()
            new_id = generate_unique_id()
            questions.append({"id": new_id, "question": question_text, "submitter": str(self.user.id)})
            save_questions(questions)
            # Notify admins/mods
            admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
            await admin_channel.send(f"🧠 <@{self.user.id}> has submitted a new Question of the Day. Use /listquestions to view the question and /removequestion if moderation is needed.")
            await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{new_id}`", ephemeral=True)

class SubmitAnswerModal(Modal, title="Submit Answer for Question"):
    answer_input = TextInput(label="Answer", style=discord.TextStyle.paragraph, required=True, max_length=300)

    def __init__(self, user, question_text):
        super().__init__()
        self.user = user
        self.question_text = question_text

    async def on_submit(self, interaction: discord.Interaction):
        answer_text = self.answer_input.value.strip()
        questions = load_questions()
        new_id = generate_unique_id()
        questions.append({
            "id": new_id,
            "question": self.question_text,
            "answer": answer_text,
            "submitter": str(self.user.id)
        })
        save_questions(questions)
        admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
        await admin_channel.send(f"🧠 <@{self.user.id}> has submitted a new Question of the Day. Use /listquestions to view the question and /removequestion if moderation is needed.")
        await interaction.response.send_message(f"\u2705 Question and answer submitted successfully! ID: `{new_id}`", ephemeral=True)

@tree.command(name="submitquestion", description="Submit a new question")
async def submit_question(interaction: discord.Interaction):
    await interaction.response.send_modal(SubmitQuestionModal(interaction.user))

@tree.command(name="removequestion", description="Admin-only: Remove a question by ID")
@app_commands.describe(question_id="ID of the question to remove")
async def remove_question(interaction: discord.Interaction, question_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    questions = load_questions()
    for q in questions:
        if q["id"] == question_id:
            questions.remove(q)
            save_questions(questions)
            await interaction.response.send_message(f"\u2705 Question `{question_id}` removed successfully.", ephemeral=True)
            return
    await interaction.response.send_message(f"\u26A0 Question ID `{question_id}` not found.", ephemeral=True)

@tree.command(name="score", description="Show your scores and rank")
async def score(interaction: discord.Interaction):
    scores = load_scores()
    uid = str(interaction.user.id)
    user_scores = scores.get(uid, {"insight_points": 0, "contribution_points": 0})
    total = user_scores.get("insight_points", 0) + user_scores.get("contribution_points", 0)
    rank = get_rank(total)
    msg = (
        f"Scores for <@{uid}>:\n"
        f"⭐ Insight Points: {user_scores.get('insight_points', 0)}\n"
        f"💡 Contribution Points: {user_scores.get('contribution_points', 0)}\n"
        f"🏆 Rank: {rank}\n"
        f"🔢 Total Points: {total}"
    )
    await interaction.response.send_message(msg, ephemeral=True)

# Leaderboard Pagination Helper
class LeaderboardView(View):
    def __init__(self, leaderboard_data, category):
        super().__init__(timeout=180)
        self.leaderboard_data = leaderboard_data
        self.category = category
        self.current_page = 0
        self.max_pages = (len(leaderboard_data) - 1) // 10

    def format_page(self):
        start = self.current_page * 10
        end = start + 10
        page_data = self.leaderboard_data[start:end]
        lines = []
        for idx, (uid, scores) in enumerate(page_data, start=start+1):
            insight = scores.get("insight_points", 0)
            contrib = scores.get("contribution_points", 0)
            total = insight + contrib
            rank = get_rank(total)
            if self.category == "all":
                line = f"#{idx} <@{uid}> - Insight: {insight}, Contribution: {contrib}, Total: {total}, Rank: {rank}"
            elif self.category == "insight":
                line = f"#{idx} <@{uid}> - Insight Points: {insight}, Rank: {rank}"
            else:  # contributor
                line = f"#{idx} <@{uid}> - Contribution Points: {contrib}, Rank: {rank}"
            lines.append(line)
        return "\n".join(lines) if lines else "No entries to display."

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(content=self.format_page(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.max_pages:
            self.current_page += 1
            await interaction.response.edit_message(content=self.format_page(), view=self)

@tree.command(name="leaderboard", description="View the leaderboard")
@app_commands.describe(category="Choose leaderboard category (all, insight, contributor)")
async def leaderboard(interaction: discord.Interaction, category: str = "all"):
    category = category.lower()
    if category not in ("all", "insight", "contributor"):
        await interaction.response.send_message("\u274C Invalid category! Choose from all, insight, contributor.", ephemeral=True)
        return
    scores = load_scores()
    # Filter users based on category and points
    filtered = {}
    for uid, score in scores.items():
        insight = score.get("insight_points", 0)
        contrib = score.get("contribution_points", 0)
        total = insight + contrib
        if category == "all" and total > 0:
            filtered[uid] = score
        elif category == "insight" and insight > 0:
            filtered[uid] = score
        elif category == "contributor" and contrib > 0:
            filtered[uid] = score
    if not filtered:
        await interaction.response.send_message("\u26A0 No entries found for this category.", ephemeral=True)
        return
    # Sort
    if category == "all":
        sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("insight_points", 0) + x[1].get("contribution_points", 0), reverse=True)
    elif category == "insight":
        sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("insight_points", 0), reverse=True)
    else:
        sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("contribution_points", 0), reverse=True)
    view = LeaderboardView(sorted_scores, category)
    await interaction.response.send_message(view.format_page(), view=view, ephemeral=True)

# AddPoints and RemovePoints Modal
class PointsModal(Modal):
    user_id_input = TextInput(label="User ID to modify points for", style=discord.TextStyle.short, required=True)
    point_type_select = Select(
    placeholder="Select point type",
    options=[
        discord.SelectOption(label="Insight Points", value="insight"),
        discord.SelectOption(label="Contribution Points", value="contribution"),
    ]
)
    quantity_input = TextInput(label="Quantity (positive integer)", style=discord.TextStyle.short, required=True)

    def __init__(self, action: str):
        super().__init__(title=f"{action} Points")
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        uid = self.user_id_input.value.strip()
        ptype = self.point_type_select.values[0]
        try:
            qty = int(self.quantity_input.value)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("\u274C Quantity must be a positive integer.", ephemeral=True)
            return
        scores = load_scores()
        if uid not in scores:
            scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}
        if self.action == "Add":
            scores[uid][ptype] = scores[uid].get(ptype, 0) + qty
        else:
            scores[uid][ptype] = max(0, scores[uid].get(ptype, 0) - qty)
        save_scores(scores)
        await interaction.response.send_message(f"\u2705 {self.action}ed {qty} {ptype.replace('_', ' ')} for <@{uid}>.", ephemeral=True)

@tree.command(name="addpoints", description="Admin-only: Add points to a user")
async def add_points(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(PointsModal("Add"))

@tree.command(name="removepoints", description="Admin-only: Remove points from a user")
async def remove_points(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(PointsModal("Remove"))

# Keep alive & run
keep_alive()
client.run(TOKEN)
