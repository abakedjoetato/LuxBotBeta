"""
Admin Cog - Handles administrative commands for queue management
"""

import discord
from discord.ext import commands
from discord import app_commands
from database import QueueLine
from typing import Optional

class AdminCog(commands.Cog):
    """Cog for administrative queue management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def _has_admin_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        return (
            hasattr(interaction.user, 'guild_permissions') and 
            interaction.user.guild_permissions and
            interaction.user.guild_permissions.manage_guild
        )
    
    @app_commands.command(name="setline", description="Set the channel for a queue line")
    @app_commands.describe(
        line="The queue line to configure",
        channel="The text channel to use for this line"
    )
    @app_commands.choices(line=[
        app_commands.Choice(name="BackToBack", value="BackToBack"),
        app_commands.Choice(name="DoubleSkip", value="DoubleSkip"),
        app_commands.Choice(name="Skip", value="Skip"),
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Calls Played", value="Calls Played")
    ])
    async def set_line(self, interaction: discord.Interaction, line: str, channel: discord.TextChannel):
        """Set the channel for a queue line"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Set channel for line
            await self.bot.db.set_channel_for_line(line, channel.id)
            
            # Update queue display
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(line)
            
            embed = discord.Embed(
                title="✅ Line Channel Set",
                description=f"**{line}** line is now set to {channel.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error setting line channel: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="move", description="Move a submission to a different queue line")
    @app_commands.describe(
        submission_id="The ID of the submission to move",
        target_line="The target queue line"
    )
    @app_commands.choices(target_line=[
        app_commands.Choice(name="BackToBack", value="BackToBack"),
        app_commands.Choice(name="DoubleSkip", value="DoubleSkip"),
        app_commands.Choice(name="Skip", value="Skip"),
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Calls Played", value="Calls Played")
    ])
    async def move_submission(self, interaction: discord.Interaction, submission_id: int, target_line: str):
        """Move a submission between queue lines"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Move the submission
            success = await self.bot.db.move_submission(submission_id, target_line)
            
            if success:
                # Update queue displays for all lines
                if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                    queue_cog = self.bot.get_cog('QueueCog')
                    for line in QueueLine:
                        await queue_cog.update_queue_display(line.value)
                
                embed = discord.Embed(
                    title="✅ Submission Moved",
                    description=f"Submission #{submission_id} has been moved to **{target_line}** line.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} not found.", 
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error moving submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="remove", description="Remove a submission from the queue")
    @app_commands.describe(submission_id="The ID of the submission to remove")
    async def remove_submission(self, interaction: discord.Interaction, submission_id: int):
        """Remove a submission from the queue"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Remove the submission
            success = await self.bot.db.remove_submission(submission_id)
            
            if success:
                # Update queue displays for all lines
                if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                    queue_cog = self.bot.get_cog('QueueCog')
                    for line in QueueLine:
                        await queue_cog.update_queue_display(line.value)
                
                embed = discord.Embed(
                    title="✅ Submission Removed",
                    description=f"Submission #{submission_id} has been removed from the queue.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"❌ Submission #{submission_id} not found.", 
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error removing submission: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="setsubmissionchannel", description="Set the channel for submissions (auto-moderated)")
    @app_commands.describe(channel="The text channel to use for submissions")
    async def set_submission_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for submissions"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Set submission channel
            await self.bot.db.set_submission_channel(channel.id)
            
            embed = discord.Embed(
                title="✅ Submission Channel Set",
                description=f"Submissions channel is now set to {channel.mention}\n\n"
                           f"Non-admin messages will be automatically removed and users will be guided to use `/submit` or `/submitfile` commands.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error setting submission channel: {str(e)}", 
                ephemeral=True
            )
    
    @app_commands.command(name="next", description="Get the next submission to review")
    async def next_submission(self, interaction: discord.Interaction):
        """Get the next submission following priority order"""
        if not self._has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
            return
        
        try:
            # Atomically take the next submission and move it to Calls Played
            next_sub = await self.bot.db.take_next_to_calls_played()
            
            if not next_sub:
                embed = discord.Embed(
                    title="📭 Queue Empty",
                    description="No submissions are currently in the queue.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create embed for the taken submission
            embed = discord.Embed(
                title="🎵 Now Playing - Moved to Calls Played",
                description=f"Moved from **{next_sub['original_line']}** line to **Calls Played**",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="Submission ID", value=f"#{next_sub['id']}", inline=True)
            embed.add_field(name="Original Line", value=next_sub['original_line'], inline=True)
            embed.add_field(name="Submitted By", value=next_sub['username'], inline=True)
            embed.add_field(name="Artist", value=next_sub['artist_name'], inline=True)
            embed.add_field(name="Song", value=next_sub['song_name'], inline=True)
            
            if next_sub['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({next_sub['link_or_file']})", inline=False)
            else:
                embed.add_field(name="File", value=next_sub['link_or_file'], inline=False)
            
            embed.set_footer(text=f"Submitted on {next_sub['submission_time']}")
            
            # Send to admin who used the command
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Update queue displays for both the origin line and Calls Played
            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('QueueCog'):
                queue_cog = self.bot.get_cog('QueueCog')
                await queue_cog.update_queue_display(next_sub['original_line'])
                await queue_cog.update_queue_display(QueueLine.CALLS_PLAYED.value)
            
            # Also send to DM if possible
            try:
                await interaction.user.send(embed=embed)
            except discord.Forbidden:
                pass  # User has DMs disabled
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error getting next submission: {str(e)}", 
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(AdminCog(bot))