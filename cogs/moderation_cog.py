"""
Moderation Cog - Handles automatic moderation of submission channels
"""
import re
import discord
from discord.ext import commands
from cogs.submission_cog import InitialSubmissionTypeView

class ModerationCog(commands.Cog):
    """Cog for submission channel moderation"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def _start_submission_process(self, message: discord.Message, submission_url: str):
        """Starts the submission process by asking the user to choose a submission type."""
        view = InitialSubmissionTypeView(self.bot, submission_url)
        embed = discord.Embed(
            title="🎵 New Submission",
            description="Is this submission for the **Skip** line or the **Free** line?",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Please choose an option below.")

        try:
            dm_message = await message.author.send(embed=embed, view=view)
            view.message = dm_message
        except discord.Forbidden:
            fallback_embed = discord.Embed(
                title="🎵 New Submission",
                description=(
                    f"{message.author.mention}, I couldn't DM you. Please choose a submission type below.\n\n"
                    "Is this submission for the **Skip** line or the **Free** line?"
                ),
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
            content_type = attachment.content_type or ""

            # Reject WAV files explicitly
            if content_type in ('audio/wav', 'audio/x-wav'):
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden): pass
                await message.channel.send(
                    f"{message.author.mention}, `.wav` files are not supported. Please convert to MP3, M4A, or FLAC.",
                    delete_after=15
                )
                return

            # Process any other audio type
            if content_type.startswith('audio/'):
                if attachment.size > 25 * 1024 * 1024:
                    try:
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden): pass
                    await message.channel.send(
                        f"{message.author.mention}, your file `{attachment.filename}` is too large (limit is 25MB).",
                        delete_after=15
                    )
                    return

                # It's a valid audio file, start the submission process
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden): pass

                await self._start_submission_process(message, attachment.url)
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

            await self._start_submission_process(message, url)
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