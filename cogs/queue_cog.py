"""
Queue Cog - Handles queue display and user queue commands
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from database import QueueLine
from typing import Optional

class QueueCog(commands.Cog):
    """Cog for queue management and display"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def update_queue_display(self, queue_line: str):
        """Update the pinned queue display using paginated views"""
        try:
            # Use the QueueViewCog to create/update paginated view
            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(queue_line)
            else:
                # Fallback to old method if QueueViewCog not available
                await self._legacy_update_queue_display(queue_line)
                
        except Exception as e:
            print(f"Error updating queue display for {queue_line}: {e}")

    async def _legacy_update_queue_display(self, queue_line: str):
        """Legacy update method (fallback)"""
        try:
            # Get channel settings for this line
            channel_settings = await self.bot.db.get_channel_for_line(queue_line)
            if not channel_settings or not channel_settings['channel_id']:
                return  # No channel set for this line
            
            # Get the channel
            channel = self.bot.get_channel(channel_settings['channel_id'])
            if not channel:
                return
            
            # Get submissions for this line
            submissions = await self.bot.db.get_queue_submissions(queue_line)
            
            # Create embed
            embed = discord.Embed(
                title=f"🎵 {queue_line} Queue Line",
                color=self._get_line_color(queue_line)
            )
            
            if not submissions:
                embed.description = "No submissions in this line."
            else:
                description = ""
                # Limit to first 15 entries for legacy display
                display_submissions = submissions[:15]
                for i, sub in enumerate(display_submissions, 1):
                    link_text = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else ""
                    # Format timestamp to show local time
                    timestamp = f"<t:{int(discord.utils.parse_time(sub['submission_time']).timestamp())}:t>"
                    description += f"**{i}.** #{sub['id']} - {sub['username']} – *{sub['artist_name']} – {sub['song_name']}*{link_text} | {timestamp}\n"
                
                if len(submissions) > 15:
                    description += f"\n*... and {len(submissions) - 15} more submissions*"
                
                embed.description = description
            
            embed.set_footer(text=f"Total submissions: {len(submissions)} | Legacy Display | Luxurious Radio By Emerald Beats")
            embed.timestamp = discord.utils.utcnow()
            
            # Update or create pinned message
            if channel_settings['pinned_message_id']:
                try:
                    message = await channel.fetch_message(channel_settings['pinned_message_id'])
                    await message.edit(embed=embed)
                except discord.NotFound:
                    # Message was deleted, create new one
                    await self._create_new_pinned_message(channel, embed, queue_line)
            else:
                # No pinned message exists, create one
                await self._create_new_pinned_message(channel, embed, queue_line)
                
        except Exception as e:
            print(f"Error updating legacy queue display for {queue_line}: {e}")
    
    async def _create_new_pinned_message(self, channel, embed, queue_line):
        """Create a new pinned message for the queue"""
        try:
            message = await channel.send(embed=embed)
            await message.pin()
            await self.bot.db.update_pinned_message(queue_line, message.id)
        except Exception as e:
            print(f"Error creating pinned message: {e}")
    
    def _get_line_color(self, queue_line: str) -> discord.Color:
        """Get color for queue line embed"""
        colors = {
            QueueLine.BACKTOBACK.value: discord.Color.red(),
            QueueLine.DOUBLESKIP.value: discord.Color.orange(),
            QueueLine.SKIP.value: discord.Color.yellow(),
            QueueLine.FREE.value: discord.Color.green(),
            QueueLine.CALLS_PLAYED.value: discord.Color.purple()
        }
        return colors.get(queue_line, discord.Color.blue())
    
    @app_commands.command(name="help", description="Show help information about the music queue bot")
    async def help_command(self, interaction: discord.Interaction):
        """Display help information"""
        embed = discord.Embed(
            title="🎵 Music Queue Bot Help",
            description="TikTok-style music review queue system",
            color=discord.Color.blue()
        )
        
        # User commands
        embed.add_field(
            name="📝 User Commands",
            value=(
                "**/submit** - Submit music link for review (opens form)\n"
                "**/submitfile** - Submit MP3/audio file for review\n"
                "**/myqueue** - View your active submissions\n"
                "**/help** - Show this help message"
            ),
            inline=False
        )
        
        # Queue lines explanation
        embed.add_field(
            name="🎯 Queue Lines (Priority Order)",
            value=(
                "**BackToBack** - Highest priority\n"
                "**DoubleSkip** - High priority\n"
                "**Skip** - Medium priority\n"
                "**Free** - Standard submissions (1 per user)\n"
                "**Calls Played** - Archive of reviewed tracks"
            ),
            inline=False
        )
        
        # Admin commands (if user has permissions)
        if (
            hasattr(interaction.user, 'guild_permissions') and 
            interaction.user.guild_permissions and
            interaction.user.guild_permissions.manage_guild
        ):
            embed.add_field(
                name="🔧 Admin Commands",
                value=(
                    "**/setline** - Set channel for queue line\n"
                    "**/setsubmissionchannel** - Set auto-moderated submission channel\n"
                    "**/move** - Move submission between lines\n"
                    "**/remove** - Remove a submission\n"
                    "**/next** - Get next submission to review\n"
                    "**/opensubmissions** - Open submissions for users\n"
                    "**/closesubmissions** - Close submissions\n"
                    "**/clearfree** - Clear all submissions from Free line"
                ),
                inline=False
            )
        
        embed.set_footer(text="Music submissions are reviewed in priority order | Luxurious Radio By Emerald Beats")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(QueueCog(bot))