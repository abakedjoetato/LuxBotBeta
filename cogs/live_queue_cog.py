# FIXED BY JULES
"""
Live Queue Cog - Manages the public-facing #live-queue channel display.
This cog is now responsible for setting up the persistent QueueView.
"""

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from cogs.queue_view import QueueView

class LiveQueueCog(commands.Cog):
    """Cog for managing the consolidated #live-queue display."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.view_instance: Optional[QueueView] = None

    async def cog_load(self):
        """
        On cog load, find the queue message if it exists and restart the persistent view.
        """
        await self.bot._send_trace("LiveQueueCog cog_load started.")
        live_queue_message_id = self.bot.settings_cache.get('live_queue_message_id')
        live_queue_channel_id = self.bot.settings_cache.get('live_queue_channel_id')

        if live_queue_channel_id and live_queue_message_id:
            try:
                channel = await self.bot.fetch_channel(live_queue_channel_id)
                message = await channel.fetch_message(live_queue_message_id)
                logging.info(f"Re-attaching persistent QueueView to message {message.id} in channel {channel.id}")
                self.view_instance = QueueView(self.bot)
                await self.view_instance.start(message)
            except (discord.NotFound, discord.Forbidden) as e:
                logging.error(f"Failed to re-attach QueueView: {e}. A new queue message must be created with /setup-live-queue.")
            except Exception as e:
                logging.error(f"An unexpected error occurred while re-attaching QueueView: {e}", exc_info=True)


    def cog_unload(self):
        """Clean up listeners when the cog is unloaded."""
        if self.view_instance:
            self.view_instance.cog_unload()

    async def _setup_live_queue_logic(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """The core logic for setting up the live queue channel with the new persistent view."""
        await interaction.response.defer(ephemeral=True)

        # Clean up any old pinned messages from the bot to avoid clutter
        try:
            await channel.purge(limit=5, check=lambda m: m.author == self.bot.user and m.pinned)
        except discord.Forbidden:
            logging.warning(f"Could not purge old pinned messages in {channel.name}. Missing permissions.")
        except Exception as e:
            logging.error(f"Error purging old messages: {e}", exc_info=True)

        # Create a placeholder embed
        placeholder_embed = discord.Embed(title="🎵 Live Queue Order", description="Initializing...", color=discord.Color.light_grey())

        try:
            # Send the initial message
            queue_message = await channel.send(embed=placeholder_embed)
            await queue_message.pin()
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I don't have permission to send messages or pin them in that channel.", ephemeral=True)
            return

        # Save settings to DB
        await self.bot.db.set_bot_config('live_queue_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('live_queue_message_id', message_id=queue_message.id)

        # Update the settings cache
        self.bot.settings_cache['live_queue_channel_id'] = channel.id
        self.bot.settings_cache['live_queue_message_id'] = queue_message.id

        # Stop any old view instance and start a new one
        if self.view_instance:
            self.view_instance.stop()

        self.view_instance = QueueView(self.bot)
        await self.view_instance.start(queue_message) # This will also do the initial update_display

        embed = discord.Embed(title="✅ Live Queue Channel Set", description=f"The public live queue display is now active in {channel.mention}.", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.command(name="setup-live-queue", description="[ADMIN] Set the channel for the public live queue display.")
    @app_commands.describe(channel="The text channel to use for the live queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_live_queue(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets up a persistent, paginated live queue display in the specified channel."""
        await self._setup_live_queue_logic(interaction, channel)

async def setup(bot: commands.Bot):
    await bot.add_cog(LiveQueueCog(bot))