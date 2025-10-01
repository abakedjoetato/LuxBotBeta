"""
Queue View - Paginated queue display system with Discord Views
"""

import discord
from discord.ext import commands
import math
from typing import List, Dict, Any, Optional
from database import QueueLine
import datetime

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
        self.message: Optional[discord.Message] = None
        
    async def update_data(self):
        """Fetch latest queue data and calculate pagination"""
        self.submissions = await self.bot.db.get_queue_submissions(self.queue_line)
        self.total_pages = max(1, math.ceil(len(self.submissions) / self.entries_per_page))
        
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        elif self.current_page < 1:
            self.current_page = 1
    
    def get_page_submissions(self) -> List[Dict[str, Any]]:
        """Get submissions for the current page"""
        start_idx = (self.current_page - 1) * self.entries_per_page
        end_idx = start_idx + self.entries_per_page
        return self.submissions[start_idx:end_idx]
    
    def create_embed(self, is_expired: bool = False) -> discord.Embed:
        """Create the embed for the current page"""
        color = self._get_line_color() if not is_expired else discord.Color.light_grey()
        embed = discord.Embed(
            title=f"🎵 {self.queue_line} Queue Line",
            color=color
        )
        
        page_submissions = self.get_page_submissions()
        
        if not self.submissions:
            embed.description = "This queue is currently empty."
        else:
            description_lines = []
            start_number = (self.current_page - 1) * self.entries_per_page + 1
            for i, sub in enumerate(page_submissions, start_number):
                link_text = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else " (File)"
                # Safely parse timestamp
                try:
                    ts = datetime.datetime.fromisoformat(sub['submission_time'])
                    timestamp_str = f"<t:{int(ts.timestamp())}:R>"
                except (ValueError, TypeError):
                    timestamp_str = ""

                description_lines.append(
                    f"**{i}.** `#{sub['id']}`: **{sub['artist_name']} – {sub['song_name']}** "
                    f"by *{sub['username']}* {timestamp_str}{link_text}"
                )
            embed.description = "\n".join(description_lines)
        
        footer_text = f"Total submissions: {len(self.submissions)}"
        if self.total_pages > 1:
            footer_text = f"Page {self.current_page} of {self.total_pages} | {footer_text}"
        
        if is_expired:
            embed.description = "This interactive view has expired. Please use the command again to get a new one."
            footer_text = "View has expired"

        embed.set_footer(text=f"{footer_text} | Luxurious Radio By Emerald Beats")
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
        return colors.get(self.queue_line, discord.Color.default())
    
    def update_buttons(self):
        """Update button states based on current page"""
        self.previous_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages
        self.go_to_page_button.disabled = self.total_pages <= 1
    
    async def _update_message(self, interaction: discord.Interaction):
        """Helper to update the message with the latest data."""
        await self.update_data()
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            await self._update_message(interaction)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self._update_message(interaction)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Go to", style=discord.ButtonStyle.primary, emoji="🔢", custom_id="goto")
    async def go_to_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.total_pages <= 1:
            await interaction.response.defer()
            return
        modal = GoToPageModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.success, emoji="🔄", custom_id="refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_message(interaction)
    
    async def on_timeout(self):
        """Called when view times out. Disables buttons and updates the embed."""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            try:
                embed = self.create_embed(is_expired=True)
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass # Message might have been deleted

class GoToPageModal(discord.ui.Modal, title="Go to Page"):
    """Modal for jumping to a specific page"""
    
    page_number = discord.ui.TextInput(
        label='Page Number',
        placeholder='Enter page number...',
        required=True,
        max_length=5
    )
    
    def __init__(self, queue_view: PaginatedQueueView):
        super().__init__()
        self.queue_view = queue_view
        self.page_number.label = f'Page Number (1-{queue_view.total_pages})'
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle page jump submission"""
        try:
            target_page = int(self.page_number.value)
            if 1 <= target_page <= self.queue_view.total_pages:
                self.queue_view.current_page = target_page
                await self.queue_view._update_message(interaction)
            else:
                await interaction.response.send_message(
                    f"❌ Invalid page. Enter a number between 1 and {self.queue_view.total_pages}.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

class QueueViewCog(commands.Cog):
    """Cog for managing paginated queue views"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def create_or_update_queue_view(self, queue_line: str):
        """Create or update a paginated queue view in its designated channel."""
        channel_settings = await self.bot.db.get_channel_for_line(queue_line)
        if not (channel_settings and channel_settings['channel_id']):
            return
            
        channel = self.bot.get_channel(channel_settings['channel_id'])
        if not channel:
            return

        view = PaginatedQueueView(self.bot, queue_line)
        await view.update_data()
        view.update_buttons()
        embed = view.create_embed()

        try:
            if channel_settings['pinned_message_id']:
                message = await channel.fetch_message(channel_settings['pinned_message_id'])
                await message.edit(embed=embed, view=view)
                view.message = message
            else:
                await self._create_new_pinned_message(channel, embed, view, queue_line)
        except discord.NotFound:
            await self._create_new_pinned_message(channel, embed, view, queue_line)
        except discord.Forbidden:
            print(f"Missing permissions to update queue view in channel {channel.id} for line {queue_line}.")
        except discord.HTTPException as e:
            print(f"Failed to update queue view for {queue_line}: {e}")
    
    async def _create_new_pinned_message(self, channel, embed, view, queue_line):
        """Create a new pinned message for the queue view."""
        try:
            message = await channel.send(embed=embed, view=view)
            await message.pin(reason="Queue display message")
            await self.bot.db.update_pinned_message(queue_line, message.id)
            view.message = message
        except discord.Forbidden:
            print(f"Missing permissions to pin message in channel {channel.id} for line {queue_line}.")
        except discord.HTTPException as e:
            print(f"Failed to create new pinned message for {queue_line}: {e}")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(QueueViewCog(bot))