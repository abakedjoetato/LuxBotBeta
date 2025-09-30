"""
Submission Cog - Handles user submissions via Discord UI Modal
"""

import discord
from discord.ext import commands
from discord import app_commands
import re
from typing import Optional
from database import QueueLine

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

    instructions = discord.ui.TextInput(
        label='Next Step',
        placeholder='After submitting this form, you will need to upload your file in the next message.',
        default='Click Submit, then upload your audio file in the next message.',
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle file submission form - request file upload"""
        # Check if submissions are open
        submissions_open = await self.bot.db.are_submissions_open()
        if not submissions_open:
            await interaction.response.send_message(
                "❌ Submissions are currently closed. Please try again later.",
                ephemeral=True
            )
            return

        # Check if user already has a submission in Free line
        existing_count = await self.bot.db.get_user_submission_count_in_line(
            interaction.user.id, QueueLine.FREE.value
        )

        if existing_count > 0:
            await interaction.response.send_message(
                "❌ You already have a submission in the Free line. You can only have one active submission in Free.",
                ephemeral=True
            )
            return

        # Store metadata in a temporary way for the next file upload
        # We'll need to use a follow-up message asking for file upload
        embed = discord.Embed(
            title="📁 Ready for File Upload",
            description="Please upload your audio file now (MP3, M4A, or FLAC).\n\n"
                       f"**Artist:** {self.artist_name.value}\n"
                       f"**Song:** {self.song_name.value}\n\n"
                       "❌ **Note:** WAV files are not supported.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Upload your file in your next message - this form will timeout in 5 minutes | Luxurious Radio By Emerald Beats")

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Store the metadata temporarily (we'll handle the file upload in a message listener)
        # For now, we'll implement a simpler approach asking user to use /submitfile instead
        await interaction.followup.send(
            "💡 **Alternative:** You can also use the `/submitfile` command directly with your file and metadata.",
            ephemeral=True
        )

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
        # Check if submissions are open
        submissions_open = await self.bot.db.are_submissions_open()
        if not submissions_open:
            await interaction.response.send_message(
                "❌ Submissions are currently closed. Please try again later.",
                ephemeral=True
            )
            return

        link_value = str(self.link_or_file.value).strip()

        # Check if it's a valid URL (simple but permissive check)
        if not (link_value.startswith('http://') or link_value.startswith('https://')):
            await interaction.response.send_message(
                "❌ Please provide a valid URL (YouTube, Spotify, SoundCloud, etc.). For file uploads, use /submitfile instead.",
                ephemeral=True
            )
            return

        # Block Apple Music links
        if 'music.apple.com' in link_value.lower() or 'itunes.apple.com' in link_value.lower():
            await interaction.response.send_message(
                "❌ Apple Music links are not supported. Please use YouTube, Spotify, SoundCloud, or other supported platforms.",
                ephemeral=True
            )
            return

        # Check if user already has a submission in Free line
        existing_count = await self.bot.db.get_user_submission_count_in_line(
            interaction.user.id, QueueLine.FREE.value
        )

        if existing_count > 0:
            await interaction.response.send_message(
                "❌ You already have a submission in the Free line. You can only have one active submission in Free.",
                ephemeral=True
            )
            return

        try:
            # Add submission to database
            submission_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=str(self.artist_name.value).strip(),
                song_name=str(self.song_name.value).strip(),
                link_or_file=link_value,
                queue_line=QueueLine.FREE.value
            )

            # Create success embed
            embed = discord.Embed(
                title="✅ Submission Added!",
                description=f"Your music has been added to the **Free** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=self.artist_name.value, inline=True)
            embed.add_field(name="Song", value=self.song_name.value, inline=True)
            embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)
            embed.set_footer(text="Use /myqueue to see all your submissions | Luxurious Radio By Emerald Beats")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Update queue display
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(QueueLine.FREE.value)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred while adding your submission: {str(e)}",
                ephemeral=True
            )

class SubmissionButtonView(discord.ui.View):
    """Persistent view with submission buttons"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label='Submit Link',
        style=discord.ButtonStyle.primary,
        emoji='🔗',
        custom_id='submit_link_button'
    )
    async def submit_link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle link submission button"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label='Submit File',
        style=discord.ButtonStyle.secondary,
        emoji='📁',
        custom_id='submit_file_button'
    )
    async def submit_file_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle file submission button"""
        modal = FileSubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

class SubmissionCog(commands.Cog):
    """Cog for handling music submissions"""

    def __init__(self, bot):
        self.bot = bot
        # Add persistent view for buttons
        self.submission_view = SubmissionButtonView(bot)

    @app_commands.command(name="submit", description="Submit music for review using a link")
    async def submit(self, interaction: discord.Interaction):
        """Open submission modal for link submissions"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="submitfile", description="Submit an MP3 file for review")
    @app_commands.describe(
        file="Upload your MP3 file",
        artist_name="Name of the artist",
        song_name="Title of the song"
    )
    async def submit_file(self, interaction: discord.Interaction, file: discord.Attachment, artist_name: str, song_name: str):
        """Submit an MP3 file for review"""
        # Check if submissions are open
        submissions_open = await self.bot.db.are_submissions_open()
        if not submissions_open:
            await interaction.response.send_message(
                "❌ Submissions are currently closed. Please try again later.",
                ephemeral=True
            )
            return

        # Validate file type (check both content type and extension) - Block WAV files
        valid_extensions = ('.mp3', '.m4a', '.flac')
        valid_content_types = ('audio/', 'video/')

        # Check for blocked file types
        if file.filename.lower().endswith('.wav'):
            await interaction.response.send_message(
                "❌ WAV files are not supported. Please convert to MP3, M4A, or FLAC format.",
                ephemeral=True
            )
            return

        is_valid_extension = file.filename.lower().endswith(valid_extensions)
        is_valid_content = file.content_type and any(file.content_type.startswith(ct) for ct in valid_content_types)

        if not (is_valid_extension or is_valid_content):
            await interaction.response.send_message(
                "❌ Please upload a valid audio file (MP3, M4A, or FLAC).",
                ephemeral=True
            )
            return

        # Check file size (25MB limit for Discord)
        if file.size > 25 * 1024 * 1024:
            await interaction.response.send_message(
                "❌ File is too large. Discord has a 25MB limit for file uploads.",
                ephemeral=True
            )
            return

        # Validate artist and song name
        if len(artist_name.strip()) == 0 or len(song_name.strip()) == 0:
            await interaction.response.send_message(
                "❌ Artist name and song name cannot be empty.",
                ephemeral=True
            )
            return

        if len(artist_name) > 100 or len(song_name) > 100:
            await interaction.response.send_message(
                "❌ Artist name and song name must be 100 characters or less.",
                ephemeral=True
            )
            return

        # Check if user already has a submission in Free line
        existing_count = await self.bot.db.get_user_submission_count_in_line(
            interaction.user.id, QueueLine.FREE.value
        )

        if existing_count > 0:
            await interaction.response.send_message(
                "❌ You already have a submission in the Free line. You can only have one active submission in Free.",
                ephemeral=True
            )
            return

        try:
            # Store the file URL (Discord CDN link)
            file_url = file.url

            # Add submission to database
            submission_id = await self.bot.db.add_submission(
                user_id=interaction.user.id,
                username=interaction.user.display_name,
                artist_name=artist_name.strip(),
                song_name=song_name.strip(),
                link_or_file=file_url,
                queue_line=QueueLine.FREE.value
            )

            # Create success embed
            embed = discord.Embed(
                title="✅ File Submission Added!",
                description=f"Your music file has been added to the **Free** line.",
                color=discord.Color.green()
            )
            embed.add_field(name="Artist", value=artist_name, inline=True)
            embed.add_field(name="Song", value=song_name, inline=True)
            embed.add_field(name="File", value=file.filename, inline=True)
            embed.add_field(name="File Size", value=f"{file.size / 1024 / 1024:.1f} MB", inline=True)
            embed.add_field(name="Submission ID", value=f"#{submission_id}", inline=False)
            embed.set_footer(text="Use /myqueue to see all your submissions | Luxurious Radio By Emerald Beats")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Update queue display
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(QueueLine.FREE.value)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred while adding your file submission: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="myqueue", description="View your submissions in all queues")
    async def my_queue(self, interaction: discord.Interaction):
        """Show user's submissions across all lines"""
        submissions = await self.bot.db.get_user_submissions(interaction.user.id)

        if not submissions:
            embed = discord.Embed(
                title="Your Queue",
                description="You don't have any active submissions.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Use /submit to add a song to the queue! | Luxurious Radio By Emerald Beats")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Group submissions by queue line
        lines = {line.value: [] for line in QueueLine}
        for sub in submissions:
            lines[sub['queue_line']].append(sub)

        embed = discord.Embed(
            title="Your Queue Submissions",
            color=discord.Color.blue()
        )

        for line_name, subs in lines.items():
            if subs:
                value = ""
                for sub in subs:
                    link_text = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else ""
                    value += f"**#{sub['id']}** - *{sub['artist_name']} – {sub['song_name']}*{link_text}\n"

                embed.add_field(
                    name=f"{line_name} Line ({len(subs)})",
                    value=value,
                    inline=False
                )

        embed.set_footer(text="Contact an admin to move submissions between lines | Luxurious Radio By Emerald Beats")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setupsubmissionbuttons", description="[ADMIN] Setup submission buttons in current channel")
    async def setup_submission_buttons(self, interaction: discord.Interaction):
        """Setup submission buttons embed (admin only)"""
        # Check admin permissions
        if not (hasattr(interaction.user, 'guild_permissions') and
                interaction.user.guild_permissions and
                interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        # Create submission instructions embed
        embed = discord.Embed(
            title="🎵 Music Submission Portal",
            description="Welcome to the music submission system! Choose how you'd like to submit your music:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🔗 Submit Link",
            value="Submit music via URL (YouTube, Spotify, SoundCloud, etc.)\n"
                  "❌ Apple Music links are not supported",
            inline=False
        )

        embed.add_field(
            name="📁 Submit File",
            value="Upload audio files directly (MP3, M4A, FLAC)\n"
                  "❌ WAV files are not supported\n"
                  "📏 25MB file size limit",
            inline=False
        )

        embed.add_field(
            name="📋 Submission Rules",
            value="• Only one submission allowed in Free line\n"
                  "• Use `/myqueue` to view your submissions\n"
                  "• All submissions go to the **Free** line by default",
            inline=False
        )

        embed.set_footer(text="Click the buttons below to start submitting! | Luxurious Radio By Emerald Beats")

        # Send embed with buttons
        view = SubmissionButtonView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

        # Pin the message
        try:
            message = await interaction.original_response()
            await message.pin()
            await interaction.followup.send("✅ Submission buttons have been set up and pinned!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("✅ Submission buttons have been set up! (Couldn't pin - check bot permissions)", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"✅ Submission buttons set up, but pinning failed: {str(e)}", ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    cog = SubmissionCog(bot)
    await bot.add_cog(cog)

    # Add persistent view for buttons
    bot.add_view(cog.submission_view)