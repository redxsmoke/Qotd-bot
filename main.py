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

def update_score(user_id: str, point_type: str, qty: int, qid=None):
    scores = load_scores()
    scores.setdefault(user_id, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
    if point_type == "insight":
        if qid is not None:
            if qid in scores[user_id]["answered_questions"]:
                return False  # Already got point for this question
            scores[user_id]["answered_questions"].append(qid)
        scores[user_id]["insight_points"] += qty
    elif point_type == "contribution":
        scores[user_id]["contribution_points"] += qty
    save_scores(scores)
    return True

def get_rank_emoji(points_total: int):
    if points_total >= 100:
        return "🏆"  # top rank
    elif points_total >= 50:
        return "🥇"
    elif points_total >= 25:
        return "🥈"
    elif points_total >= 10:
        return "🥉"
    else:
        return "🔰"

# --- Post Question with Buttons ---
async def post_question():
    q = get_today_question()
    if not q:
        return
    question = q["question"]
    submitter = q.get("submitter")
    submitter_text = f"🧠 Question submitted by <@{submitter}>" if submitter else "🤖 Question submitted by the Question of the Day Bot"
    is_multiple_choice = "answers" in q and isinstance(q["answers"], list) and len(q["answers"]) >= 2

    class QuestionView(View):
        def __init__(self, qid, multiple_choice):
            super().__init__(timeout=None)
            self.qid = qid
            self.multiple_choice = multiple_choice

            if self.multiple_choice:
                # Add buttons for each choice with custom_id as the choice text
                for idx, choice in enumerate(q["answers"], 1):
                    self.add_item(
                        Button(label=f"{choice}", style=discord.ButtonStyle.primary, custom_id=f"mc_{self.qid}_{idx}")
                    )
            else:
                self.add_item(
                    Button(label="Answer Freely 🧠 (+1 Insight)", style=discord.ButtonStyle.success, custom_id="freely")
                )
                self.add_item(
                    Button(label="Answer Anonymously (0 Insight)", style=discord.ButtonStyle.secondary, custom_id="anon")
                )

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # Ensure this View is only used in the right context (optional)
            return True

        async def on_timeout(self):
            # Could disable buttons on timeout if desired
            pass

        @discord.ui.button(label="Answer Freely 🧠 (+1 Insight)", style=discord.ButtonStyle.success, custom_id="freely")
        async def free_button(self, interaction: discord.Interaction, button: Button):
            if self.multiple_choice:
                await interaction.response.send_message("This question requires selecting one of the multiple choices.", ephemeral=True)
                return
            await interaction.response.send_modal(AnswerModal(qid=self.qid, user=interaction.user))

        @discord.ui.button(label="Answer Anonymously (0 Insight)", style=discord.ButtonStyle.secondary, custom_id="anon")
        async def anon_button(self, interaction: discord.Interaction, button: Button):
            if self.multiple_choice:
                await interaction.response.send_message("This question requires selecting one of the multiple choices.", ephemeral=True)
                return
            await interaction.response.send_message("Please reply here with your anonymous answer (this will be relayed anonymously).", ephemeral=True)

        async def on_button_click(self, interaction: discord.Interaction):
            # Handle multiple choice answers
            custom_id = interaction.data["custom_id"]
            if custom_id.startswith(f"mc_{self.qid}_"):
                choice_index = int(custom_id.split("_")[-1]) - 1
                selected_answer = q["answers"][choice_index]
                user_id = str(interaction.user.id)

                # Award insight point if not already awarded for this qid
                scores = load_scores()
                scores.setdefault(user_id, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
                if self.qid not in scores[user_id]["answered_questions"]:
                    scores[user_id]["insight_points"] += 1
                    scores[user_id]["answered_questions"].append(self.qid)
                    save_scores(scores)
                    msg = f"🗣️ Answer from <@{user_id}>: {selected_answer}\n\n✨ +1 Insight Point!"
                else:
                    msg = f"🗣️ Answer from <@{user_id}>: {selected_answer}\n\n(You've already earned a point for this question!)"

                await interaction.response.send_message(msg)

    class AnswerModal(Modal, title="Answer the Question"):
        answer = TextInput(label="Your answer", style=discord.TextStyle.paragraph)

        def __init__(self, qid, user):
            super().__init__()
            self.qid = qid
            self.user = user

        async def on_submit(self, interaction: discord.Interaction):
            user_id = str(self.user.id)
            added = update_score(user_id, "insight", 1, qid=self.qid)
            if added:
                msg = f"🗣️ Answer from <@{user_id}>:\n{self.answer}\n\n✨ +1 Insight Point!"
            else:
                msg = f"🗣️ Answer from <@{user_id}>:\n{self.answer}\n\n(You've already earned a point for this question!)"
            await interaction.response.send_message(msg)

    channel = client.get_channel(CHANNEL_ID)
    view = QuestionView(q["id"], is_multiple_choice)
    # For multiple choice questions, remove the two default buttons
    if is_multiple_choice:
        # Remove free and anon buttons if they exist (they won't be added here because of constructor logic)
        # So no action needed here
        pass

    await channel.send(f"@everyone {question}\n\n{submitter_text}", view=view)

# --- Events & Loops ---
@client.event
async def on_ready():
    print("✅ Discord bot connected")
    await tree.sync()
    purge_channel_before_post.start()
    post_daily_message.start()
    await post_question()  # Post immediately for testing

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
        await admin_channel.send(f"📩 Anonymous answer:\n{message.content}")
        await message.channel.send("✅ Received anonymously.")

# --- Slash Commands ---
@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    cmds = (
        "/submitquestion - Submit a question (plain or multiple choice)\n"
        "/removequestion - Remove a question by ID (admin only)\n"
        "/questionqueue - View question queue (admin only)\n"
        "/score - View your Insight & Contribution points\n"
        "/leaderboard - View the leaderboard\n"
        "/addpoints - Add points to a user (admin only)\n"
        "/removepoints - Remove points from a user (admin only)"
    )
    await interaction.response.send_message(f"Available commands:\n{cmds}", ephemeral=True)

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

    # Award contribution points for submitting question
    update_score(str(interaction.user.id), "contribution", 1)

    await interaction.response.send_message(f"✅ Question submitted (ID: {new_id}) — +1 Contribution Point!", ephemeral=True)

@tree.command(name="removequestion", description="Remove a question by ID (admin/mod only)")
@app_commands.describe(id="ID of the question to remove")
async def remove_question(interaction: discord.Interaction, id: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
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
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    questions = load_questions()
    if not questions:
        await interaction.response.send_message("No questions in queue.", ephemeral=True)
        return

    lines = [f"`{q['id']}`: {q['question'][:80]}{'...' if len(q['question']) > 80 else ''}" for q in questions]
    message = "📋 Question Queue:\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)

@tree.command(name="score", description="View your Insight and Contribution points")
async def score(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    scores = load_scores().get(uid, {"insight_points": 0, "contribution_points": 0})
    await interaction.response.send_message(
        f"🧠 Insight Points: {scores['insight_points']}\n🛠️ Contribution Points: {scores['contribution_points']}",
        ephemeral=True)

@tree.command(name="leaderboard", description="See the leaderboard")
@app_commands.describe(category="Sort by: all, insight, contribution")
@app_commands.choices(category=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Insight", value="insight"),
    app_commands.Choice(name="Contribution", value="contribution")
])
async def leaderboard(interaction: discord.Interaction, category: app_commands.Choice[str]):
    scores = load_scores()
    users = []
    for uid, data in scores.items():
        total = data.get("insight_points", 0) + data.get("contribution_points", 0)
        users.append({
            "id": uid,
            "insight": data.get("insight_points", 0),
            "contribution": data.get("contribution_points", 0),
            "total": total
        })

    key = "total" if category.value == "all" else ("insight" if category.value == "insight" else "contribution")
    sorted_users = sorted(users, key=itemgetter(key), reverse=True)

    pages = [sorted_users[i:i+10] for i in range(0, len(sorted_users), 10)]

    class LeaderboardView(View):
        def __init__(self):
            super().__init__()
            self.page = 0

        async def update(self, interaction):
            lines = []
            for u in pages[self.page]:
                points_total = u["total"]
                emoji = get_rank_emoji(points_total)
                lines.append(f"{emoji} <@{u['id']}> — 🧠 {u['insight']} Insight | 🛠️ {u['contribution']} Contribution")

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
        lines = []
        for u in pages[0]:
            points_total = u["total"]
            emoji = get_rank_emoji(points_total)
            lines.append(f"{emoji} <@{u['id']}> — 🧠 {u['insight']} Insight | 🛠️ {u['contribution']} Contribution")

        await interaction.response.send_message(f"**Leaderboard - {category.name}**\n\n" + "\n".join(lines), view=LeaderboardView(), ephemeral=False)

# Admin commands to add/remove points
class AddRemovePointModal(Modal):
    def __init__(self, action: str):
        super().__init__(title=f"{action} Points")
        self.action = action

        self.point_type = discord.ui.TextInput(
            label="Point type (insight/contribution)",
            placeholder="insight or contribution",
            required=True,
            max_length=20
        )
        self.user_id = discord.ui.TextInput(
            label="User ID (mention user and copy ID or type user ID)",
            placeholder="User ID",
            required=True,
            max_length=30
        )
        self.quantity = discord.ui.TextInput(
            label="Quantity (positive integer)",
            placeholder="e.g., 1",
            required=True,
            max_length=10
        )

        self.add_item(self.point_type)
        self.add_item(self.user_id)
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        point_type = self.point_type.value.lower()
        if point_type not in ("insight", "contribution"):
            await interaction.response.send_message("❌ Invalid point type. Must be 'insight' or 'contribution'.", ephemeral=True)
            return

        try:
            user_id = self.user_id.value.strip().replace("<@", "").replace(">", "")
            qty = int(self.quantity.value)
            if qty <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Quantity must be a positive integer and User ID valid.", ephemeral=True)
            return

        scores = load_scores()
        scores.setdefault(user_id, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})

        if self.action == "Add":
            scores[user_id][f"{point_type}_points"] += qty
            await interaction.response.send_message(f"✅ Added {qty} {point_type} point(s) to <@{user_id}>.", ephemeral=True)
        else:
            scores[user_id][f"{point_type}_points"] = max(0, scores[user_id][f"{point_type}_points"] - qty)
            await interaction.response.send_message(f"✅ Removed {qty} {point_type} point(s) from <@{user_id}>.", ephemeral=True)

        save_scores(scores)

@tree.command(name="addpoints", description="Add points to a user (admin only)")
async def add_points(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(AddRemovePointModal("Add"))

@tree.command(name="removepoints", description="Remove points from a user (admin only)")
async def remove_points(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return
    await interaction.response.send_modal(AddRemovePointModal("Remove"))

# Keep alive & run
keep_alive()
client.run(TOKEN)
