"""
Submission Cog - Handles user submissions via Discord UI Modal
"""

import discord
from discord.ext import commands
from discord import app_commands
import re
from typing import Optional
from database import QueueLine

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
        label='Link or File',
        placeholder='Paste a URL (YouTube, Spotify, etc.) or upload an MP3...',
        required=True,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        # Validate link/URL format
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        link_value = str(self.link_or_file.value).strip()
        
        # Check if it's a valid URL or uploaded file
        if not (url_pattern.match(link_value) or link_value.endswith('.mp3')):
            await interaction.response.send_message(
                "❌ Please provide a valid URL (YouTube, Spotify, etc.) or upload an MP3 file.",
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
            embed.set_footer(text="Use /myqueue to see all your submissions")
            
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

class SubmissionCog(commands.Cog):
    """Cog for handling music submissions"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="submit", description="Submit music for review")
    async def submit(self, interaction: discord.Interaction):
        """Open submission modal"""
        modal = SubmissionModal(self.bot)
        await interaction.response.send_modal(modal)
    
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
            embed.set_footer(text="Use /submit to add a song to the queue!")
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
        
        embed.set_footer(text="Contact an admin to move submissions between lines")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(SubmissionCog(bot))