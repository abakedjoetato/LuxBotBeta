# FIXED BY JULES
"""
Live Queue Cog - Manages the public-facing #live-music-queue channel display.
This cog is responsible for setting up and managing a single, persistent,
paginated view that shows the consolidated play order and user engagement points.
"""

import discord
import math
import logging
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional

from database import QueueLine

# --- Base View for Shared Logic ---

class BasePaginatorView(discord.ui.View):
    """Base class for persistent, paginated, and auto-updating views."""
    def __init__(self, bot, custom_id_prefix: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.current_page = 0
        self.page_size = 10
        self.total_pages = 0
        self.message: Optional[discord.Message] = None
        self.custom_id_prefix = custom_id_prefix

        # Dynamically set custom_ids for buttons
        self.previous_button.custom_id = f"{self.custom_id_prefix}_prev"
        self.next_button.custom_id = f"{self.custom_id_prefix}_next"
        self.refresh_button.custom_id = f"{self.custom_id_prefix}_refresh"

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
        logging.info(f"View ({self.custom_id_prefix}) received queue_update event. Refreshing display.")
        self.current_page = 0
        if self.message:
            await self.update_display()

    async def get_queue_data(self) -> List[Dict[str, Any]]:
        """Placeholder for fetching data. Must be implemented by subclasses."""
        raise NotImplementedError("get_queue_data must be implemented in a subclass.")

    def create_embed(self, queue_data: List[Dict[str, Any]]) -> discord.Embed:
        """Placeholder for creating the embed. Must be implemented by subclasses."""
        raise NotImplementedError("create_embed must be implemented in a subclass.")

    async def update_display(self):
        """Fetches data, creates the embed, and updates the message."""
        if not self.message:
            logging.warning(f"View ({self.custom_id_prefix}) cannot update display: message not set.")
            return

        queue_data = await self.get_queue_data()
        embed = self.create_embed(queue_data)
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.NotFound:
            logging.error(f"Failed to edit message {self.message.id} for view {self.custom_id_prefix}: Not Found.")
            self.stop()
        except Exception as e:
            logging.error(f"Error updating display for view {self.custom_id_prefix}: {e}", exc_info=True)

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await interaction.response.defer()
        await self.update_display()

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await interaction.response.defer()
        await self.update_display()

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page = 0
        await self.update_display()


# --- Public Queue View ---

class PublicQueueView(BasePaginatorView):
    """A persistent view for the public-facing live music queue."""
    def __init__(self, bot):
        super().__init__(bot, "public_live_queue")

    async def get_queue_data(self) -> List[Dict[str, Any]]:
        # Use the detailed flag to get the total_score
        return await self.bot.db.get_all_active_queue_songs(detailed=True)

    def create_embed(self, queue_data: List[Dict[str, Any]]) -> discord.Embed:
        self.total_pages = math.ceil(len(queue_data) / self.page_size) or 1
        embed = discord.Embed(title="🎵 Live Music Queue", color=discord.Color.dark_purple())
        embed.set_footer(text="This queue is sorted by skips first, then by engagement points for the Free line.")
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
                # Display engagement points for the Free line
                points_display = f" `({song['total_score']:.0f} points)`" if song['queue_line'] == QueueLine.FREE.value else ""
                skip_indicator = " `(Skip)`" if "skip" in song['queue_line'].lower() else ""

                # Construct the entry string
                song_list.append(f"**{i}.** {song['artist_name']} - {song['song_name']}{skip_indicator} `(by {song['username']})`{points_display}")

            embed.description = "\n".join(song_list)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Total Songs: {len(queue_data)}")
            self.previous_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page >= self.total_pages - 1

        return embed


# --- Cog Implementation ---

class LiveQueueCog(commands.Cog):
    """Cog for setting up and managing the public live queue view."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.public_view = PublicQueueView(bot)

    async def cog_load(self):
        """On cog load, find the queue message if it exists and restart the persistent view."""
        await self.bot._send_trace("LiveQueueCog cog_load started.")

        message_id = self.bot.settings_cache.get('public_live_queue_message_id')
        channel_id = self.bot.settings_cache.get('public_live_queue_channel_id')

        if not channel_id or not message_id:
            return

        try:
            channel = await self.bot.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            await self.public_view.start(message)
            logging.info(f"Re-attached PublicQueueView to message {message.id}")
        except (discord.NotFound, discord.Forbidden) as e:
            logging.error(f"Failed to re-attach public queue view: {e}. A new setup is required.")
        except Exception as e:
            logging.error(f"An unexpected error occurred re-attaching public queue view: {e}", exc_info=True)

    def cog_unload(self):
        """Unload listeners when the cog is removed."""
        self.public_view.cog_unload()

    @app_commands.command(name="setup-live-queue", description="[ADMIN] Sets up the persistent public queue display.")
    @app_commands.describe(channel="The text channel to use for the public queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_live_queue(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets up the public queue view in the specified channel."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Purge old bot messages to keep the channel clean
            await channel.purge(limit=5, check=lambda m: m.author == self.bot.user and m.pinned)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I need permission to 'Manage Messages' to clean up the channel first.", ephemeral=True)
            return
        except Exception as e:
            logging.error(f"Error purging public queue channel: {e}", exc_info=True)

        try:
            embed = discord.Embed(title="🎵 Live Music Queue", description="Initializing...", color=discord.Color.light_grey())
            message = await channel.send(embed=embed)
            await message.pin()
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I don't have permission to send or pin messages in that channel.", ephemeral=True)
            return

        # Save settings to DB with new keys
        await self.bot.db.set_bot_config('public_live_queue_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('public_live_queue_message_id', message_id=message.id)

        # Update cache
        self.bot.settings_cache['public_live_queue_channel_id'] = channel.id
        self.bot.settings_cache['public_live_queue_message_id'] = message.id

        # Start the view
        await self.public_view.start(message)

        await interaction.followup.send(f"✅ Public live queue has been successfully set up in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveQueueCog(bot))