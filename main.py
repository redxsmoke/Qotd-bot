import discord
import json
import datetime
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
import logging
from datetime import time
import os

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

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages

# ----- Daily Question Posting Logic & Modal Views -----

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
                msg = (f"\U0001F5E3️ Answer from <@{uid}>:\n{self.answer}\n\n"
                       f"⭐ Insight Points: {scores[uid]['insight_points']} | 💡 Contribution: {scores[uid]['contribution_points']} | 🏆 Rank: {get_rank(total)}")
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

# ----- Tasks -----

@tasks.loop(time=time(hour=11, minute=59))
async def purge_channel_before_post():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.purge(limit=1000)

@tasks.loop(time=time(hour=12, minute=0))
async def post_daily_message():
    await post_question()

# ----- Events -----

@client.event
async def on_ready():
    print("\u2705 Discord bot connected")
    await tree.sync()
    purge_channel_before_post.start()
    post_daily_message.start()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.guild is None:
        admin_channel = client.get_channel(ADMIN_CHANNEL_ID)
        await admin_channel.send(f"\U0001F4E9 Anonymous answer:\n{message.content}")
        await message.channel.send("\u2705 Received anonymously.")

# ----- Slash Commands -----

@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n"
        "/submitquestion\n/removequestion\n/questionlist\n/score\n/leaderboard\n/ranks\n"
        "/addinsightpoints\n/addcontributorpoints\n/removeinsightpoints\n/removecontributorpoints",
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

class SubmitQuestionModal(Modal, title="Submit a Question"):
    question_input = TextInput(label="Your question", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        question_text = self.question_input.value.strip()
        questions = load_questions()

        # Find max numeric ID and assign next
        existing_ids = []
        for q in questions:
            try:
                existing_ids.append(int(q.get("id")))
            except (TypeError, ValueError):
                pass
        next_id = str(max(existing_ids) + 1) if existing_ids else "1"

        questions.append({"id": next_id, "question": question_text, "submitter": str(self.user.id)})
        save_questions(questions)

        # Add contributor point, limited once per day
        scores = load_scores()
        uid = str(self.user.id)
        today = datetime.date.today()

        if uid not in scores:
            scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": [], "last_contrib_award": None}

        last_award = scores[uid].get("last_contrib_award")
        if last_award != str(today):
            scores[uid]["contribution_points"] += 1
            scores[uid]["last_contrib_award"] = str(today)
            save_scores(scores)
            await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{next_id}`\n\n💡 You have been awarded 1 contribution point for your submission today.", ephemeral=True)
        else:
            await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{next_id}`\n\n⚠️ You have already received a contribution point today.", ephemeral=True)

@tree.command(name="submitquestion", description="Submit a new question")
async def submit_question(interaction: discord.Interaction):
    await interaction.response.send_modal(SubmitQuestionModal(interaction.user))

@tree.command(name="questionlist", description="Admin-only view of questions with IDs")
async def question_list(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    questions = load_questions()
    if not questions:
        await interaction.response.send_message("\u26A0 No questions found.", ephemeral=True)
        return
    lines = [f"`{q['id']}`: {q['question'][:80]}{'...' if len(q['question']) > 80 else ''}" for q in questions]
    await interaction.response.send_message("\U0001F4CB Questions:\n" + "\n".join(lines), ephemeral=True)

@tree.command(name="removequestion", description="Admin-only: Remove a question by ID")
@app_commands.describe(question_id="Enter the ID of the question to remove")
async def remove_question(interaction: discord.Interaction, question_id: str):
    if not is_admin(interaction):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    questions = load_questions()
    new_questions = [q for q in questions if q['id'] != question_id]
    if len(new_questions) == len(questions):
        await interaction.response.send_message("\u274C No question found with that ID.", ephemeral=True)
        return
    save_questions(new_questions)
    await interaction.response.send_message(f"\u2705 Question `{question_id}` removed successfully.", ephemeral=True)

@tree.command(name="score", description="Show your score and rank")
async def score(interaction: discord.Interaction):
    scores = load_scores()
    uid = str(interaction.user.id)
    score = scores.get(uid, {"insight_points": 0, "contribution_points": 0})
    insight = score.get("insight_points", 0)
    contrib = score.get("contribution_points", 0)
    total = insight + contrib
    await interaction.response.send_message(f"⭐ Insight: {insight}\n💡 Contribution: {contrib}\n🏆 Rank: {get_rank(total)}", ephemeral=True)

# Leaderboard select menu and view logic

class LeaderboardSelect(Select):
    def __init__(self, interaction, scores):
        options = [
            discord.SelectOption(label="All", description="Combined Insight and Contribution points"),
            discord.SelectOption(label="Insight", description="Insight points only"),
            discord.SelectOption(label="Contributor", description="Contribution points only"),
        ]
        super().__init__(placeholder="Choose leaderboard category...", min_values=1, max_values=1, options=options)
        self.interaction = interaction
        self.scores = scores
        self.page = 0

    async def update_message(self, interaction):
        category = self.values[0]
        leaderboard = []

        if category == "All":
            for uid, score in self.scores.items():
                insight = score.get("insight_points", 0)
                contrib = score.get("contribution_points", 0)
                total = insight + contrib
                if total > 0:
                    leaderboard.append((uid, insight, contrib, total))
            leaderboard.sort(key=lambda x: x[3], reverse=True)
        elif category == "Insight":
            for uid, score in self.scores.items():
                insight = score.get("insight_points", 0)
                if insight > 0:
                    leaderboard.append((uid, insight))
            leaderboard.sort(key=lambda x: x[1], reverse=True)
        else:  # Contributor
            for uid, score in self.scores.items():
                contrib = score.get("contribution_points", 0)
                if contrib > 0:
                    leaderboard.append((uid, contrib))
            leaderboard.sort(key=lambda x: x[1], reverse=True)

        items_per_page = 10
        max_page = (len(leaderboard) - 1) // items_per_page if leaderboard else 0
        self.page = max(0, min(self.page, max_page))

        start_idx = self.page * items_per_page
        end_idx = start_idx + items_per_page
        page_entries = leaderboard[start_idx:end_idx]

        if not leaderboard:
            text = "No users found with points in this category."
        else:
            lines = []
            for i, entry in enumerate(page_entries, start=start_idx + 1):
                if category == "All":
                    uid, insight, contrib, total = entry
                    lines.append(f"{i}. <@{uid}> — {insight} insight points / {contrib} contribution points")
                else:
                    uid, pts = entry
                    lines.append(f"{i}. <@{uid}> — {pts} points")
            text = "\n".join(lines)

        footer_text = f"Page {self.page + 1} / {max_page + 1}"

        embed = discord.Embed(title=f"Leaderboard — {category} Points", description=text, color=discord.Color.green())
        embed.set_footer(text=footer_text)

        view = LeaderboardView(self.interaction, self.scores, category, self.page, max_page)
        await interaction.response.edit_message(embed=embed, view=view)

    async def callback(self, interaction: discord.Interaction):
        await self.update_message(interaction)

class LeaderboardView(View):
    def __init__(self, interaction, scores, category, page, max_page):
        super().__init__(timeout=120)
        self.interaction = interaction
        self.scores = scores
        self.category = category
        self.page = page
        self.max_page = max_page

        self.add_item(CategorySelect(self.interaction, self.scores))

        self.prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        self.prev_button.disabled = (self.page == 0)
        self.next_button.disabled = (self.page == self.max_page)

    async def prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        await self.update_leaderboard(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.page = min(self.max_page, self.page + 1)
        await self.update_leaderboard(interaction)

    async def update_leaderboard(self, interaction):
        category = self.category
        leaderboard = []

        if category == "All":
            for uid, score in self.scores.items():
                insight = score.get("insight_points", 0)
                contrib = score.get("contribution_points", 0)
                total = insight + contrib
                if total > 0:
                    leaderboard.append((uid, insight, contrib, total))
            leaderboard.sort(key=lambda x: x[3], reverse=True)
        elif category == "Insight":
            for uid, score in self.scores.items():
                insight = score.get("insight_points", 0)
                if insight > 0:
                    leaderboard.append((uid, insight))
            leaderboard.sort(key=lambda x: x[1], reverse=True)
        else:  # Contributor
            for uid, score in self.scores.items():
                contrib = score.get("contribution_points", 0)
                if contrib > 0:
                    leaderboard.append((uid, contrib))
            leaderboard.sort(key=lambda x: x[1], reverse=True)

        items_per_page = 10
        max_page = (len(leaderboard) - 1) // items_per_page if leaderboard else 0
        self.max_page = max_page
        self.page = max(0, min(self.page, max_page))

        start_idx = self.page * items_per_page
        end_idx = start_idx + items_per_page
        page_entries = leaderboard[start_idx:end_idx]

        if not leaderboard:
            text = "No users found with points in this category."
        else:
            lines = []
            for i, entry in enumerate(page_entries, start=start_idx + 1):
                if category == "All":
                    uid, insight, contrib, total = entry
                    lines.append(f"{i}. <@{uid}> — {insight} insight points / {contrib} contribution points")
                else:
                    uid, pts = entry
                    lines.append(f"{i}. <@{uid}> — {pts} points")
            text = "\n".join(lines)

        footer_text = f"Page {self.page + 1} / {self.max_page + 1}"

        embed = discord.Embed(title=f"Leaderboard — {category} Points", description=text, color=discord.Color.green())
        embed.set_footer(text=footer_text)

        self.prev_button.disabled = (self.page == 0)
        self.next_button.disabled = (self.page == self.max_page)

        view = LeaderboardView(self.interaction, self.scores, category, self.page, self.max_page)
        await interaction.response.edit_message(embed=embed, view=view)

class CategorySelect(Select):
    def __init__(self, interaction, scores):
        options = [
            discord.SelectOption(label="All", description="Combined Insight and Contribution points"),
            discord.SelectOption(label="Insight", description="Insight points only"),
            discord.SelectOption(label="Contributor", description="Contribution points only"),
        ]
        super().__init__(placeholder="Choose leaderboard category...", min_values=1, max_values=1, options=options)
        self.interaction = interaction
        self.scores = scores

    async def callback(self, interaction: discord.Interaction):
        lb_select = LeaderboardSelect(interaction, self.scores)
        lb_select.page = 0
        lb_select.values = self.values
        await lb_select.update_message(interaction)

@tree.command(name="leaderboard", description="Show leaderboard by category")
async def leaderboard(interaction: discord.Interaction):
    scores = load_scores()
    if not scores:
        await interaction.response.send_message("No scores found yet.", ephemeral=True)
        return
    view = LeaderboardView(interaction, scores, "All", 0, 0)
    # Start with first page and "All" category leaderboard
    lb_select = LeaderboardSelect(interaction, scores)
    lb_select.page = 0
    lb_select.values = ["All"]
    await lb_select.update_message(interaction)

    await interaction.response.send_message("Leaderboard:", view=view, ephemeral=True)

# --- Admin-only points commands ---

@app_commands.check(is_admin)
@tree.command(name="addinsightpoints", description="Admin-only: Add insight points to a user")
@app_commands.describe(user="User to add points to", amount="Amount of points to add")
async def add_insight_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    scores = load_scores()
    uid = str(user.id)
    if uid not in scores:
        scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}
    scores[uid]["insight_points"] += amount
    save_scores(scores)
    await interaction.response.send_message(f"\u2705 Added {amount} insight points to {user.mention}.", ephemeral=True)

@app_commands.check(is_admin)
@tree.command(name="addcontributorpoints", description="Admin-only: Add contributor points to a user")
@app_commands.describe(user="User to add points to", amount="Amount of points to add")
async def add_contributor_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    scores = load_scores()
    uid = str(user.id)
    if uid not in scores:
        scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}
    scores[uid]["contribution_points"] += amount
    save_scores(scores)
    await interaction.response.send_message(f"\u2705 Added {amount} contributor points to {user.mention}.", ephemeral=True)

@app_commands.check(is_admin)
@tree.command(name="removeinsightpoints", description="Admin-only: Remove insight points from a user")
@app_commands.describe(user="User to remove points from", amount="Amount of points to remove")
async def remove_insight_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    scores = load_scores()
    uid = str(user.id)
    if uid not in scores:
        scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}
    scores[uid]["insight_points"] = max(0, scores[uid]["insight_points"] - amount)
    save_scores(scores)
    await interaction.response.send_message(f"\u2705 Removed {amount} insight points from {user.mention}.", ephemeral=True)

@app_commands.check(is_admin)
@tree.command(name="removecontributorpoints", description="Admin-only: Remove contributor points from a user")
@app_commands.describe(user="User to remove points from", amount="Amount of points to remove")
async def remove_contributor_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    scores = load_scores()
    uid = str(user.id)
    if uid not in scores:
        scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}
    scores[uid]["contribution_points"] = max(0, scores[uid]["contribution_points"] - amount)
    save_scores(scores)
    await interaction.response.send_message(f"\u2705 Removed {amount} contributor points from {user.mention}.", ephemeral=True)

# ----- Run bot -----
client.run(TOKEN)
