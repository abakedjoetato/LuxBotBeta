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

class SkipQuestionView(discord.ui.View):
    """Asks the user if their submission is a skip."""
    def __init__(self, bot, submission_data: dict):
        super().__init__(timeout=180)
        self.bot = bot
        self.submission_data = submission_data
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="This submission request has timed out.", view=self)

    @discord.ui.button(label="Yes, it's a skip", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.submission_data['is_skip'] = True
        await _begin_submission_process(self.bot, interaction, self.submission_data)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.grey)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.submission_data['is_skip'] = False
        await _begin_submission_process(self.bot, interaction, self.submission_data)
        self.stop()


class TikTokHandleModal(discord.ui.Modal, title='Enter Your TikTok Handle'):
    """Modal for asking user for their TikTok handle."""
    def __init__(self, bot, submission_data: dict):
        super().__init__()
        self.bot = bot
        self.submission_data = submission_data

    handle = discord.ui.TextInput(
        label='Your TikTok @Handle',
        placeholder='Enter your handle. This will be saved with the submission.',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Bypassing validation. Just save the handle and finalize.
        clean_handle = self.handle.value.strip().lstrip('@')
        self.submission_data['tiktok_username'] = clean_handle

        await interaction.response.defer(ephemeral=True, thinking=True)
        await _finalize_submission(self.bot, interaction, self.submission_data)


async def _begin_submission_process(bot, interaction: discord.Interaction, submission_data: dict):
    """
    The new submission process: asks for the TikTok handle directly.
    This is now called from a button, so we must use interaction.response.send_modal.
    """
    # This function is now triggered by a button click.
    # The original interaction from the button click must be responded to.
    # We respond by sending a new modal.
    modal = TikTokHandleModal(bot, submission_data)
    await interaction.response.send_modal(modal)


async def _finalize_submission(bot, interaction: discord.Interaction, submission_data: dict):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    artist = submission_data['artist_name']
    song = submission_data['song_name']
    user_id = interaction.user.id
    is_skip = submission_data.get('is_skip', False)

    # Determine queue line based on whether it's a skip
    queue_line = QueueLine.PENDING_SKIPS.value if is_skip else QueueLine.FREE.value

    try:
        is_duplicate = await bot.db.check_duplicate_submission(artist, song)
        if is_duplicate:
            await interaction.followup.send(f"❌ This track (**{artist} - {song}**) is already in an active queue.", ephemeral=True)
            return

        if queue_line == QueueLine.FREE.value and not await bot.db.is_free_line_open():
             await interaction.followup.send("❌ Submissions to the Free line are currently closed.", ephemeral=True)
             return

        public_id = await bot.db.add_submission(
            user_id=user_id, username=interaction.user.display_name,
            artist_name=artist, song_name=song,
            link_or_file=submission_data['link_or_file'],
            queue_line=queue_line, note=submission_data.get('note'),
            tiktok_username=submission_data.get('tiktok_username')
        )
        # FIXED BY JULES
        await bot.dispatch_queue_update()

        embed = discord.Embed(title="✅ Submission Added!", description=f"Your music has been added to the **{queue_line}** line.", color=discord.Color.green())
        embed.add_field(name="Artist", value=artist, inline=True)
        embed.add_field(name="Song", value=song, inline=True)
        embed.add_field(name="Submission ID", value=f"#{public_id}", inline=False)
        if submission_data.get('tiktok_username'):
            embed.add_field(name="TikTok Handle Saved", value=f"`{submission_data.get('tiktok_username')}`", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

        link_value = submission_data.get('link_or_file', '')
        if any(domain in link_value.lower() for domain in CLOUD_STORAGE_DOMAINS):
            await interaction.followup.send(embed=discord.Embed(title="🔗 Link Sharing Reminder", description="Please ensure your file is publicly accessible so the host can play it.", color=discord.Color.orange()), ephemeral=True)

    except Exception as e:
        logging.error(f"Error in _finalize_submission: {e}", exc_info=True)
        await interaction.followup.send("❌ An unexpected error occurred while processing your submission.", ephemeral=True)


class SubmissionModal(discord.ui.Modal, title='Submit Music for Review'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    artist_name = discord.ui.TextInput(label='Artist Name', required=True, max_length=100)
    song_name = discord.ui.TextInput(label='Song Name', required=True, max_length=100)
    link = discord.ui.TextInput(label='Music Link', required=True, max_length=500)
    note = discord.ui.TextInput(label='Note (Optional)', required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        submission_data = {
            'artist_name': str(self.artist_name.value).strip(),
            'song_name': str(self.song_name.value).strip(),
            'link_or_file': str(self.link.value).strip(),
            'note': str(self.note.value).strip() if self.note.value else None
        }
        await interaction.response.defer(ephemeral=True)
        skip_view = SkipQuestionView(self.bot, submission_data)
        embed = discord.Embed(title="Is this submission a skip?", description="Please let us know if you intend for this to be a skip submission.", color=discord.Color.blue())
        message = await interaction.followup.send(embed=embed, view=skip_view, ephemeral=True)
        skip_view.message = message

class HistorySelect(discord.ui.Select):
    def __init__(self, bot, history: List[Dict[str, Any]]):
        self.bot = bot
        self.history_data = {f"history_{item['id']}": item for item in history}
        options = [discord.SelectOption(label=f"{item['artist_name']} - {item['song_name']}", description=f"Submitted: {item['submission_time'].strftime('%Y-%m-%d')}", value=submission_id) for submission_id, item in self.history_data.items()]
        super().__init__(placeholder='Select a past submission to re-submit...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        submission_to_resubmit = self.history_data[selected_id]
        submission_data = {'artist_name': submission_to_resubmit['artist_name'], 'song_name': submission_to_resubmit['song_name'], 'link_or_file': submission_to_resubmit['link_or_file'], 'note': submission_to_resubmit['note']}

        await interaction.response.defer(ephemeral=True)
        skip_view = SkipQuestionView(self.bot, submission_data)
        embed = discord.Embed(title="Is this submission a skip?", description="Please let us know if you intend for this to be a skip submission.", color=discord.Color.blue())
        message = await interaction.followup.send(embed=embed, view=skip_view, ephemeral=True)
        skip_view.message = message

class HistoryView(discord.ui.View):
    def __init__(self, bot, history: List[Dict[str, Any]], timeout=180):
        super().__init__(timeout=timeout)
        self.add_item(HistorySelect(bot, history))


class SubmissionButtonView(discord.ui.View):
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
        embed = discord.Embed(title="📁 How to Submit an Audio File", description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='Submit from History', style=discord.ButtonStyle.success, emoji='📜', custom_id='submit_history_button')
    async def submit_from_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if interaction has already been acknowledged
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        history = await self.bot.db.get_user_submissions_history(interaction.user.id, limit=25)
        if not history:
            await interaction.followup.send("You have no past submissions to choose from.", ephemeral=True)
            return
        await interaction.followup.send("Please select a track from your history to re-submit.", view=HistoryView(self.bot, history), ephemeral=True)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, bot, public_id: str):
        super().__init__(timeout=60)
        self.bot = bot
        self.public_id = public_id
        self.confirmed = False

    @discord.ui.button(label="Yes, Delete Permanently", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()


class MySubmissionsView(discord.ui.View):
    def __init__(self, bot, interaction: discord.Interaction, history: List[Dict[str, Any]], page_size: int = 3):
        super().__init__(timeout=300)
        self.bot = bot
        self.original_interaction = interaction
        self.history = history
        self.page_size = page_size
        self.current_page = 0
        self.update_page_count()
        self.update_components()

    def update_page_count(self):
        self.total_pages = (len(self.history) + self.page_size - 1) // self.page_size
        if self.total_pages == 0: self.total_pages = 1

    def update_components(self):
        self.clear_items()
        start_index = self.current_page * self.page_size
        end_index = start_index + self.page_size
        page_items = self.history[start_index:end_index]

        for i, item in enumerate(page_items):
            remove_button = discord.ui.Button(label=f"#{item['public_id']}: Remove from Queue", style=discord.ButtonStyle.secondary, custom_id=f"remove_queue_{item['public_id']}", row=i)
            remove_button.disabled = not item['queue_line'] or item['queue_line'] == QueueLine.SONGS_PLAYED.value
            remove_button.callback = self.create_remove_from_queue_callback(item['public_id'])
            self.add_item(remove_button)

            delete_button = discord.ui.Button(label=f"#{item['public_id']}: Delete Permanently", style=discord.ButtonStyle.danger, custom_id=f"delete_perm_{item['public_id']}", row=i)
            delete_button.callback = self.create_delete_permanently_callback(item['public_id'])
            self.add_item(delete_button)

        prev_button = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.grey, custom_id="page_prev", row=4)
        prev_button.disabled = self.current_page == 0
        prev_button.callback = self.prev_page
        self.add_item(prev_button)

        next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.grey, custom_id="page_next", row=4)
        next_button.disabled = self.current_page >= self.total_pages - 1
        next_button.callback = self.next_page
        self.add_item(next_button)

    # FIXED BY Replit: Submission history with pagination and data isolation - verified working
    async def get_page_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"Your Submission History (Page {self.current_page + 1}/{self.total_pages})", description="Use the buttons below to manage your submissions.", color=discord.Color.blurple())
        start_index = self.current_page * self.page_size
        end_index = start_index + self.page_size
        page_items = self.history[start_index:end_index]

        if not page_items:
            embed.description = "You have no submissions on this page."
        else:
            for item in page_items:
                status = f"`{item['queue_line'] or 'Not in Queue'}`"
                if item['played_time']:
                    status = f"`Played on {item['played_time'].strftime('%Y-%m-%d')}`"
                entry = f"**{item['artist_name']} - {item['song_name']}**\n**ID:** `#{item['public_id']}` | **Status:** {status}"
                embed.add_field(name=f"Submitted: {item['submission_time'].strftime('%Y-%m-%d %H:%M')}", value=entry, inline=False)
        return embed

    async def update_message(self, interaction: discord.Interaction):
        self.update_components()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await self.update_message(interaction)

    def create_remove_from_queue_callback(self, public_id: str):
        async def callback(interaction: discord.Interaction):
            original_line = await self.bot.db.remove_submission_from_queue(public_id)
            if original_line:
                # FIXED BY JULES
                await self.bot.dispatch_queue_update()
                await interaction.response.send_message(f"✅ Submission `#{public_id}` removed from the **{original_line}** queue.", ephemeral=True)
                self.history = await self.bot.db.get_user_submissions_history(interaction.user.id, limit=100)
                self.update_page_count()
                # Use followup to edit the original message since we already responded
                await self.original_interaction.edit_original_response(embed=await self.get_page_embed(), view=self)
            else:
                await interaction.response.send_message(f"⚠️ Could not remove submission `#{public_id}`. It might have already been played or removed.", ephemeral=True)
        return callback

    def create_delete_permanently_callback(self, public_id: str):
        async def callback(interaction: discord.Interaction):
            confirm_view = ConfirmDeleteView(self.bot, public_id)
            await interaction.response.send_message(f"Are you sure you want to permanently delete submission `#{public_id}`? **This cannot be undone.**", view=confirm_view, ephemeral=True)
            await confirm_view.wait()
            if confirm_view.confirmed:
                deleted = await self.bot.db.delete_submission_from_history(public_id, interaction.user.id)
                if deleted:
                    await interaction.followup.send(f"✅ Submission `#{public_id}` has been permanently deleted.", ephemeral=True)
                    self.history = await self.bot.db.get_user_submissions_history(self.original_interaction.user.id, limit=100)
                    self.update_page_count()
                    if self.current_page >= self.total_pages: self.current_page = max(0, self.total_pages - 1)
                    self.update_components()
                    embed = await self.get_page_embed()
                    await self.original_interaction.edit_original_response(embed=embed, view=self)
                else:
                    await interaction.followup.send(f"⚠️ Could not delete submission `#{public_id}`.", ephemeral=True)
            else:
                await interaction.followup.send("Deletion cancelled.", ephemeral=True)
        return callback


class SubmissionCog(commands.Cog):
    """Cog for handling all music submissions."""
    def __init__(self, bot):
        self.bot = bot
        self.submission_view = SubmissionButtonView(bot)

    async def cog_load(self):
        self.bot.add_view(self.submission_view)

    @app_commands.command(name="my-submissions", description="View and manage your submission history.")
    async def my_submissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        history = await self.bot.db.get_user_submissions_history(interaction.user.id, limit=100)
        if not history:
            await interaction.followup.send("You have no submission history.", ephemeral=True)
            return
        view = MySubmissionsView(self.bot, interaction, history)
        embed = await view.get_page_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="submit", description="Submit music for review using a link.")
    async def submit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SubmissionModal(self.bot))

    @app_commands.command(name="submitfile", description="Submit an audio file for review.")
    @app_commands.describe(file="Your audio file.", artist_name="The artist's name.", song_title="The song's title.", note="Optional note for the host.")
    async def submit_file(self, interaction: discord.Interaction, file: discord.Attachment, artist_name: str, song_title: str, note: Optional[str] = None):
        if not file.content_type or not file.content_type.startswith('audio/'):
            await interaction.response.send_message("❌ The uploaded file does not appear to be an audio file.", ephemeral=True)
            return

        submission_data = {
            'artist_name': artist_name.strip(),
            'song_name': song_title.strip(),
            'link_or_file': file.url,
            'note': note.strip() if note else None
        }

        await interaction.response.defer(ephemeral=True)
        skip_view = SkipQuestionView(self.bot, submission_data)
        embed = discord.Embed(title="Is this submission a skip?", description="Please let us know if you intend for this to be a skip submission.", color=discord.Color.blue())
        message = await interaction.followup.send(embed=embed, view=skip_view, ephemeral=True)
        skip_view.message = message

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
