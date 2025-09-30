
"""
Queue View - Paginated queue display system with Discord Views
"""

import discord
from discord.ext import commands
import math
from typing import List, Dict, Any, Optional
from database import QueueLine

class PaginatedQueueView(discord.ui.View):
    """Discord View for paginated queue display with navigation buttons"""
    
    def __init__(self, bot, queue_line: str, entries_per_page: int = 10):
        super().__init__(timeout=900)  # 15 minutes timeout
        self.bot = bot
        self.queue_line = queue_line
        self.entries_per_page = entries_per_page
        self.current_page = 1
        self.total_pages = 1
        self.submissions = []
        
    async def update_data(self):
        """Fetch latest queue data and calculate pagination"""
        self.submissions = await self.bot.db.get_queue_submissions(self.queue_line)
        self.total_pages = max(1, math.ceil(len(self.submissions) / self.entries_per_page))
        
        # Ensure current page is valid
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        elif self.current_page < 1:
            self.current_page = 1
    
    def get_page_submissions(self) -> List[Dict[str, Any]]:
        """Get submissions for the current page"""
        start_idx = (self.current_page - 1) * self.entries_per_page
        end_idx = start_idx + self.entries_per_page
        return self.submissions[start_idx:end_idx]
    
    def create_embed(self) -> discord.Embed:
        """Create the embed for the current page"""
        embed = discord.Embed(
            title=f"🎵 {self.queue_line} Queue Line",
            color=self._get_line_color()
        )
        
        page_submissions = self.get_page_submissions()
        
        if not self.submissions:
            embed.description = "No submissions in this line."
        elif not page_submissions:
            embed.description = "No submissions on this page."
        else:
            description = ""
            start_number = (self.current_page - 1) * self.entries_per_page + 1
            
            for i, sub in enumerate(page_submissions):
                position = start_number + i
                link_text = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else ""
                timestamp = f"<t:{int(discord.utils.parse_time(sub['submission_time']).timestamp())}:t>"
                description += f"**{position}.** #{sub['id']} - {sub['username']} – *{sub['artist_name']} – {sub['song_name']}*{link_text} | {timestamp}\n"
            
            embed.description = description
        
        # Footer with pagination info
        if self.total_pages > 1:
            embed.set_footer(
                text=f"Page {self.current_page} of {self.total_pages} | Total: {len(self.submissions)} submissions | Luxurious Radio By Emerald Beats"
            )
        else:
            embed.set_footer(
                text=f"Total submissions: {len(self.submissions)} | Luxurious Radio By Emerald Beats"
            )
        
        embed.timestamp = discord.utils.utcnow()
        return embed
    
    def _get_line_color(self) -> discord.Color:
        """Get color for queue line embed"""
        colors = {
            QueueLine.BACKTOBACK.value: discord.Color.red(),
            QueueLine.DOUBLESKIP.value: discord.Color.orange(),
            QueueLine.SKIP.value: discord.Color.yellow(),
            QueueLine.FREE.value: discord.Color.green(),
            QueueLine.CALLS_PLAYED.value: discord.Color.purple()
        }
        return colors.get(self.queue_line, discord.Color.blue())
    
    def update_buttons(self):
        """Update button states based on current page"""
        self.previous_button.disabled = (self.current_page <= 1)
        self.next_button.disabled = (self.current_page >= self.total_pages)
        self.go_to_page_button.disabled = (self.total_pages <= 1)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_data()
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.update_data()
            self.update_buttons()
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔢 Go to Page", style=discord.ButtonStyle.primary, custom_id="goto")
    async def go_to_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to go to specific page"""
        if self.total_pages <= 1:
            await interaction.response.defer()
            return
        
        modal = GoToPageModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.success, custom_id="refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh the queue data"""
        await self.update_data()
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_timeout(self):
        """Called when view times out"""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Try to edit the message to show it's expired
        try:
            embed = self.create_embed()
            embed.set_footer(text="This view has expired. Use the queue command again to get a fresh view.")
            if hasattr(self, 'message') and self.message:
                await self.message.edit(embed=embed, view=self)
        except:
            pass

class GoToPageModal(discord.ui.Modal, title="Go to Page"):
    """Modal for jumping to a specific page"""
    
    def __init__(self, queue_view: PaginatedQueueView):
        super().__init__()
        self.queue_view = queue_view
    
    page_number = discord.ui.TextInput(
        label=f'Page Number (1-{1})',  # Will be updated dynamically
        placeholder='Enter page number...',
        required=True,
        max_length=5
    )
    
    def __init__(self, queue_view: PaginatedQueueView):
        super().__init__()
        self.queue_view = queue_view
        # Update the label with actual max pages
        self.page_number.label = f'Page Number (1-{queue_view.total_pages})'
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle page jump submission"""
        try:
            target_page = int(self.page_number.value)
            
            if 1 <= target_page <= self.queue_view.total_pages:
                self.queue_view.current_page = target_page
                await self.queue_view.update_data()
                self.queue_view.update_buttons()
                embed = self.queue_view.create_embed()
                await interaction.response.edit_message(embed=embed, view=self.queue_view)
            else:
                await interaction.response.send_message(
                    f"❌ Invalid page number. Please enter a number between 1 and {self.queue_view.total_pages}.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.",
                ephemeral=True
            )

class QueueViewCog(commands.Cog):
    """Cog for managing paginated queue views"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def create_or_update_queue_view(self, queue_line: str) -> Optional[PaginatedQueueView]:
        """Create or update a paginated queue view"""
        try:
            # Get channel settings for this line
            channel_settings = await self.bot.db.get_channel_for_line(queue_line)
            if not channel_settings or not channel_settings['channel_id']:
                return None
            
            # Get the channel
            channel = self.bot.get_channel(channel_settings['channel_id'])
            if not channel:
                return None
            
            # Create new paginated view
            view = PaginatedQueueView(self.bot, queue_line)
            await view.update_data()
            view.update_buttons()
            embed = view.create_embed()
            
            # Update or create pinned message
            if channel_settings['pinned_message_id']:
                try:
                    message = await channel.fetch_message(channel_settings['pinned_message_id'])
                    await message.edit(embed=embed, view=view)
                    view.message = message
                except discord.NotFound:
                    # Message was deleted, create new one
                    message = await self._create_new_pinned_message(channel, embed, view, queue_line)
                    view.message = message
            else:
                # No pinned message exists, create one
                message = await self._create_new_pinned_message(channel, embed, view, queue_line)
                view.message = message
            
            return view
            
        except Exception as e:
            print(f"Error creating/updating queue view for {queue_line}: {e}")
            return None
    
    async def _create_new_pinned_message(self, channel, embed, view, queue_line):
        """Create a new pinned message for the queue view"""
        try:
            message = await channel.send(embed=embed, view=view)
            await message.pin()
            await self.bot.db.update_pinned_message(queue_line, message.id)
            return message
        except Exception as e:
            print(f"Error creating pinned message: {e}")
            return None

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(QueueViewCog(bot))
