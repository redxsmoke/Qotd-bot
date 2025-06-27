import discord
from discord.ext import tasks
import asyncio
import json
import os
from datetime import datetime, time, timezone, timedelta, date
import random
from discord import app_commands
from discord import ui, Interaction, User, TextStyle, TextInput

# --- Global Variables ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

QUESTIONS_FILE = "submitted_questions.json"
SCORES_FILE = "scores.json"
STREAKS_FILE = "streaks.json"

submitted_questions = []
scores = {}
streaks = {}

used_question_ids = set()
current_riddle = None
current_answer_revealed = False
correct_users = set()
guess_attempts = {}  # user_id -> guesses this riddle
deducted_for_user = set()  # users who lost 1 point this riddle

max_id = 0  # tracks max numeric ID assigned

submission_dates = {}  # user_id -> date of last submission point awarded


# --- Helper functions ---

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return [] if file == QUESTIONS_FILE else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_all_scores():
    save_json(SCORES_FILE, scores)
    save_json(STREAKS_FILE, streaks)

def load_scores():
    global scores
    scores = load_json(SCORES_FILE)
    return scores

def save_scores(scores_dict):
    global scores
    scores = scores_dict
    save_json(SCORES_FILE, scores)

def get_rank(score, streak):
    if scores:
        max_score = max(scores.values())
        if score == max_score and max_score > 0:
            return "🍣 Master Sushi Chef (Top scorer)"
    if streak >= 3:
        return f"🔥 Streak Samurai (Solved {streak} riddles consecutively)"
    if score <= 5:
        return "Sushi Newbie 🍽️"
    elif 6 <= score <= 15:
        return "Maki Novice 🍣"
    elif 16 <= score <= 25:
        return "Sashimi Skilled 🍤"
    elif 26 <= score <= 50:
        return "Brainy Botan 🧠"
    else:
        return "Sushi Einstein 🧪"

def count_unused_questions():
    return len([q for q in submitted_questions if q.get("id") not in used_question_ids])

def pick_next_riddle():
    unused = [q for q in submitted_questions if q.get("id") not in used_question_ids and q.get("id") is not None]
    if not unused:
        used_question_ids.clear()
        unused = [q for q in submitted_questions if q.get("id") is not None]
    riddle = random.choice(unused)
    used_question_ids.add(riddle["id"])
    return riddle

def format_question_text(qdict):
    base = f"@everyone {qdict['id']}. {qdict['question']} ***(Answer will be revealed at 23:00 UTC)***"
    remaining = count_unused_questions()
    if remaining < 5:
        base += "\n\n⚠️ Less than 5 new riddles remain - submit a new riddle with /submitriddle to add it to the queue!"
    return base

def get_next_id():
    global max_id
    max_id += 1
    return str(max_id)


# --- Load data and initialize max_id ---
submitted_questions = load_json(QUESTIONS_FILE)
scores = load_json(SCORES_FILE)
streaks = load_json(STREAKS_FILE)

existing_ids = [int(q["id"]) for q in submitted_questions if q.get("id") and str(q["id"]).isdigit()]
max_id = max(existing_ids) if existing_ids else 0


# --- /listquestions command ---
class QuestionListView(discord.ui.View):
    def __init__(self, user_id, questions, per_page=10):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.questions = questions
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(questions) - 1) // per_page + 1 if questions else 1

    def get_page_content(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_questions = self.questions[start:end]
        lines = [f"📋 Total riddles: {len(self.questions)}"]
        for q in page_questions:
            qid = q.get("id", "NA")
            lines.append(f"{qid}. {q['question']}")
        return "\n".join(lines)

    async def update_message(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ This pagination isn't for you.", ephemeral=True)
            return
        await interaction.response.edit_message(content=self.get_page_content(), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("⛔ Already at the first page.", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("⛔ Already at the last page.", ephemeral=True)

@tree.command(name="listquestions", description="List all submitted riddles")
@app_commands.checks.has_permissions(manage_guild=True)
async def listquestions(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not submitted_questions:
        await interaction.followup.send("📭 No riddles found in the queue.", ephemeral=True)
        return
    view = QuestionListView(interaction.user.id, submitted_questions)
    await interaction.followup.send(content=view.get_page_content(), view=view, ephemeral=True)

@tree.command(name="removequestion", description="Remove a submitted riddle by ID")
@app_commands.checks.has_permissions(manage_guild=True)
async def removequestion(interaction: discord.Interaction):
    class RemoveQuestionModal(discord.ui.Modal, title="Remove a Riddle"):
        question_id = discord.ui.TextInput(
            label="Enter the ID of the riddle to remove",
            placeholder="e.g. 3",
            required=True,
            max_length=10
        )
        async def on_submit(self, modal_interaction: discord.Interaction):
            qid = self.question_id.value.strip()
            idx = next((i for i, q in enumerate(submitted_questions) if q.get("id") == qid), None)
            if idx is None:
                await modal_interaction.response.send_message(f"⚠️ No riddle found with ID `{qid}`.", ephemeral=True)
                return
            removed = submitted_questions.pop(idx)
            save_json(QUESTIONS_FILE, submitted_questions)
            await modal_interaction.response.send_message(f"✅ Removed riddle ID {qid}: \"{removed['question']}\"", ephemeral=True)
    await interaction.response.send_modal(RemoveQuestionModal())


# --- Submit riddle modal ---
class SubmitRiddleModal(discord.ui.Modal, title="Submit a New Riddle"):
    question = discord.ui.TextInput(
        label="Riddle Question",
        style=discord.TextStyle.paragraph,
        placeholder="Enter your riddle question here",
        required=True,
        max_length=1000
    )
    answer = discord.ui.TextInput(
        label="Answer",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the answer here",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        global max_id
        q = self.question.value.strip().replace("\n", " ").replace("\r", " ")
        a = self.answer.value.strip()

        q_normalized = q.lower().replace(" ", "")
        for existing in submitted_questions:
            existing_q = existing["question"].strip().lower().replace(" ", "")
            if existing_q == q_normalized:
                await interaction.response.send_message("⚠️ This riddle has already been submitted. Please try a different one.", ephemeral=True)
                return

        new_id = get_next_id()
        uid = str(interaction.user.id)
        submitted_questions.append({
            "id": new_id,
            "question": q,
            "answer": a,
            "submitter_id": uid
        })
        save_json(QUESTIONS_FILE, submitted_questions)

        # Notify admins and moderators
        ch_id = int(os.getenv("DISCORD_CHANNEL_ID") or 0)
        channel = client.get_channel(ch_id)
        if channel:
            await channel.send("🧠 @𝐈𝐳𝐳𝐲𝐁𝐚𝐧 has submitted a new Riddle of the Day. Use /listquestions to view the question and /removequestion if moderation is needed.")

        # Award point to submitter only once per day
        today = date.today()
        last_award_date = submission_dates.get(uid)
        awarded_point_msg = ""
        if last_award_date != today:
            scores[uid] = scores.get(uid, 0) + 1
            save_json(SCORES_FILE, scores)
            submission_dates[uid] = today
            awarded_point_msg = "\n🏅 You’ve also been awarded **1 point** for your submission!"

        try:
            dm = await interaction.user.create_dm()
            await dm.send(
                "✅ Thanks for submitting a riddle! It is now in the queue.\n"
                "⚠️ You will **not** be able to answer your own riddle when it is posted."
                + awarded_point_msg
            )
        except discord.Forbidden:
            pass

        await interaction.response.send_message("✅ Your riddle has been submitted and added to the queue! Check your DMs.", ephemeral=True)


@tree.command(name="submitriddle", description="Submit a new riddle via a form")
async def submitriddle(interaction: discord.Interaction):
    await interaction.response.send_modal(SubmitRiddleModal())


# --- New Modal for Add/Remove Points ---
class PointsModal(ui.Modal):
    def __init__(self, action: str, target_user: User):
        super().__init__(title=f"{action} Points for {target_user.display_name}")
        self.action = action
        self.target_user = target_user

        self.point_type = TextInput(
            label="Point Type (insight or contribution)",
            style=TextStyle.short,
            placeholder="insight or contribution",
            required=True,
            max_length=12
        )
        self.quantity = TextInput(
            label="Quantity (positive integer)",
            style=TextStyle.short,
            placeholder="1",
            required=True,
            max_length=5
        )

        self.add_item(self.point_type)
        self.add_item(self.quantity)

    async def on_submit(self, interaction: Interaction):
        point_type = self.point_type.value.lower()
        quantity_str = self.quantity.value

        if point_type not in ("insight", "contribution"):
            await interaction.response.send_message("❌ Invalid point type. Use 'insight' or 'contribution'.", ephemeral=True)
            return

        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Quantity must be a positive integer.", ephemeral=True)
            return

        # Load or initialize scores structure as dict of dicts
        # Format: scores = {user_id: {"insight_points": int, "contribution_points": int, "answered_questions": []}, ...}
        scores_dict = load_json(SCORES_FILE)

        uid = str(self.target_user.id)

        if uid not in scores_dict:
            scores_dict[uid] = {
                "insight_points": 0,
                "contribution_points": 0,
                "answered_questions": []
            }

        key = f"{point_type}_points"
        current_points = scores_dict[uid].get(key, 0)

        if self.action == "Add":
            scores_dict[uid][key] = current_points + quantity
        else:
            scores_dict[uid][key] = max(0, current_points - quantity)

        save_json(SCORES_FILE, scores_dict)

        await interaction.response.send_message(
            f"✅ {self.action}ed {quantity} {point_type} point(s) for {self.target_user.mention}.",
            ephemeral=True
        )

@tree.command(name="addpoints", description="Add points to a user")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(user="The user to award points to")
async def addpoints(interaction: discord.Interaction, user: discord.User):
    modal = PointsModal("Add", user)
    await interaction.response.send_modal(modal)

@tree.command(name="removepoints", description="Remove points from a user")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(user="The user to remove points from")
async def removepoints(interaction: discord.Interaction, user: discord.User):
    modal = PointsModal("Remove", user)
    await interaction.response.send_modal(modal)


# --- Score and leaderboard commands ---

@tree.command(name="score", description="View your score and rank")
async def score(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    sv = 0
    st = streaks.get(uid, 0)

    # Handle older flat score int or new dict structure
    user_score = scores.get(uid, 0)
    if isinstance(user_score, dict):
        sv = user_score.get("insight_points", 0) + user_score.get("contribution_points", 0)
    else:
        sv = user_score

    await interaction.response.send_message(
        f"📊 {interaction.user.display_name}'s score: **{sv}**, 🔥 Streak: {st}\n🏅 {get_rank(sv, st)}",
        ephemeral=True
    )


# --- Updated /leaderboard command with pagination ---
class LeaderboardView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        # Sort scores by sum of insight+contribution points if dict, else use legacy int
        def score_val(item):
            uid, val = item
            if isinstance(val, dict):
                return val.get("insight_points", 0) + val.get("contribution_points", 0)
            return val

        self.sorted_scores = sorted(scores.items(), key=score_val, reverse=True)
        self.total_pages = max((len(self.sorted_scores) - 1) // 10 + 1, 1)
        self.current_page = 0

    async def format_page(self):
        start = self.current_page * 10
        end = start + 10
        embed = discord.Embed(
            title=f"🏆 Riddle Leaderboard ({self.current_page + 1}/{self.total_pages})",
            color=discord.Color.gold()
        )
        for i, (uid, val) in enumerate(self.sorted_scores[start:end], start=start + 1):
            try:
                user = client.get_user(int(uid)) or await client.fetch_user(int(uid))
                name = user.display_name
            except:
                name = "Unknown"
            st = streaks.get(uid, 0)
            if isinstance(val, dict):
                total_points = val.get("insight_points", 0) + val.get("contribution_points", 0)
            else:
                total_points = val
            embed.add_field(name=f"{i}. {name}",
                            value=f"Score: {total_points} | Streak: {st}\nRank: {get_rank(total_points, st)}",
                            inline=False)
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ This leaderboard isn't for you.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            embed = await self.format_page()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("⛔ Already at the first page.", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ This leaderboard isn't for you.", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            embed = await self.format_page()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("⛔ Already at the last page.", ephemeral=True)


@tree.command(name="leaderboard", description="Show the top solvers")
async def leaderboard(interaction: discord.Interaction):
    if not scores:
        await interaction.response.send_message("📭 No scores available yet.", ephemeral=True)
        return
    view = LeaderboardView(interaction.user.id)
    embed = await view.format_page()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- on_message event and other logic below remain unchanged ---

@client.event
async def on_message(message):
    if message.author.bot:
        return

    ch_id = int(os.getenv("DISCORD_CHANNEL_ID") or 0)
    if message.channel.id != ch_id:
        return

    global correct_users, guess_attempts, deducted_for_user, current_riddle

    user_id = str(message.author.id)
    content = message.content.strip()

    if not current_riddle or current_answer_revealed:
        return

    # Block submitter from answering their own riddle
    if current_riddle.get("submitter_id") == user_id:
        try: await message.delete()
        except: pass
        await message.channel.send(f"⛔ You submitted this riddle and cannot answer it, {message.author.mention}.", delete_after=5)
        return

    if user_id in correct_users:
        # User already answered correctly; ignore guesses and do not deduct points
        return

    guesses = guess_attempts.get(user_id, 0)
    if guesses >= 5:
        await message.channel.send(f"⛔ {message.author.mention}, you have no guesses left for this riddle.", delete_after=5)
        try: await message.delete()
        except: pass
        return

    if content.lower() == current_riddle.get("answer", "").lower():
        # Correct guess
        correct_users.add(user_id)
        # Award point
        sc = scores.get(user_id, {"insight_points": 0, "contribution_points": 0, "answered_questions": []})
        if isinstance(sc, dict):
            sc.setdefault("answered_questions", [])
            if current_riddle["id"] not in sc["answered_questions"]:
                sc["answered_questions"].append(current_riddle["id"])
                # sum points
                insight = sc.get("insight_points", 0)
                contrib = sc.get("contribution_points", 0)
                sc["insight_points"] = insight
                sc["contribution_points"] = contrib
                scores[user_id] = sc
                # Add 1 point to contribution_points by default
                sc["contribution_points"] += 1
                streaks[user_id] = streaks.get(user_id, 0) + 1
                save_all_scores()
        else:
            # legacy int
            scores[user_id] = scores.get(user_id, 0) + 1
            streaks[user_id] = streaks.get(user_id, 0) + 1
            save_all_scores()

        await message.channel.send(f"🎉 {message.author.mention} got it right! +1 point.\n🔥 Current streak: {streaks.get(user_id, 0)}")
        try:
            await message.delete()
        except:
            pass
        return

    # Wrong guess
    guess_attempts[user_id] = guesses + 1
    # Deduct point only once per riddle if no correct guess
    if guess_attempts[user_id] >= 5 and user_id not in deducted_for_user:
        deducted_for_user.add(user_id)
        # Deduct point from contribution points or legacy int
        sc = scores.get(user_id, {"insight_points": 0, "contribution_points": 0})
        if isinstance(sc, dict):
            cur_points = sc.get("contribution_points", 0)
            sc["contribution_points"] = max(0, cur_points - 1)
            scores[user_id] = sc
            save_all_scores()
        else:
            scores[user_id] = max(0, scores.get(user_id, 0) - 1)
            save_all_scores()

    # Show countdown to answer reveal
    reveal_time = datetime.now(timezone.utc).replace(hour=23, minute=0, second=0, microsecond=0)
    now = datetime.now(timezone.utc)
    delta = reveal_time - now
    if delta.total_seconds() < 0:
        delta = timedelta(hours=0)
    minutes = int(delta.total_seconds() // 60)
    seconds = int(delta.total_seconds() % 60)

    await message.channel.send(
        f"⏳ {message.author.mention}, answer reveal in {minutes}m {seconds}s.",
        delete_after=5
    )
    try:
        await message.delete()
    except:
        pass


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user} (ID: {client.user.id})")

# --- Bot token from env ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if TOKEN is None:
    print("❌ Missing DISCORD_BOT_TOKEN environment variable!")
else:
    client.run(TOKEN)
