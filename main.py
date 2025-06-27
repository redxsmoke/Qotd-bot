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

# Slash command: /questionofthedaycommands
@tree.command(name="questionofthedaycommands", description="List available question commands")
async def question_commands(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Available commands:\n"
        "/submitquestion\n/removequestion\n/questionlist\n/score\n/leaderboard\n/ranks",
        ephemeral=True
    )

# Slash command: /ranks
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

# Slash command: /submitquestion
class SubmitQuestionModal(Modal, title="Submit a Question"):
    question_input = TextInput(label="Your question", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        question_text = self.question_input.value.strip()
        questions = load_questions()

        existing_ids = []
        for q in questions:
            try:
                existing_ids.append(int(q.get("id")))
            except (TypeError, ValueError):
                pass
        next_id = str(max(existing_ids) + 1) if existing_ids else "1"

        questions.append({"id": next_id, "question": question_text, "submitter": str(self.user.id)})
        save_questions(questions)

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

# Slash command: /questionlist
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

# Slash command: /removequestion
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

# Slash command: /score
@tree.command(name="score", description="Show your score and rank")
async def score(interaction: discord.Interaction):
    scores = load_scores()
    uid = str(interaction.user.id)
    score = scores.get(uid, {"insight_points": 0, "contribution_points": 0})
    insight = score.get("insight_points", 0)
    contrib = score.get("contribution_points", 0)
    total = insight + contrib
    await interaction.response.send_message(f"⭐ Insight: {insight}\n💡 Contribution: {contrib}\n🏆 Rank: {get_rank(total)}", ephemeral=True)

# Slash command: /leaderboard (already implemented with category select)
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
