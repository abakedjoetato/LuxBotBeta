"""
Moderation Cog - Handles automatic moderation of submission channels
"""

import discord
from discord.ext import commands

class ModerationCog(commands.Cog):
    """Cog for submission channel moderation"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def _is_admin_or_mod(self, member: discord.Member) -> bool:
        """Check if a member has admin or moderator permissions."""
        if isinstance(member, discord.User):  # User in DMs, no permissions
            return False
        # Simplified check for guild permissions
        return member.guild_permissions.manage_messages or member.guild_permissions.manage_guild

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle non-command messages in the designated submission channel."""
        # --- Basic checks ---
        if message.author.bot:
            return
        
        submission_channel_id = await self.bot.db.get_submission_channel()
        if not submission_channel_id or message.channel.id != submission_channel_id:
            return
        
        # --- Permission and content checks ---
        if self._is_admin_or_mod(message.author):
            return

        # Don't delete the main submission portal embed message
        if message.embeds and any("Music Submission Portal" in (e.title or "") for e in message.embeds):
            return

        # --- Action: Delete message and send DM guidance ---
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            # Message was already deleted or we lack permissions.
            pass

        # Create and send a guidance message via DM
        guidance_embed = discord.Embed(
            title="🎵 How to Submit Your Music",
            description=(
                "Hello! I noticed you sent a message in the submissions channel. "
                "To keep things organized, that channel only accepts submissions through our official bot commands.\n\n"
                "**Please use one of these methods:**\n"
                "1. Click the `Submit Link` or `Submit File` buttons in the channel.\n"
                "2. Use the `/submit` command for links.\n"
                "3. Use the `/submitfile` command for audio files."
            ),
            color=discord.Color.blue()
        )
        guidance_embed.set_footer(text="This helps us process every submission fairly. Thank you!")

        try:
            await message.author.send(embed=guidance_embed)
        except discord.Forbidden:
            # User has DMs disabled, so we can't send the message.
            # We can post a temporary message in the channel as a fallback.
            fallback_message = (
                f"{message.author.mention}, I tried to DM you submission instructions, but your DMs are closed. "
                "Please use the buttons or `/submit` commands in this channel."
            )
            try:
                await message.channel.send(fallback_message, delete_after=15)
            except discord.Forbidden:
                pass # Can't send messages in the channel either, so we fail silently.
        except discord.HTTPException:
            # Handle other potential HTTP errors.
            # In this context, we'll just fail silently.
            pass

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ModerationCog(bot))