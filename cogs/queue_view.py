# FIXED BY JULES
"""
This file contains the persistent, paginated, and auto-updating view for the live queue.
"""

import discord
import math
import logging
from typing import List, Dict, Any

class QueueView(discord.ui.View):
    """
    A persistent view for displaying the live song queue with pagination and auto-refresh.
    It listens for a 'queue_update' event dispatched by the bot to refresh its state.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.current_page = 0
        self.page_size = 10
        self.total_pages = 0
        self.message: discord.Message = None

    async def start(self, message: discord.Message):
        """Starts the view and sets the message it's attached to."""
        self.message = message
        self.bot.add_view(self)
        self.bot.add_listener(self.on_queue_update, 'on_queue_update')
        await self.update_display()

    def cog_unload(self):
        """Remove the listener when the cog unloads."""
        self.bot.remove_listener(self.on_queue_update, 'on_queue_update')

    async def on_queue_update(self):
        """Listener for the custom queue update event."""
        logging.info("QueueView received queue_update event. Refreshing display.")
        # Reset to the first page on any update to ensure freshness
        self.current_page = 0
        if self.message:
            await self.update_display()

    async def get_queue_data(self) -> List[Dict[str, Any]]:
        """Fetches and caches the latest queue data."""
        return await self.bot.db.get_all_active_queue_songs()

    def create_embed(self, queue_data: List[Dict[str, Any]]) -> discord.Embed:
        """Creates the embed for the current page of the queue."""
        self.total_pages = math.ceil(len(queue_data) / self.page_size)
        if self.total_pages == 0:
            self.total_pages = 1

        embed = discord.Embed(
            title="🎵 Live Queue Order",
            color=discord.Color.dark_purple()
        )
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The queue is currently empty. Submit a song to get it started!"
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            start_index = self.current_page * self.page_size
            end_index = start_index + self.page_size
            page_items = queue_data[start_index:end_index]

            song_list = []
            for i, song in enumerate(page_items, start=start_index + 1):
                is_skip = "skip" in song['queue_line'].lower()
                skip_indicator = " `(Skip)`" if is_skip else ""
                song_list.append(f"**{i}.** {song['artist_name']} - {song['song_name']}{skip_indicator} `(by {song['username']})`")

            embed.description = "\n".join(song_list)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Total Songs: {len(queue_data)}")

            self.previous_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page >= self.total_pages - 1

        return embed

    async def update_display(self):
        """Fetches data, creates the embed, and updates the message."""
        if not self.message:
            logging.warning("QueueView cannot update display because its message is not set.")
            return

        queue_data = await self.get_queue_data()
        embed = self.create_embed(queue_data)
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.NotFound:
            logging.error(f"Failed to edit queue message ({self.message.id}) because it was not found.")
            self.stop()
        except Exception as e:
            logging.error(f"Error updating queue display: {e}", exc_info=True)

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey, custom_id="queue_prev_page")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await interaction.response.defer()
        await self.update_display()

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey, custom_id="queue_next_page")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await interaction.response.defer()
        await self.update_display()

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄", custom_id="queue_refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.update_display()