"""
Moderation Cog - Handles automatic moderation of submission channels
"""
import re
import discord
from discord.ext import commands
from cogs.submission_cog import AddSubmissionDetailView, FreeLineClosedConfirmationView

class ModerationCog(commands.Cog):
    """Cog for submission channel moderation"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def _start_submission_process(self, message: discord.Message, submission_url: str, submission_type: str):
        """Checks if the free line is open and sends the appropriate view to the user."""
        is_open = await self.bot.db.is_free_line_open()

        if is_open:
            view = AddSubmissionDetailView(self.bot, submission_url)
            embed = discord.Embed(
                title=f"🎵 Complete Your {submission_type} Submission",
                description=f"You've provided a {submission_type.lower()}! Click the button below to add the artist and song details.",
                color=discord.Color.purple()
            )
            embed.set_footer(text="This prompt will time out in 5 minutes.")
        else:
            view = FreeLineClosedConfirmationView(self.bot, submission_url)
            embed = discord.Embed(
                title="⚠️ Free Submissions Closed",
                description=(
                    "Submissions to the **Free line** are currently closed. "
                    "However, you can still submit to the **Skip line**.\n\n"
                    "Would you like to submit your music as a Skip?"
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="This prompt will time out in 3 minutes.")

        try:
            dm_message = await message.author.send(embed=embed, view=view)
            view.message = dm_message
        except discord.Forbidden:
            fallback_embed = discord.Embed(
                title="🎵 Complete Your Submission",
                description=f"{message.author.mention}, I can't DM you! Click below to continue your submission.",
                color=discord.Color.orange()
            )
            public_message = await message.channel.send(embed=fallback_embed, view=view)
            view.message = public_message
        except discord.HTTPException:
            pass # Fail silently

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle messages in the designated submission channel for files, links, or invalid content."""
        # --- Basic checks ---
        if message.author.bot:
            return
        
        submission_channel_id = await self.bot.db.get_submission_channel()
        if not submission_channel_id or message.channel.id != submission_channel_id:
            return
        
        # --- Permission and content checks ---
        # Don't delete the main submission portal embed message
        if message.embeds and any("Music Submission Portal" in (e.title or "") for e in message.embeds):
            return

        # --- Handle File Uploads ---
        if message.attachments:
            attachment = message.attachments[0]

            # --- Use content_type for reliable file detection ---
            valid_content_types = ('audio/mpeg', 'audio/mp4', 'audio/flac')

            # WAV file check
            if attachment.content_type == 'audio/wav':
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden): pass
                await message.channel.send(
                    f"{message.author.mention}, `.wav` files are not supported. Please convert to MP3, M4A, or FLAC.",
                    delete_after=15
                )
                return

            # Check for other valid audio file types
            if attachment.content_type in valid_content_types:
                if attachment.size > 25 * 1024 * 1024:
                    try:
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden): pass
                    await message.channel.send(
                        f"{message.author.mention}, your file `{attachment.filename}` is too large (limit is 25MB).",
                        delete_after=15
                    )
                    return

                # It's a valid file, start the submission process
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden): pass

                await self._start_submission_process(message, attachment.url, "File")
                return

        # --- Handle Links ---
        url_match = re.search(r'https?://\S+', message.content)
        if url_match and not message.attachments:
            url = url_match.group(0)

            # Check for forbidden links (Apple Music)
            if 'music.apple.com' in url.lower() or 'itunes.apple.com' in url.lower():
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden): pass
                await message.channel.send(
                    f"{message.author.mention}, Apple Music links are not supported. Please use another platform.",
                    delete_after=15
                )
                return

            # It's a valid link, start the submission process
            try:
                await message.delete()
            except (discord.NotFound, discord.Forbidden): pass

            await self._start_submission_process(message, url, "Link")
            return

        # --- Action: Delete any other messages and send guidance ---
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden): pass

        guidance_embed = discord.Embed(
            title="🎵 How to Submit Your Music",
            description=(
                "Hello! To keep this channel organized, please submit by either **pasting a link** or **uploading an audio file**.\n\n"
                "I will then guide you through the rest of the submission process privately."
            ),
            color=discord.Color.blue()
        )
        guidance_embed.set_footer(text="You can also use the /submit or /submitfile commands.")

        try:
            await message.author.send(embed=guidance_embed)
        except discord.Forbidden:
            fallback_message = (
                f"{message.author.mention}, please submit by pasting a link or uploading an audio file. "
                "I tried to DM you more info, but your DMs are closed."
            )
            try:
                await message.channel.send(fallback_message, delete_after=20)
            except discord.Forbidden: pass
        except discord.HTTPException:
            pass

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ModerationCog(bot))