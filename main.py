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
intents.members = True  # Needed for member list
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

# --- Question Pagination View for /questionslist ---
class QuestionsListView(View):
    def __init__(self, questions):
        super().__init__(timeout=180)
        self.questions = questions
        self.current_page = 0
        self.max_pages = (len(questions) - 1) // 10

    def format_page(self):
        start = self.current_page * 10
        end = start + 10
        page_data = self.questions[start:end]
        lines = []
        for q in page_data:
            qid = q['id']
            qtext = q['question']
            short = qtext if len(qtext) <= 80 else qtext[:77] + "..."
            lines.append(f"`{qid}`: {short}")
        footer = f"\nPage {self.current_page+1}/{self.max_pages+1}"
        return "\U0001F4CB Questions:\n" + "\n".join(lines) + footer

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

# --- Submit Question Modal ---
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

        # Notify admins/mods in DM
        admins_mods = [member for member in guild.members if member.guild_permissions.administrator or member.guild_permissions.manage_messages]
        dm_message = f"🧠 <@{self.user.id}> has submitted a new Question of the Day. Use /questionslist to view the question and /removequestion if moderation is needed."
        for admin in admins_mods:
            try:
                await admin.send(dm_message)
            except:
                pass  # ignore if DM fails

        await interaction.response.send_message(f"\u2705 Question submitted successfully! ID: `{new_id}`", ephemeral=True)

# --- Remove Question Modal ---
class RemoveQuestionModal(Modal, title="Remove a Question"):
    question_id_input = TextInput(label="Enter Question ID to remove", style=discord.TextStyle.short, required=True)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
            await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
            return

        qid = self.question_id_input.value.strip()
        questions = load_questions()
        new_questions = [q for q in questions if q['id'] != qid]
        if len(new_questions) == len(questions):
            await interaction.response.send_message(f"\u274C Question ID `{qid}` not found.", ephemeral=True)
            return
        save_questions(new_questions)
        await interaction.response.send_message(f"\u2705 Question ID `{qid}` removed successfully.", ephemeral=True)

# --- Score Display ---
@tree.command(name="score", description="View your insight score, contribution score, and rank")
async def score(interaction: discord.Interaction):
    scores = load_scores()
    uid = str(interaction.user.id)
    user_scores = scores.get(uid, {"insight_points": 0, "contribution_points": 0})
    insight = user_scores.get("insight_points", 0)
    contrib = user_scores.get("contribution_points", 0)
    total = insight + contrib
    rank = get_rank(total)
    await interaction.response.send_message(
        f"Your Scores:\n⭐ Insight Points: {insight}\n💡 Contribution Points: {contrib}\n🏆 Rank: {rank}",
        ephemeral=True
    )

# --- Leaderboard Pagination and Category Selection ---

class LeaderboardView(View):
    def __init__(self, leaderboard_data, category):
        super().__init__(timeout=180)
        self.leaderboard_data = leaderboard_data
        self.category = category
        self.current_page = 0
        self.max_pages = (len(leaderboard_data) - 1) // 10 if leaderboard_data else 0

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

class LeaderboardCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="All", value="all", description="All points combined"),
            discord.SelectOption(label="Insight", value="insight", description="Insight points only"),
            discord.SelectOption(label="Contributor", value="contributor", description="Contribution points only"),
        ]
        super().__init__(placeholder="Select leaderboard category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        scores = load_scores()
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
            await interaction.response.edit_message(content="\u26A0 No entries found for this category.", view=None)
            return

        if category == "all":
            sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("insight_points", 0) + x[1].get("contribution_points", 0), reverse=True)
        elif category == "insight":
            sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("insight_points", 0), reverse=True)
        else:
            sorted_scores = sorted(filtered.items(), key=lambda x: x[1].get("contribution_points", 0), reverse=True)

        view = LeaderboardView(sorted_scores, category)
        await interaction.response.edit_message(content=view.format_page(), view=view)

class LeaderboardCategoryView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(LeaderboardCategorySelect())

@tree.command(name="leaderboard", description="View the leaderboard")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardCategoryView()
    await interaction.response.send_message("Select leaderboard category:", view=view, ephemeral=True)

# --- Ranks Command ---
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

# --- Points Modification Flow ---

class PointsUserSelect(discord.ui.Select):
    def __init__(self, users, action):
        options = [discord.SelectOption(label=user.display_name, value=str(user.id)) for user in users]
        super().__init__(placeholder="Select a user", min_values=1, max_values=1, options=options)
        self.selected_user_id = None
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        self.selected_user_id = self.values[0]
        await interaction.response.edit_message(content="Select point type to modify:", view=PointsTypeSelectView(self.selected_user_id, self.action))

class PointsTypeSelect(discord.ui.Select):
    def __init__(self, user_id, action):
        options = [
            discord.SelectOption(label="Insight", value="insight"),
            discord.SelectOption(label="Contribution", value="contribution"),
        ]
        super().__init__(placeholder="Select point type", min_values=1, max_values=1, options=options)
        self.user_id = user_id
        self.action = action
        self.selected_point_type = None

    async def callback(self, interaction: discord.Interaction):
        self.selected_point_type = self.values[0]
        await interaction.response.send_modal(PointsQuantityModal(self.user_id, self.selected_point_type, self.action))

class PointsUserSelectView(View):
    def __init__(self, users, action):
        super().__init__(timeout=60)
        self.action = action
        self.add_item(PointsUserSelect(users, action))

class PointsTypeSelectView(View):
    def __init__(self, user_id, action):
        super().__init__(timeout=60)
        self.action = action
        self.user_id = user_id
        self.add_item(PointsTypeSelect(user_id, action))

class PointsQuantityModal(Modal):
    quantity_input = TextInput(label="Quantity (positive integer)", style=discord.TextStyle.short, required=True)

    def __init__(self, user_id, point_type, action):
        super().__init__(title=f"{action} Points")
        self.user_id = user_id
        self.point_type = point_type
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity_input.value)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("\u274C Quantity must be a positive integer.", ephemeral=True)
            return

        scores = load_scores()
        if self.user_id not in scores:
            scores[self.user_id] = {"insight_points": 0, "contribution_points": 0, "answered_questions": []}

        key = f"{self.point_type}_points"
        current = scores[self.user_id].get(key, 0)

        if self.action == "Add":
            scores[self.user_id][key] = current + qty
        else:  # Remove
            scores[self.user_id][key] = max(0, current - qty)

        save_scores(scores)
        await interaction.response.send_message(f"\u2705 {self.action}ed {qty} {self.point_type} points for <@{self.user_id}>.", ephemeral=True)

@tree.command(name="addpoints", description="Admin-only: Add points to a user")
async def add_points(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("\u274C This command must be used in a server.", ephemeral=True)
        return
    members = [m for m in guild.members if not m.bot]
    await interaction.response.send_message("Select a user to add points:", view=PointsUserSelectView(members, "Add"), ephemeral=True)

@tree.command(name="removepoints", description="Admin-only: Remove points from a user")
async def remove_points(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("\u274C This command must be used in a server.", ephemeral=True)
        return
    members = [m for m in guild.members if not m.bot]
    await interaction.response.send_message("Select a user to remove points:", view=PointsUserSelectView(members, "Remove"), ephemeral=True)

# --- List Questions Command ---
@tree.command(name="questionslist", description="Admin/mod only: List all questions (paginated)")
async def questions_list(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    questions = load_questions()
    if not questions:
        await interaction.response.send_message("\u26A0 No questions found.", ephemeral=True)
        return
    view = QuestionsListView(questions)
    await interaction.response.send_message(view.format_page(), view=view, ephemeral=True)

# --- Remove Question Command ---
@tree.command(name="removequestion", description="Admin/mod only: Remove a question by ID")
async def remove_question(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_messages):
        await interaction.response.send_message("\u274C You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(RemoveQuestionModal(interaction.user))

# --- Question of the Day Commands List ---
@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n"
        "/submitquestion\n"
        "/removequestion\n"
        "/questionslist\n"
        "/score\n"
        "/leaderboard\n"
        "/ranks\n"
        "/addpoints\n"
        "/removepoints",
        ephemeral=True
    )

# --- Submit Question Command ---
@tree.command(name="submitquestion", description="Submit a new question")
async def submit_question(interaction: discord.Interaction):
    await interaction.response.send_modal(SubmitQuestionModal(interaction.user))

# --- Keep alive & run ---
keep_alive()
client.run(TOKEN)
