"""
Submission Cog - Handles user submissions via Discord UI Modal and history,
including the TikTok handle linking flow.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Dict, Any

from database import QueueLine

# List of common cloud storage domains to check for public link reminders.
CLOUD_STORAGE_DOMAINS = [
    "drive.google.com", "dropbox.com", "onedrive.live.com", "1drv.ms",
    "icloud.com", "box.com", "pcloud.com", "mega.nz", "mega.io", "sync.com",
    "icedrive.net", "koofr.net", "koofr.eu", "terabox.com", "mediafire.com",
    "s3.amazonaws.com", "degoo.com", "disk.yandex.", "tresorit.com", "nordlocker.com"
]

class TikTokHandleModal(discord.ui.Modal, title='Link Your TikTok Handle'):
    """Modal for asking user for their TikTok handle."""
    def __init__(self, bot, submission_data: dict):
        super().__init__()
        self.bot = bot
        self.submission_data = submission_data

    handle = discord.ui.TextInput(
        label='Your TikTok @Handle',
        placeholder='Enter your handle to get points for interactions',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        clean_handle = self.handle.value.strip().lstrip('@')

        # Link the account and handle the response tuple (success, message)
        success, message = await self.bot.db.link_tiktok_account(interaction.user.id, clean_handle)

        if not success:
            # If linking failed, show the error message from the DB and stop.
            await interaction.followup.send(f"❌ **Linking Failed:** {message}", ephemeral=True)
            return

        # If linking succeeded, show the success message and proceed with the submission.
        await interaction.followup.send(f"✅ {message} Your submission will now proceed.", ephemeral=True)
        await _finalize_submission(self.bot, interaction, self.submission_data)

class HandlePromptView(discord.ui.View):
    """A view that prompts a user to link their TikTok handle before submitting."""
    def __init__(self, bot, submission_data: dict):
        super().__init__(timeout=180)
        self.bot = bot
        self.submission_data = submission_data
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Link TikTok Account", style=discord.ButtonStyle.success, emoji="🔗")
    async def link_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Opens the modal to link a TikTok account."""
        modal = TikTokHandleModal(self.bot, self.submission_data)
        await interaction.response.send_modal(modal)
        self.stop() # Stop this view once the modal is shown

    @discord.ui.button(label="Submit Without Linking", style=discord.ButtonStyle.grey)
    async def submit_anyway(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Proceeds with submission without linking, with a warning."""
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            "⚠️ **Warning:** You are submitting without a linked TikTok account. "
            "You will **not** receive engagement points for likes, comments, shares, or gifts on TikTok LIVE.",
            ephemeral=True
        )
        await _finalize_submission(self.bot, interaction, self.submission_data)
        self.stop()

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="This submission request has timed out.", view=self)


async def _begin_submission_process(bot, interaction: discord.Interaction, submission_data: dict):
    """
    Checks if a user has a linked TikTok handle and either finalizes the submission
    or prompts them to link their account.
    """
    # This function should be called after a defer, but we check just in case.
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    linked_handles = await bot.db.get_linked_tiktok_handles(interaction.user.id)

    if linked_handles:
        # User already has a handle, proceed directly to finalization
        await _finalize_submission(bot, interaction, submission_data)
    else:
        # User does not have a handle, prompt them.
        view = HandlePromptView(bot, submission_data)
        embed = discord.Embed(
            title="🔗 Link Your TikTok Account?",
            description=(
                "To get points for your engagement on TikTok LIVE (likes, shares, gifts, etc.), "
                "you need to link your TikTok handle to your Discord account.\n\n"
                "**This is highly recommended!**"
            ),
            color=discord.Color.blue()
        )
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = message


async def _finalize_submission(bot, interaction: discord.Interaction, submission_data: dict):
    """
    The final step of the submission process. Checks for duplicates, adds to the DB, and sends confirmations.
    """
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    artist = submission_data['artist_name']
    song = submission_data['song_name']
    user_id = interaction.user.id
    queue_line = QueueLine.FREE.value # All submissions now start in the Free queue

    try:
        is_duplicate = await bot.db.check_duplicate_submission(artist, song)
        if is_duplicate:
            await interaction.followup.send(f"❌ This track (**{artist} - {song}**) is already in the active queue.", ephemeral=True)
            return

        if not await bot.db.is_free_line_open():
             await interaction.followup.send("❌ Submissions to the Free line are currently closed.", ephemeral=True)
             return

        public_id = await bot.db.add_submission(
            user_id=user_id, username=interaction.user.display_name,
            artist_name=artist, song_name=song,
            link_or_file=submission_data['link_or_file'],
            queue_line=queue_line, note=submission_data.get('note')
        )

        embed = discord.Embed(title="✅ Submission Added!", description=f"Your music has been added to the **{queue_line}** line.", color=discord.Color.green())
        embed.add_field(name="Artist", value=artist, inline=True)
        embed.add_field(name="Song", value=song, inline=True)
        embed.add_field(name="Submission ID", value=f"#{public_id}", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        link_value = submission_data.get('link_or_file', '')
        if any(domain in link_value.lower() for domain in CLOUD_STORAGE_DOMAINS):
            await interaction.followup.send(embed=discord.Embed(title="🔗 Link Sharing Reminder", description="Please ensure your file is publicly accessible so the host can play it.", color=discord.Color.orange()), ephemeral=True)

    except Exception as e:
        logging.error(f"Error in _finalize_submission: {e}", exc_info=True)
        await interaction.followup.send("❌ An unexpected error occurred while processing your submission.", ephemeral=True)


class SubmissionModal(discord.ui.Modal, title='Submit Music for Review'):
    """Modal form for music submissions via link."""
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    artist_name = discord.ui.TextInput(label='Artist Name', required=True, max_length=100)
    song_name = discord.ui.TextInput(label='Song Name', required=True, max_length=100)
    link = discord.ui.TextInput(label='Music Link', required=True, max_length=500)
    note = discord.ui.TextInput(label='Note (Optional)', required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        submission_data = {'artist_name': str(self.artist_name.value).strip(), 'song_name': str(self.song_name.value).strip(), 'link_or_file': str(self.link.value).strip(), 'note': str(self.note.value).strip() if self.note.value else None}
        await _begin_submission_process(self.bot, interaction, submission_data)

# ... (HistorySelect and HistoryView remain the same) ...
class HistorySelect(discord.ui.Select):
    """A select menu for choosing a song from submission history."""
    def __init__(self, bot, history: List[Dict[str, Any]]):
        self.bot = bot
        self.history_data = {f"history_{item['id']}": item for item in history}
        options = [discord.SelectOption(label=f"{item['artist_name']} - {item['song_name']}", description=f"Submitted: {item['submission_time'].strftime('%Y-%m-%d')}", value=submission_id) for submission_id, item in self.history_data.items()]
        super().__init__(placeholder='Select a past submission to re-submit...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        submission_to_resubmit = self.history_data[selected_id]
        submission_data = {'artist_name': submission_to_resubmit['artist_name'], 'song_name': submission_to_resubmit['song_name'], 'link_or_file': submission_to_resubmit['link_or_file'], 'note': submission_to_resubmit['note']}
        await _begin_submission_process(self.bot, interaction, submission_data)

class HistoryView(discord.ui.View):
    """A view that contains the history select menu."""
    def __init__(self, bot, history: List[Dict[str, Any]], timeout=180):
        super().__init__(timeout=timeout)
        self.add_item(HistorySelect(bot, history))


class SubmissionButtonView(discord.ui.View):
    """Persistent view with submission buttons."""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Submit Link', style=discord.ButtonStyle.primary, emoji='🔗', custom_id='submit_link_button')
    async def submit_link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmissionModal(self.bot))

    @discord.ui.button(label='Submit File Instructions', style=discord.ButtonStyle.secondary, emoji='📁', custom_id='submit_file_button')
    async def submit_file_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        description = (
            "Type `/` then `submitfile` in the chat and hit enter.\n"
            "Attach your audio file `.mp3`, `.m4a`, etc. (No `.wav` files).\n"
            "Fill in the `artist_name` and `song_title` fields and optional note.\n"
            "Hit send!\n"
            "Answer whether you intend to send a monetary skip - Gift, PP, CA.\n"
            "If you haven't linked your TikTok handle please do so, you won't be eligible for interaction-based track boosting if you don't link your TikTok @handle(s) to your Discord account."
        )
        embed = discord.Embed(
            title="📁 How to Submit an Audio File",
            description=description,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='Submit from History', style=discord.ButtonStyle.success, emoji='📜', custom_id='submit_history_button')
    async def submit_from_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        history = await self.bot.db.get_user_submissions_history(interaction.user.id, limit=25)
        if not history:
            await interaction.followup.send("You have no past submissions to choose from.", ephemeral=True)
            return
        await interaction.followup.send("Please select a track from your history to re-submit.", view=HistoryView(self.bot, history), ephemeral=True)


class RemoveSubmissionSelect(discord.ui.Select):
    """A select menu for choosing a submission to remove from the queue."""
    def __init__(self, bot, submissions: List[Dict[str, Any]]):
        self.bot = bot
        options = [
            discord.SelectOption(
                label=f"#{item['public_id']} | {item['artist_name']}",
                description=f"{item['song_name']}",
                value=item['public_id']
            ) for item in submissions[:25] # Select menu can have max 25 options
        ]
        super().__init__(placeholder="Select a submission to remove from the active queue...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        public_id = self.values[0]
        original_line = await self.bot.db.remove_submission_from_queue(public_id)

        if original_line:
            await interaction.response.send_message(f"✅ Successfully removed submission `#{public_id}` from the **{original_line}** queue.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Could not remove submission `#{public_id}`. It might have already been played or removed.", ephemeral=True)

        for item in self.view.children:
            item.disabled = True
        await interaction.edit_original_response(view=self.view)


class SubmissionCog(commands.Cog):
    """Cog for handling all music submissions."""
    def __init__(self, bot):
        self.bot = bot
        self.submission_view = SubmissionButtonView(bot)

    async def cog_load(self):
        self.bot.add_view(self.submission_view)

    @app_commands.command(name="my-submissions", description="View your submission history and manage your queued songs.")
    async def my_submissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        history = await self.bot.db.get_user_submissions_history(interaction.user.id, limit=100)

        if not history:
            await interaction.followup.send("You have no submission history.", ephemeral=True)
            return

        embed = discord.Embed(title="Your Submission History", color=discord.Color.blurple())

        lines = []
        removable_submissions = []
        for item in history:
            status = f"`{item['queue_line'] or 'Not in Queue'}`"
            if item['played_time']:
                status = f"`Played`"

            line = f"**{item['artist_name']} - {item['song_name']}** (`#{item['public_id']}`) - Status: {status}"
            lines.append(line)

            if item['queue_line'] and item['queue_line'] not in [QueueLine.SONGS_PLAYED.value]:
                 removable_submissions.append(item)

        embed.description = "\n".join(lines[:15])
        if len(lines) > 15:
            embed.set_footer(text=f"...and {len(lines) - 15} more.")

        if removable_submissions:
            view = discord.ui.View(timeout=180)
            view.add_item(RemoveSubmissionSelect(self.bot, removable_submissions))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="submit", description="Submit music for review using a link.")
    async def submit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SubmissionModal(self.bot))

    @app_commands.command(name="submitfile", description="Submit an audio file for review.")
    @app_commands.describe(file="Your audio file.", artist_name="The artist's name.", song_title="The song's title.", note="Optional note for the host.")
    async def submit_file(self, interaction: discord.Interaction, file: discord.Attachment, artist_name: str, song_title: str, note: Optional[str] = None):
        if not file.content_type or not file.content_type.startswith('audio/'):
            await interaction.response.send_message("❌ The uploaded file does not appear to be an audio file.", ephemeral=True)
            return
        submission_data = {'artist_name': artist_name.strip(), 'song_name': song_title.strip(), 'link_or_file': file.url, 'note': note.strip() if note else None}
        await _begin_submission_process(self.bot, interaction, submission_data)

    @app_commands.command(name="setupsubmissionportal", description="[ADMIN] Setup submission buttons in the current channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_submission_portal(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎵 Music Submission Portal", description="Use the buttons below to submit your music.", color=discord.Color.dark_purple())
        embed.add_field(name="🔗 Submit a Link", value="Click the `Submit Link` button to open a form where you can paste a URL.", inline=False)
        file_submission_instructions = (
            "Type `/` then `submitfile` in the chat and hit enter.\n"
            "Attach your audio file `.mp3`, `.m4a`, etc. (No `.wav` files).\n"
            "Fill in the `artist_name` and `song_title` fields and optional note.\n"
            "Hit send!\n"
            "Answer whether you intend to send a monetary skip - Gift, PP, CA.\n"
            "If you haven't linked your TikTok handle please do so, you won't be eligible for interaction-based track boosting if you don't link your TikTok @handle(s) to your Discord account."
        )
        embed.add_field(name="📁 Submit a File", value=file_submission_instructions, inline=False)
        embed.add_field(name="📜 Submit from History", value="Click `Submit from History` to quickly re-submit one of your previously played tracks.", inline=False)
        await interaction.response.send_message(embed=embed, view=SubmissionButtonView(self.bot))

async def setup(bot):
    await bot.add_cog(SubmissionCog(bot))