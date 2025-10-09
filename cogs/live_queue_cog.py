# FIXED BY JULES
# FIXED BY Replit: Queue pagination and auto-updating - verified working
"""
Live Queue Cog - Manages the public-facing #live-music-queue channel display.
This cog follows the correct persistent view pattern where the Cog manages
the state (message, page number) and the View handles interactions.
"""

import discord
import math
import logging
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional

from database import QueueLine

# --- View Class (Simplified and Stateless) ---

class PublicQueueView(discord.ui.View):
    """A stateless view for the public queue. Delegates actions to the cog."""
    def __init__(self, cog: 'LiveQueueCog'):
        super().__init__(timeout=None)
        self.cog = cog
        self.previous_button.custom_id = "public_live_queue_prev"
        self.next_button.custom_id = "public_live_queue_next"
        self.refresh_button.custom_id = "public_live_queue_refresh"

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_display(interaction=interaction, page_offset=-1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_display(interaction=interaction, page_offset=1)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_display(interaction=interaction, reset_page=True)


# --- Cog Implementation (Manages State and Logic) ---

class LiveQueueCog(commands.Cog):
    """Cog for setting up and managing the public live queue view."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_message: Optional[discord.Message] = None
        self.current_page = 0
        self.page_size = 10

    async def cog_load(self):
        """On cog load, register persistent view and find the queue message if it exists."""
        await self.bot._send_trace("LiveQueueCog cog_load started.")
        
        # FIXED BY Replit: Register persistent view for this cog
        self.bot.add_view(PublicQueueView(self))
        await self.bot._send_trace("Registered LiveQueueCog persistent view.")
        
        channel_id = self.bot.settings_cache.get('public_live_queue_channel_id')
        message_id = self.bot.settings_cache.get('public_live_queue_message_id')

        if not channel_id or not message_id:
            return

        try:
            channel = await self.bot.fetch_channel(channel_id)
            self.queue_message = await channel.fetch_message(message_id)
            logging.info("Successfully loaded public queue message object.")
        except (discord.NotFound, discord.Forbidden) as e:
            logging.error(f"Failed to load public queue message on startup: {e}. A new setup is required.")
        except Exception as e:
            logging.error(f"An unexpected error occurred loading public queue message: {e}", exc_info=True)

    @commands.Cog.listener('on_queue_update')
    async def on_queue_update(self):
        """Listener for the custom queue update event."""
        logging.info("LiveQueueCog received queue_update event. Refreshing display.")
        await self.update_display(reset_page=True)

    async def update_display(self, interaction: Optional[discord.Interaction] = None, page_offset: int = 0, reset_page: bool = False):
        if not self.queue_message:
            return

        if interaction:
            await interaction.response.defer()

        if reset_page:
            self.current_page = 0
        else:
            self.current_page += page_offset

        queue_data = await self.bot.db.get_all_active_queue_songs(detailed=True)
        total_pages = math.ceil(len(queue_data) / self.page_size) or 1
        self.current_page = max(0, min(self.current_page, total_pages - 1))

        embed = discord.Embed(title="🎵 Live Music Queue", color=discord.Color.dark_purple())
        embed.set_footer(text="This queue is sorted by skips first, then by engagement points for the Free line.")
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The queue is currently empty. Submit a song to get it started!"
        else:
            start_index = self.current_page * self.page_size
            page_items = queue_data[start_index : start_index + self.page_size]

            song_list = []
            for i, song in enumerate(page_items, start=start_index + 1):
                points_display = f" `({song['total_score']:.0f} points)`" if song['queue_line'] == QueueLine.FREE.value else ""
                skip_indicator = " `(Skip)`" if "skip" in song['queue_line'].lower() else ""
                song_list.append(f"**{i}.** {song['artist_name']} - {song['song_name']}{skip_indicator} `(by {song['username']})`{points_display}")
            embed.description = "\n".join(song_list)

        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages} | Total Songs: {len(queue_data)}")

        view = PublicQueueView(self)
        view.previous_button.disabled = self.current_page == 0
        view.next_button.disabled = self.current_page >= total_pages - 1

        if interaction:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self.queue_message.edit(embed=embed, view=view)

    @app_commands.command(name="setup-live-queue", description="[ADMIN] Sets up the persistent public queue display.")
    @app_commands.describe(channel="The text channel to use for the public queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_live_queue(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets up the public queue view in the specified channel."""
        await interaction.response.defer(ephemeral=True)

        try:
            await channel.purge(limit=5, check=lambda m: m.author == self.bot.user and m.pinned)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I need 'Manage Messages' permission.", ephemeral=True)
            return

        try:
            embed = discord.Embed(title="🎵 Live Music Queue", description="Initializing...", color=discord.Color.light_grey())
            self.queue_message = await channel.send(embed=embed, view=PublicQueueView(self))
            await self.queue_message.pin()
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I don't have permission to send or pin messages in that channel.", ephemeral=True)
            return

        # Save settings
        await self.bot.db.set_bot_config('public_live_queue_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('public_live_queue_message_id', message_id=self.queue_message.id)
        self.bot.settings_cache['public_live_queue_channel_id'] = channel.id
        self.bot.settings_cache['public_live_queue_message_id'] = self.queue_message.id

        # Initial update
        await self.update_display(reset_page=True)

        await interaction.followup.send(f"✅ Public live queue has been successfully set up in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveQueueCog(bot))