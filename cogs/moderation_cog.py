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

        # --- Action: Delete message and send temporary guidance ---
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            # Message was already deleted or we lack permissions.
            # If we can't delete, we likely can't send messages either, but we'll try.
            pass

        # Create and send a temporary, self-destructing guidance message
        guidance_embed = discord.Embed(
            title="🎵 Please Use Submission Commands",
            description=f"{message.author.mention}, this channel is for commands only. "
                        "Please use the buttons above or the `/submit` and `/submitfile` commands to add your music.",
            color=discord.Color.orange()
        )
        guidance_embed.set_footer(text="This message will be deleted automatically.")

        try:
            await message.channel.send(embed=guidance_embed, delete_after=15)
        except discord.Forbidden:
            # Bot lacks permission to send messages in this channel.
            # Silently fail as we can't inform the user.
            pass

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ModerationCog(bot))