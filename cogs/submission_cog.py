"""
Submission Cog - Handles user submissions via Discord UI Modal
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
from typing import Optional
from database import QueueLine
from .checks import submissions_open, check_submissions_open, is_admin

class FileSubmissionModal(discord.ui.Modal, title='Submit Music File'):
    """Modal form for file submissions with metadata"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    artist_name = discord.ui.TextInput(
        label='Artist Name',
        placeholder='Enter the artist name...',
        required=True,
        max_length=100
    )

    song_name = discord.ui.TextInput(
        label='Song Name',
        placeholder='Enter the song title...',
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle file submission form - store metadata and request file upload"""
        if not await check_submissions_open(interaction):
            return

        existing_count = await self.bot.db.get_user_submission_count_in_line(
            interaction.user.id, QueueLine.FREE.value
        )

        if existing_count > 0:
            await interaction.response.send_message(
                "❌ You already have a submission in the Free line.",
                ephemeral=True
            )
            return

        await self.bot.db.add_pending_submission(
            user_id=interaction.user.id,
            artist_name=self.artist_name.value.strip(),
            song_name=self.song_name.value.strip(),
            channel_id=interaction.channel_id
        )

        embed = discord.Embed(
            title="📁 Upload Your File Now",
            description="Perfect! Now upload your audio file by **dragging and dropping** or **attaching** it to your next message.\n\n"
                       f"**Artist:** {self.artist_name.value}\n"
                       f"**Song:** {self.song_name.value}\n\n"
                       "✅ **Supported:** MP3, M4A, FLAC\n"
                       "❌ **Not Supported:** WAV files\n"
                       "📏 **Size Limit:** 25MB",
            color=discord.Color.green()
        )
        embed.set_footer(text="Just upload your file - no commands needed! This will timeout in 5 minutes | Luxurious Radio By Emerald Beats")

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)


class SubmissionModal(discord.ui.Modal, title='Submit Music for Review'):
    """Modal form for music submissions"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    artist_name = discord.ui.TextInput(
        label='Artist Name',
        placeholder='Enter the artist name...',
        required=True,
        max_length=100
    )

    song_name = discord.ui.TextInput(
        label='Song Name',
        placeholder='Enter the song title...',
        required=True,
        max_length=100
    )

    link_or_file = discord.ui.TextInput(
        label='Music Link',
        placeholder='Paste a URL (YouTube, Spotify, SoundCloud, etc.)...',
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        if not await check_submissions_open(interaction):
            return

        link_value = str(self.link_or_file.value).strip()

        if not (link_value.startswith('http://') or link_value.startswith('https://')):
            await interaction.response.send_message(
                "❌ Please provide a valid URL. For file uploads, use /submitfile instead.",
                ephemeral=True
            )
            return

        if 'music.apple.com' in link_value.lower() or 'itunes.apple.com' in link_value.lower():
            await interaction.response.send_message(
                "❌ Apple Music links are not supported. Please use a different platform.",
                ephemeral=True
            )
            return

        existing_count = await self.bot.db.get_user_submission_count_in_line(
            interaction.user.id, QueueLine.FREE.value
        )

        if existing_count > 0:
            await interaction.response.send_message(
                "❌ You already have a submission in the Free line.",
                ephemeral=True
            )
            return

        try:
            submission_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=str(self.artist_name.value).strip(),
                song_name=str(self.song_name.value).strip(),
                link_or_file=link_value,
                queue_line=QueueLine.FREE.value
            )

            embed = discord.Embed(
                title="✅ Submission Added!",
                description=f"Your music has been added to the **Free** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=self.artist_name.value, inline=True)
            embed.add_field(name="Song", value=self.song_name.value, inline=True)
            embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)
            embed.set_footer(text="Use /myqueue to see your submissions | Luxurious Radio By Emerald Beats")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(QueueLine.FREE.value)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

class SubmissionButtonView(discord.ui.View):
    """Persistent view with submission buttons"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Submit Link', style=discord.ButtonStyle.primary, emoji='🔗', custom_id='submit_link_button')
    async def submit_link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle link submission button"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='Submit File', style=discord.ButtonStyle.secondary, emoji='📁', custom_id='submit_file_button')
    async def submit_file_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle file submission button"""
        modal = FileSubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

class SubmissionCog(commands.Cog):
    """Cog for handling music submissions"""

    def __init__(self, bot):
        self.bot = bot
        self.submission_view = SubmissionButtonView(bot)

    async def cog_load(self):
        self.bot.add_view(self.submission_view)
        self.cleanup_task.start()

    async def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Clean up expired pending uploads every 5 minutes"""
        cleared_count = await self.bot.db.clear_expired_pending_submissions(expiry_minutes=5)
        if cleared_count > 0:
            print(f"Cleared {cleared_count} expired pending submissions.")

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="submit", description="Submit music for review using a link")
    @submissions_open()
    async def submit(self, interaction: discord.Interaction):
        """Open submission modal for link submissions"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="submitfile", description="Submit an MP3 file for review")
    @app_commands.describe(file="Upload your MP3 file", artist_name="Name of the artist", song_name="Title of the song")
    @submissions_open()
    async def submit_file(self, interaction: discord.Interaction, file: discord.Attachment, artist_name: str, song_name: str):
        """Submit an MP3 file for review"""
        valid_extensions = ('.mp3', '.m4a', '.flac')
        if file.filename.lower().endswith('.wav'):
            await interaction.response.send_message("❌ WAV files are not supported. Please convert to MP3, M4A, or FLAC.", ephemeral=True)
            return

        if not file.filename.lower().endswith(valid_extensions):
            await interaction.response.send_message("❌ Please upload a valid audio file (MP3, M4A, or FLAC).", ephemeral=True)
            return

        if file.size > 25 * 1024 * 1024:
            await interaction.response.send_message("❌ File is too large (limit is 25MB).", ephemeral=True)
            return

        if not (artist_name.strip() and song_name.strip()):
            await interaction.response.send_message("❌ Artist name and song name cannot be empty.", ephemeral=True)
            return

        if len(artist_name) > 100 or len(song_name) > 100:
            await interaction.response.send_message("❌ Artist and song names must be 100 characters or less.", ephemeral=True)
            return

        existing_count = await self.bot.db.get_user_submission_count_in_line(interaction.user.id, QueueLine.FREE.value)
        if existing_count > 0:
            await interaction.response.send_message("❌ You already have a submission in the Free line.", ephemeral=True)
            return

        try:
            submission_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=artist_name.strip(),
                song_name=song_name.strip(),
                link_or_file=file.url,
                queue_line=QueueLine.FREE.value
            )

            embed = discord.Embed(
                title="✅ File Submission Added!",
                description=f"Your music file has been added to the **Free** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=artist_name, inline=True)
            embed.add_field(name="Song", value=song_name, inline=True)
            embed.add_field(name="File", value=file.filename, inline=True)
            embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)
            embed.set_footer(text="Use /myqueue to see your submissions | Luxurious Radio By Emerald Beats")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                await self.bot.get_cog('QueueCog').update_queue_display(QueueLine.FREE.value)

        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="myqueue", description="View your submissions in all queues")
    async def my_queue(self, interaction: discord.Interaction):
        """Show user's submissions across all lines"""
        submissions = await self.bot.db.get_user_submissions(interaction.user.id)

        if not submissions:
            embed = discord.Embed(title="Your Queue", description="You don't have any active submissions.", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        lines = {line.value: [] for line in QueueLine}
        for sub in submissions:
            lines[sub['queue_line']].append(sub)

        embed = discord.Embed(title="Your Queue Submissions", color=discord.Color.blue())

        for line_name, subs in lines.items():
            if subs:
                value = "\n".join([f"**#{s['id']}** - *{s['artist_name']} – {s['song_name']}*" for s in subs])
                embed.add_field(name=f"{line_name} Line ({len(subs)})", value=value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for file uploads from users with pending metadata"""
        if message.author.bot: return
        
        pending_data = await self.bot.db.get_pending_submission(message.author.id)
        if not pending_data or not message.attachments or message.channel.id != pending_data['channel_id']:
            return

        file = message.attachments[0]
        
        try:
            await self._process_pending_file_upload(message, file, pending_data)
            await self.bot.db.remove_pending_submission(message.author.id)
        except Exception as e:
            await message.channel.send(f"{message.author.mention} ❌ Error processing your file: {str(e)}", delete_after=15)

    async def _process_pending_file_upload(self, message, file, pending_data):
        """Process file upload with stored metadata from the database"""
        if file.filename.lower().endswith('.wav'):
            await message.channel.send(f"{message.author.mention} ❌ WAV files are not supported.", delete_after=15)
            return

        if not file.filename.lower().endswith(('.mp3', '.m4a', '.flac')):
            await message.channel.send(f"{message.author.mention} ❌ Please upload a valid audio file.", delete_after=15)
            return

        if file.size > 25 * 1024 * 1024:
            await message.channel.send(f"{message.author.mention} ❌ File is too large (limit is 25MB).", delete_after=15)
            return

        existing_count = await self.bot.db.get_user_submission_count_in_line(message.author.id, QueueLine.FREE.value)
        if existing_count > 0:
            await message.channel.send(f"{message.author.mention} ❌ You already have a submission in the Free line.", delete_after=15)
            return

        submission_id = await self.bot.db.add_submission(
            user_id=message.author.id,
            username=message.author.display_name,
            artist_name=pending_data['artist_name'],
            song_name=pending_data['song_name'],
            link_or_file=file.url,
            queue_line=QueueLine.FREE.value
        )

        embed = discord.Embed(title="✅ File Submission Added!", description=f"Your music file has been added to the **Free** line.", color=discord.Color.green())
        embed.add_field(name="Artist", value=pending_data['artist_name'], inline=True)
        embed.add_field(name="Song", value=pending_data['song_name'], inline=True)
        embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)

        await message.add_reaction("✅")
        await message.channel.send(embed=embed, delete_after=30)

        if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
            await self.bot.get_cog('QueueCog').update_queue_display(QueueLine.FREE.value)

    @app_commands.command(name="setupsubmissionbuttons", description="[ADMIN] Setup submission buttons in current channel")
    @is_admin()
    async def setup_submission_buttons(self, interaction: discord.Interaction):
        """Setup submission buttons embed (admin only)"""
        embed = discord.Embed(title="🎵 Music Submission Portal", description="Choose how you'd like to submit your music:", color=discord.Color.blue())
        embed.add_field(name="🔗 Submit Link", value="Submit via URL (YouTube, Spotify, etc.)", inline=False)
        embed.add_field(name="📁 Submit File", value="Upload audio files directly (MP3, M4A, FLAC)", inline=False)
        embed.set_footer(text="Click the buttons below to start submitting! | Luxurious Radio By Emerald Beats")

        view = SubmissionButtonView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

        try:
            message = await interaction.original_response()
            await message.pin()
            await interaction.followup.send("✅ Submission buttons have been set up and pinned!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("✅ Submission buttons set up! (Couldn't pin - check permissions)", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"✅ Buttons set up, but pinning failed: {str(e)}", ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(SubmissionCog(bot))