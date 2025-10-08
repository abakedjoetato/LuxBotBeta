"""
Admin Cog - Handles administrative commands for queue management
"""

import discord
from discord.ext import commands
from discord import app_commands
from database import QueueLine
from typing import Optional
from .checks import is_admin
import logging

class NextActionView(discord.ui.View):
    def __init__(self, bot, submission_public_id: str):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.bot = bot
        self.submission_public_id = submission_public_id

    @discord.ui.button(label="Bookmark", style=discord.ButtonStyle.success, emoji="🔖")
    async def bookmark_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            bookmark_channel_id = self.bot.settings_cache.get('bookmark_channel_id')
            if not bookmark_channel_id:
                await interaction.followup.send("❌ No bookmark channel has been set.", ephemeral=True)
                return

            bookmark_channel = self.bot.get_channel(int(bookmark_channel_id))
            if not bookmark_channel:
                await interaction.followup.send("❌ Bookmark channel not found.", ephemeral=True)
                return

            submission = await self.bot.db.get_submission_by_id(self.submission_public_id)
            if not submission:
                await interaction.followup.send(f"❌ Submission #{self.submission_public_id} not found.", ephemeral=True)
                return

            embed = discord.Embed(title="🔖 Bookmarked Submission", description=f"Bookmarked by {interaction.user.mention}", color=discord.Color.gold())
            embed.add_field(name="Submission ID", value=f"#{submission['public_id']}", inline=True)
            embed.add_field(name="Queue Line", value=submission['queue_line'], inline=True)
            embed.add_field(name="Submitted By", value=submission['username'], inline=True)
            embed.add_field(name="Artist", value=submission['artist_name'], inline=True)
            embed.add_field(name="Song", value=submission['song_name'], inline=True)
            embed.add_field(name="User ID", value=submission['user_id'], inline=True)
            if submission['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({submission['link_or_file']})", inline=False)
            if submission.get('tiktok_username'):
                embed.add_field(name="TikTok", value=submission['tiktok_username'], inline=True)
            if submission.get('note'):
                embed.add_field(name="Note", value=submission['note'], inline=False)
            embed.set_footer(text=f"Originally submitted on {submission['submission_time']}")
            embed.timestamp = discord.utils.utcnow()

            await bookmark_channel.send(embed=embed)
            button.disabled = True
            button.label = "Bookmarked"
            await interaction.edit_original_response(view=self)

        except Exception as e:
            logging.error(f"Error bookmarking submission: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error bookmarking submission: {str(e)}", ephemeral=True)


class AdminCog(commands.Cog):
    """Cog for administrative queue management"""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="move", description="Move a submission to a different queue line")
    @app_commands.describe(submission_id="The ID of the submission to move (e.g., #123456)", target_line="The target queue line")
    @app_commands.choices(target_line=[app_commands.Choice(name=ql.value, value=ql.value) for ql in QueueLine if ql != QueueLine.SONGS_PLAYED])
    @is_admin()
    async def move_submission(self, interaction: discord.Interaction, submission_id: str, target_line: str):
        """Move a submission between queue lines"""
        public_id = submission_id.strip('#')
        try:
            original_line = await self.bot.db.move_submission(public_id, target_line)
            if original_line:
                embed = discord.Embed(title="✅ Submission Moved", description=f"Submission `#{public_id}` has been moved to **{target_line}** line.", color=discord.Color.green())
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Submission `#{public_id}` not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error moving submission: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="remove", description="Remove a submission from the queue")
    @app_commands.describe(submission_id="The ID of the submission to remove (e.g., #123456)")
    @is_admin()
    async def remove_submission(self, interaction: discord.Interaction, submission_id: str):
        """Remove a submission from the queue"""
        public_id = submission_id.strip('#')
        try:
            original_line = await self.bot.db.remove_submission_from_queue(public_id)
            if original_line:
                embed = discord.Embed(title="✅ Submission Removed", description=f"Submission `#{public_id}` has been removed from the queue.", color=discord.Color.green())
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Submission `#{public_id}` not found.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error removing submission: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="setsubmissionchannel", description="Set the channel for submissions (auto-moderated)")
    @app_commands.describe(channel="The text channel to use for submissions")
    @is_admin()
    async def set_submission_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.set_bot_config('submission_channel_id', channel_id=channel.id)
        self.bot.settings_cache['submission_channel_id'] = channel.id
        embed = discord.Embed(title="✅ Submission Channel Set", description=f"Submissions channel is now set to {channel.mention}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="next", description="Get the next submission to review")
    @is_admin()
    async def next_submission(self, interaction: discord.Interaction):
        """Get the next submission, move it to Songs Played, and reset the user's points."""
        try:
            next_sub = await self.bot.db.take_next_to_songs_played()
            if not next_sub:
                await interaction.response.send_message(embed=discord.Embed(title="📭 Queue Empty", description="No submissions are currently in the queue.", color=discord.Color.blue()), ephemeral=True)
                return

            submitter_id = next_sub.get('user_id')
            if submitter_id:
                await self.bot.db.reset_user_points(submitter_id)
                point_reset_message = "Submitter points reset."
            else:
                point_reset_message = "Could not reset points."

            now_playing_channel_id = self.bot.settings_cache.get('now_playing_channel_id')
            if now_playing_channel_id:
                channel = self.bot.get_channel(int(now_playing_channel_id))
                if channel:
                    announcement = f"🎶 Now Playing: {next_sub['artist_name']} – {next_sub['song_name']} (submitted by {next_sub['username']})"
                    await channel.send(announcement)

            embed = discord.Embed(title="🎵 Now Playing - Moved to Songs Played", description=f"Moved from **{next_sub['original_line']}** line.", color=discord.Color.gold())
            embed.add_field(name="Submission ID", value=f"#{next_sub['public_id']}", inline=True)
            embed.add_field(name="Submitted By", value=next_sub['username'], inline=True)
            embed.add_field(name="Artist", value=next_sub['artist_name'], inline=True)
            embed.add_field(name="Song", value=next_sub['song_name'], inline=True)
            if next_sub['link_or_file'].startswith('http'):
                embed.add_field(name="Link", value=f"[Click Here]({next_sub['link_or_file']})", inline=False)
            if next_sub.get('note'):
                embed.add_field(name="Note", value=next_sub['note'], inline=False)
            embed.set_footer(text=f"Submitted on {next_sub['submission_time']} | {point_reset_message}")
            
            view = NextActionView(self.bot, next_sub['public_id'])
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Error in /next command: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ Error getting next submission: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="opensubmissions", description="Open submissions for the Free line")
    @is_admin()
    async def open_submissions(self, interaction: discord.Interaction):
        await self.bot.db.set_free_line_status(True)
        await interaction.response.send_message(embed=discord.Embed(title="✅ Free Line Opened", color=discord.Color.green()), ephemeral=True)
    
    @app_commands.command(name="closesubmissions", description="Close submissions for the Free line")
    @is_admin()
    async def close_submissions(self, interaction: discord.Interaction):
        await self.bot.db.set_free_line_status(False)
        await interaction.response.send_message(embed=discord.Embed(title="🚫 Free Line Closed", color=discord.Color.red()), ephemeral=True)
    
    @app_commands.command(name="clearfree", description="Clear all submissions from the Free line")
    @is_admin()
    async def clear_free_line(self, interaction: discord.Interaction):
        cleared_count = await self.bot.db.clear_free_line()
        embed = discord.Embed(title="🗑️ Free Line Cleared", description=f"Removed {cleared_count} submissions.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="setbookmarkchannel", description="Set the channel for bookmarked submissions")
    @is_admin()
    async def set_bookmark_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.set_bot_config('bookmark_channel_id', channel_id=channel.id)
        self.bot.settings_cache['bookmark_channel_id'] = channel.id
        embed = discord.Embed(title="✅ Bookmark Channel Set", description=f"Bookmark channel set to {channel.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setnowplayingchannel", description="Set the channel for 'Now Playing' announcements")
    @is_admin()
    async def set_now_playing_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.set_bot_config('now_playing_channel_id', channel_id=channel.id)
        self.bot.settings_cache['now_playing_channel_id'] = channel.id
        embed = discord.Embed(title="✅ 'Now Playing' Channel Set", description=f"Announcements will be sent to {channel.mention}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))