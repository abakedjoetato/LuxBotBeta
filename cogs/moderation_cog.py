
"""
Moderation Cog - Handles automatic moderation of submission channels
"""

import discord
from discord.ext import commands

class ModerationCog(commands.Cog):
    """Cog for submission channel moderation"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def _has_admin_permissions(self, member: discord.Member) -> bool:
        """Check if user has admin/moderator permissions"""
        return (
            hasattr(member, 'guild_permissions') and 
            member.guild_permissions and
            (member.guild_permissions.manage_guild or 
             member.guild_permissions.manage_messages or
             member.guild_permissions.administrator)
        )
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages in submission channel"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if this is the submission channel
        submission_channel_id = await self.bot.db.get_submission_channel()
        if not submission_channel_id or message.channel.id != submission_channel_id:
            return
        
        # Check if user has admin/moderator permissions
        if isinstance(message.author, discord.Member) and self._has_admin_permissions(message.author):
            return
        
        # Check if this message has embeds with submission buttons (preserve those)
        if message.embeds:
            for embed in message.embeds:
                if embed.title and "Music Submission Portal" in embed.title:
                    return  # Don't delete the submission buttons embed
        
        # Delete the message and send guidance
        try:
            await message.delete()
            
            # Create guidance embed
            embed = discord.Embed(
                title="🎵 Submission Guidelines",
                description="This channel is for music submissions only. Please use the proper commands:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📋 How to Submit",
                value=(
                    "**For links:** Use `/submit` command\n"
                    "**For files:** Use `/submitfile` command\n\n"
                    "These commands will guide you through the submission process!"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔍 View Your Submissions",
                value="Use `/myqueue` to see all your active submissions",
                inline=False
            )
            
            embed.set_footer(text="Your message was removed - please use the commands above")
            
            # Send as ephemeral message to the user
            try:
                await message.channel.send(
                    f"{message.author.mention}, please check your DMs for submission guidelines.",
                    delete_after=10
                )
                await message.author.send(embed=embed)
            except discord.Forbidden:
                # If DMs are disabled, send in channel with delete timer
                await message.channel.send(
                    content=f"{message.author.mention}",
                    embed=embed,
                    delete_after=30
                )
                
        except discord.NotFound:
            # Message was already deleted
            pass
        except discord.Forbidden:
            # Bot doesn't have permission to delete messages
            pass

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ModerationCog(bot))
