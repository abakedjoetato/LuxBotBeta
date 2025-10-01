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
        embed = discord.Embed(
            title="📁 Use the `/submitfile` Command",
            description="To submit a file, please use the `/submitfile` command directly in the chat.\n\n"
                        "**Example:**\n"
                        "`/submitfile` `file:<your_audio_file>` `artist_name:Your Artist` `song_name:Your Song`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="This ensures your file is uploaded correctly with all required information.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SubmissionCog(commands.Cog):
    """Cog for handling music submissions"""

    def __init__(self, bot):
        self.bot = bot
        self.submission_view = SubmissionButtonView(bot)

    async def cog_load(self):
        self.bot.add_view(self.submission_view)

    async def cog_unload(self):
        pass

    @app_commands.command(name="submit", description="Submit music for review using a link")
    @submissions_open()
    async def submit(self, interaction: discord.Interaction):
        """Open submission modal for link submissions"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="submitfile", description="Submit an audio file for review (MP3, M4A, FLAC)")
    @app_commands.describe(
        file="Upload your audio file (MP3, M4A, FLAC)",
        artist_name="Name of the artist",
        song_name="Title of the song"
    )
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