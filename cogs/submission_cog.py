"""
Submission Cog - Handles user submissions via Discord UI Modal
"""

import discord
from discord.ext import commands
from discord import app_commands
import uuid
from typing import Optional
from database import QueueLine
from .checks import is_admin
from s3_utils import S3Client  # Import the S3Client

# List of common cloud storage domains to check for public link reminders.
CLOUD_STORAGE_DOMAINS = [
    "drive.google.com", "dropbox.com", "onedrive.live.com", "1drv.ms",
    "icloud.com", "box.com", "pcloud.com", "mega.nz", "mega.io", "sync.com",
    "icedrive.net", "koofr.net", "koofr.eu", "terabox.com", "mediafire.com",
    "s3.amazonaws.com", "degoo.com", "disk.yandex.", "tresorit.com", "nordlocker.com"
]


class TikTokHandleModal(discord.ui.Modal, title='Add Your TikTok Handle'):
    """Modal for asking user for their TikTok handle."""
    tiktok_username = discord.ui.TextInput(
        label='TikTok @Handle',
        placeholder='Enter your @handle for engagement rewards...',
        required=True,
        max_length=100
    )

    def __init__(self, bot, view, is_skip: bool):
        super().__init__()
        self.bot = bot
        self.view = view
        self.is_skip = is_skip

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        handle = self.tiktok_username.value.strip()

        if not handle or ' ' in handle or len(handle) > 100:
            await interaction.followup.send("❌ Invalid TikTok username format.", ephemeral=True)
            return

        if handle.startswith('@'):
            handle = handle[1:]

        try:
            await self.bot.db.set_tiktok_handle(interaction.user.id, handle)
            await self.bot.db.update_user_submissions_tiktok_handle(interaction.user.id, handle)
            await interaction.followup.send(f"✅ Your TikTok handle has been set to **{handle}**.", ephemeral=True)
            await self.view._finalize_submission(interaction, self.is_skip)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)


class SkipConfirmationView(discord.ui.View):
    """A view to ask the user if the submission is a skip."""
    def __init__(self, bot, submission_data: dict, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.submission_data = submission_data
        self.message: Optional[discord.Message] = None

    async def _finalize_submission(self, interaction: discord.Interaction, is_skip: bool):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        queue_line = QueueLine.PENDING_SKIPS.value if is_skip else QueueLine.FREE.value
        line_name = "Pending Skips" if is_skip else "Free"

        if not is_skip:
            if not await self.bot.db.is_free_line_open():
                await interaction.followup.send("❌ Submissions to the Free line are currently closed.", ephemeral=True)
                return
            existing_count = await self.bot.db.get_user_submission_count_in_line(interaction.user.id, QueueLine.FREE.value)
            if existing_count > 0:
                await interaction.followup.send("❌ You already have a submission in the Free line.", ephemeral=True)
                return

        try:
            public_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=self.submission_data['artist_name'],
                song_name=self.submission_data['song_name'],
                link_or_file=self.submission_data['link_or_file'],
                queue_line=queue_line,
                note=self.submission_data.get('note')
            )

            embed = discord.Embed(
                title="✅ Submission Added!",
                description=f"Your music has been added to the **{line_name}** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=self.submission_data['artist_name'], inline=True)
            embed.add_field(name="Song", value=self.submission_data['song_name'], inline=True)
            embed.add_field(name="Submission ID", value=f"#{public_id}", inline=False)
            embed.set_footer(text="Use /mysubmissions to see your submissions | Luxurious Radio By Emerald Beats")
            await interaction.followup.send(embed=embed, ephemeral=True)

            link_value = self.submission_data.get('link_or_file', '')
            if any(domain in link_value.lower() for domain in CLOUD_STORAGE_DOMAINS):
                reminder_embed = discord.Embed(
                    title="🔗 Link Sharing Reminder",
                    description="Please ensure your file is publicly accessible so that anyone with the link can view it.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=reminder_embed, ephemeral=True)

            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(queue_line)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    async def handle_submission(self, interaction: discord.Interaction, is_skip: bool):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

        handle = await self.bot.db.get_tiktok_handle(interaction.user.id)
        if not handle:
            modal = TikTokHandleModal(self.bot, self, is_skip)
            await interaction.response.send_modal(modal)
        else:
            await self._finalize_submission(interaction, is_skip)

    @discord.ui.button(label="Yes, it's a Skip", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_submission(interaction, is_skip=True)

    @discord.ui.button(label="No, it's for the Free line", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_submission(interaction, is_skip=False)

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="This submission request has timed out.", view=self)


class SubmissionModal(discord.ui.Modal, title='Submit Music for Review'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    artist_name = discord.ui.TextInput(label='Artist Name', placeholder='Enter the artist name...', required=True, max_length=100)
    song_name = discord.ui.TextInput(label='Song Name', placeholder='Enter the song title...', required=True, max_length=100)
    link_or_file = discord.ui.TextInput(label='Music Link', placeholder='Paste a URL (YouTube, Spotify, SoundCloud, etc.)...', required=True, max_length=500)
    note = discord.ui.TextInput(label='Note (Optional)', placeholder='Anything to add for the host?', required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        link_value = str(self.link_or_file.value).strip()
        if not (link_value.startswith('http://') or link_value.startswith('https://')):
            await interaction.response.send_message("❌ Please provide a valid URL. For file uploads, use /submitfile instead.", ephemeral=True)
            return
        if 'music.apple.com' in link_value.lower() or 'itunes.apple.com' in link_value.lower():
            await interaction.response.send_message("❌ Apple Music links are not supported.", ephemeral=True)
            return

        submission_data = {
            'artist_name': str(self.artist_name.value).strip(),
            'song_name': str(self.song_name.value).strip(),
            'link_or_file': link_value,
            'note': str(self.note.value).strip() if self.note.value else None
        }
        view = SkipConfirmationView(self.bot, submission_data)
        await interaction.response.send_message("Is this a **Skip** submission?", view=view, ephemeral=True)
        view.message = await interaction.original_response()


class ResubmissionSelect(discord.ui.Select):
    def __init__(self, bot, submissions: list):
        self.bot = bot
        # Create a map for easy lookup by public_id
        self.submissions_map = {s['public_id']: s for s in submissions}

        # Sort submissions by most recent first for display, then truncate
        submissions.sort(key=lambda x: x['submission_time'], reverse=True)
        if len(submissions) > 25:
            submissions = submissions[:25]

        options = [
            discord.SelectOption(
                label=f"{s['artist_name']} - {s['song_name']}"[:100],
                description=f"Played on {s['played_time'].strftime('%Y-%m-%d')}" if s.get('played_time') else f"Submitted on {s['submission_time'].strftime('%Y-%m-%d')}",
                value=s['public_id']
            ) for s in submissions
        ]

        super().__init__(placeholder="Choose a past song to re-submit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        selected_public_id = self.values[0]
        submission_to_resubmit = self.submissions_map.get(selected_public_id)

        if not submission_to_resubmit:
            await interaction.followup.send("❌ An error occurred while finding that submission.", ephemeral=True)
            return

        # Check if the free line is open
        if not await self.bot.db.is_free_line_open():
            await interaction.followup.send("❌ Submissions to the Free line are currently closed.", ephemeral=True)
            return

        # Check if user already has a submission in the free line
        existing_count = await self.bot.db.get_user_submission_count_in_line(interaction.user.id, QueueLine.FREE.value)
        if existing_count > 0:
            await interaction.followup.send("❌ You already have a submission in the Free line.", ephemeral=True)
            return

        try:
            new_public_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=submission_to_resubmit['artist_name'],
                song_name=submission_to_resubmit['song_name'],
                link_or_file=submission_to_resubmit['link_or_file'],
                queue_line=QueueLine.FREE.value,
                note=submission_to_resubmit.get('note')
            )

            embed = discord.Embed(
                title="✅ Re-submission Successful!",
                description=f"Your music has been added to the **Free** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=submission_to_resubmit['artist_name'], inline=True)
            embed.add_field(name="Song", value=submission_to_resubmit['song_name'], inline=True)
            embed.add_field(name="New Submission ID", value=f"#{new_public_id}", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)

            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(QueueLine.FREE.value)

            # Disable the view after successful submission
            self.view.stop()
            await interaction.edit_original_response(content="This re-submission has been processed.", view=None)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred during re-submission: {str(e)}", ephemeral=True)


class ResubmissionView(discord.ui.View):
    def __init__(self, bot, submissions: list):
        super().__init__(timeout=180)
        self.message: Optional[discord.WebhookMessage] = None
        self.add_item(ResubmissionSelect(bot, submissions))

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="This re-submission request has timed out.", view=self)


class SubmissionButtonView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Submit Link', style=discord.ButtonStyle.primary, emoji='🔗', custom_id='submit_link_button')
    async def submit_link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='File Submission Instructions', style=discord.ButtonStyle.secondary, emoji='📁', custom_id='submit_file_button')
    async def submit_file_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📁 Use the `/submitfile` Command",
            description="To submit a file, please use the `/submitfile` command directly in the chat.\n\n**Example:**\n`/submitfile` `file:<your_audio_file>` `artist_name:Your Artist` `song_name:Your Song`",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Re-submit From History", style=discord.ButtonStyle.success, emoji="🔁", custom_id="resubmit_history_button")
    async def resubmit_from_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Fetch user's entire submission history
        user_submissions = await self.bot.db.get_user_submissions(interaction.user.id)

        if not user_submissions:
            await interaction.followup.send("You have no past submissions to re-submit.", ephemeral=True)
            return

        view = ResubmissionView(self.bot, user_submissions)
        message = await interaction.followup.send(
            "Please select a song from your history to re-submit to the **Free** line. Only your 25 most recent submissions are shown.",
            view=view,
            ephemeral=True
        )
        view.message = message


class SubmissionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.submission_view = SubmissionButtonView(bot)
        self.s3_client = S3Client()

    async def cog_load(self):
        self.bot.add_view(self.submission_view)

    @app_commands.command(name="submit", description="Submit music for review using a link")
    async def submit(self, interaction: discord.Interaction):
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="submitfile", description="Submit an audio file for review (MP3, M4A, FLAC)")
    @app_commands.describe(
        file="Upload your audio file (MP3, M4A, FLAC)",
        artist_name="Name of the artist",
        song_name="Title of the song",
        note="Optional note for the host"
    )
    async def submit_file(self, interaction: discord.Interaction, file: discord.Attachment, artist_name: str, song_name: str, note: Optional[str] = None):
        if not self.s3_client.is_configured:
            await interaction.response.send_message(
                "❌ File submissions are temporarily disabled as the bot's file storage is not configured. Please use a link instead.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        valid_extensions = ('.mp3', '.m4a', '.flac')
        if not file.filename.lower().endswith(valid_extensions):
            await interaction.followup.send("❌ Please upload a valid audio file (MP3, M4A, or FLAC). WAV is not supported.", ephemeral=True)
            return
        if file.size > 25 * 1024 * 1024:
            await interaction.followup.send("❌ File is too large (limit is 25MB).", ephemeral=True)
            return
        if not (artist_name.strip() and song_name.strip()):
            await interaction.followup.send("❌ Artist name and song name cannot be empty.", ephemeral=True)
            return

        try:
            file_bytes = await file.read()
            file_extension = f".{file.filename.split('.')[-1]}"
            object_name = f"submissions/{interaction.user.id}/{uuid.uuid4()}{file_extension}"

            success = await self.s3_client.upload_file_from_bytes(file_bytes, object_name, file.content_type)
            if not success:
                await interaction.followup.send("❌ There was an error uploading your file to storage. Please try again later.", ephemeral=True)
                return

            file_url = self.s3_client.get_public_file_url(object_name)

            submission_data = {
                'artist_name': artist_name.strip(),
                'song_name': song_name.strip(),
                'link_or_file': file_url,
                'note': note.strip() if note else None
            }

            view = SkipConfirmationView(self.bot, submission_data)
            await interaction.followup.send("Is this a **Skip** submission?", view=view, ephemeral=True)
            view.message = await interaction.original_response()

        except Exception as e:
            await interaction.followup.send(f"❌ An unexpected error occurred during file processing: {e}", ephemeral=True)

    @app_commands.command(name="mysubmissions", description="View your submissions in all queues")
    async def my_submissions(self, interaction: discord.Interaction):
        submissions = await self.bot.db.get_user_submissions(interaction.user.id)
        if not submissions:
            await interaction.response.send_message("You don't have any active submissions.", ephemeral=True)
            return

        embed = discord.Embed(title="Your Submissions", color=discord.Color.blue())
        description = "\n".join([f"**{s['artist_name']} – {s['song_name']}** `(ID: #{s['public_id']})`" for s in submissions])
        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="updatetiktokhandle", description="Set or update your TikTok username for all your submissions.")
    @app_commands.describe(tiktok_username="Your TikTok username (e.g., @myusername)")
    async def update_tiktok_handle(self, interaction: discord.Interaction, tiktok_username: str):
        await interaction.response.defer(ephemeral=True)
        handle = tiktok_username.strip().lstrip('@')
        if not handle or ' ' in handle or len(handle) > 100:
            await interaction.followup.send("❌ Invalid TikTok username format.", ephemeral=True)
            return

        try:
            await self.bot.db.set_tiktok_handle(interaction.user.id, handle)
            await self.bot.db.update_user_submissions_tiktok_handle(interaction.user.id, handle)
            await interaction.followup.send(f"✅ Your TikTok handle has been updated to **{handle}** for all submissions.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="setupsubmissionbuttons", description="[ADMIN] Setup submission buttons in current channel")
    @is_admin()
    async def setup_submission_buttons(self, interaction: discord.Interaction):
        """Sets up the submission buttons in the current channel."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="🎵 Music Submission Portal",
            description="Please follow the instructions for the submission type you are using.",
            color=discord.Color.blue()
        )
        link_instructions = "1. Click 'Submit Link'.\n2. Fill out the form.\n3. Await confirmation."
        file_instructions = "1. Use the `/submitfile` command.\n2. Attach your audio file.\n3. Fill in the options."
        resubmit_instructions = "1. Click 'Re-submit From History'.\n2. Choose a song from the dropdown.\n3. Await confirmation."
        embed.add_field(name="🔗 Link Submissions", value=link_instructions, inline=False)
        embed.add_field(name="📁 File Submissions", value=file_instructions, inline=False)
        embed.add_field(name="🔁 Re-submissions", value=resubmit_instructions, inline=False)

        view = SubmissionButtonView(self.bot)

        try:
            # Send the message to the channel directly
            message = await interaction.channel.send(embed=embed, view=view)

            # Try to pin the message
            try:
                await message.pin()
                await interaction.followup.send("✅ Submission buttons have been set up and pinned!", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("✅ Buttons set up, but I couldn't pin the message. Please check my permissions.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while setting up buttons: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SubmissionCog(bot))