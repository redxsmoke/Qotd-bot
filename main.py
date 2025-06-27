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

@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n"
        "/submitquestion\n/removequestion\n/questionlist\n/score\n/leaderboard\n/ranks\n/addpoints\n/removepoints",
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
        # Assign incremental ID based on max existing ID
        max_id = 0
        for q in questions:
            try:
                q_id_int = int(q.get("id"))
                if q_id_int > max_id:
                    max_id = q_id_int
            except:
                pass
        new_id = str(max_id + 1)
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

        await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{new_id}`", ephemeral=True)

@tree.command(name="submitquestion", description="Submit a new question")
async def submit_question(interaction: discord.Interaction):
    await interaction.response.send_modal(SubmitQuestionModal(interaction.user))

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

@tree.command(name="removequestion", description="Admin-only: Remove a question by ID")
@app_commands.describe(question_id="Enter the ID of the question to remove")
async def remove_question(interaction: discord.Interaction, question_id: str):
    if not interaction.user.guild_permissions.manage_messages:
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

# --- Updated Add/Remove Points Modal with Point Type Select ---

class PointsModal(Modal):
    point_type_select = Select(
        placeholder="Select point type...",
        options=[
            discord.SelectOption(label="Insight", value="insight"),
            discord.SelectOption(label="Contribution", value="contribution")
        ],
        min_values=1,
        max_values=1,
        custom_id="point_type_select"
    )
    quantity_input = TextInput(label="Quantity (positive integer)", style=discord.TextStyle.short, required=True)

    def __init__(self, action: str, user: discord.User):
        super().__init__(title=f"{action} Points for {user.display_name}")
        self.action = action
        self.target_user = user
        self.add_item(self.point_type_select)
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction):
        point_type = self.point_type_select.values[0]
        try:
            qty = int(self.quantity_input.value.strip())
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("\u274C Quantity must be a positive integer.", ephemeral=True)
            return

        scores = load_scores()
        uid = str(self.target_user.id)
        if uid not in scores:
            scores[uid] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}

        key = f"{point_type}_points"
        current = scores[uid].get(key, 0)

        if self.action == "Add":
            scores[uid][key] = current + qty
        else:
            scores[uid][key] = max(0, current - qty)

        save_scores(scores)
        await interaction.response.send_message(f"\u2705 {self.action}ed {qty} {point_type} points for <@{uid}>.", ephemeral=True)

@tree.command(name="addpoints", description="Admin-only: Add points to a user")
@app_commands.describe(user="The user to add points to")
async def add_points(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(PointsModal("Add", user))

@tree.command(name="removepoints", description="Admin-only: Remove points from a user")
@app_commands.describe(user="The user to remove points from")
async def remove_points(interaction: discord.Interaction, user: discord.User):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(PointsModal("Remove", user))


# --- New Leaderboard Pagination ---

class LeaderboardView(View):
    def __init__(self, entries, category):
        super().__init__(timeout=180)
        self.entries = entries  # List of (user_id, insight_points, contribution_points)
        self.category = category
        self.page = 0
        self.max_pages = (len(entries) - 1) // 10 + 1 if entries else 1

    def format_page(self):
        start = self.page * 10
        end = start + 10
        page_entries = self.entries[start:end]
        lines = []
        for idx, (uid, insight, contrib) in enumerate(page_entries, start=start+1):
            user_mention = f"<@{uid}>"
            if self.category == "all":
                total = insight + contrib
                lines.append(f"**{idx}.** {user_mention} — {insight} insight / {contrib} contribution (Total: {total})")
            elif self.category == "insight":
                lines.append(f"**{idx}.** {user_mention} — {insight} insight points")
            else:  # contribution
                lines.append(f"**{idx}.** {user_mention} — {contrib} contribution points")
        return "\n".join(lines) if lines else "No entries to display."

    async def update_message(self, interaction):
        content = f"**Leaderboard - {self.category.capitalize()} Points (Page {self.page + 1}/{self.max_pages})**\n\n"
        content += self.format_page()
        await interaction.response.edit_message(content=content, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if self.page + 1 < self.max_pages:
            self.page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

class LeaderboardCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="All", description="Combined Insight + Contribution Points", value="all"),
            discord.SelectOption(label="Insight", description="Rank by Insight Points only", value="insight"),
            discord.SelectOption(label="Contribution", description="Rank by Contribution Points only", value="contribution")
        ]
        super().__init__(placeholder="Select leaderboard category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        scores = load_scores()

        # Filter out users with 0 points in the category
        entries = []
        for uid, data in scores.items():
            insight = data.get("insight_points", 0)
            contrib = data.get("contribution_points", 0)
            total = insight + contrib
            if category == "all" and total > 0:
                entries.append((int(uid), insight, contrib))
            elif category == "insight" and insight > 0:
                entries.append((int(uid), insight, contrib))
            elif category == "contribution" and contrib > 0:
                entries.append((int(uid), insight, contrib))

        # Sort entries
        if category == "all":
            entries.sort(key=lambda x: x[1] + x[2], reverse=True)
        elif category == "insight":
            entries.sort(key=lambda x: x[1], reverse=True)
        else:  # contribution
            entries.sort(key=lambda x: x[2], reverse=True)

        if not entries:
            await interaction.response.edit_message(content=f"No users with points in category **{category}**.", view=None)
            return

        view = LeaderboardView(entries, category)
        content = f"**Leaderboard - {category.capitalize()} Points (Page 1/{view.max_pages})**\n\n{view.format_page()}"
        await interaction.response.edit_message(content=content, view=view)

class LeaderboardCategoryView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(LeaderboardCategorySelect())

@tree.command(name="leaderboard", description="View the leaderboard")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardCategoryView()
    await interaction.response.send_message("Select a leaderboard category:", view=view, ephemeral=True)


keep_alive()
client.run(TOKEN)
