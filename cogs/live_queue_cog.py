"""
Live Queue Cog - Manages the public-facing #live-queue channel display.
"""

import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Optional

class LiveQueueCog(commands.Cog):
    """Cog for managing the consolidated #live-queue display."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.live_queue_channel_id: Optional[int] = None
        self.live_queue_message_id: Optional[int] = None
        # Use asyncio.create_task to avoid awaiting here
        asyncio.create_task(self.bot._send_trace("LiveQueueCog initialized."))
        self.update_live_queue.start()

    async def cog_load(self):
        """Load initial settings on cog load."""
        await self.bot._send_trace("LiveQueueCog cog_load started.")
        # Settings are loaded into a cache on startup. We pull from the cache.
        self.live_queue_channel_id = self.bot.settings_cache.get('live_queue_channel_id')
        self.live_queue_message_id = self.bot.settings_cache.get('live_queue_message_id')
        await self.bot._send_trace(f"LiveQueueCog loaded from cache: channel_id={self.live_queue_channel_id}, message_id={self.live_queue_message_id}")

    def cog_unload(self):
        """Cancel tasks when the cog is unloaded."""
        self.update_live_queue.cancel()

    @app_commands.command(name="setqueuechannel", description="[ADMIN] Set the channel for the public live queue display.")
    @app_commands.describe(channel="The text channel to use for the live queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_queue_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the channel for the live queue and pins the initial message."""
        await interaction.response.defer(ephemeral=True)
        self.live_queue_channel_id = channel.id
        self.live_queue_message_id = None # Force creation of a new message

        # Save settings to DB using separate keys
        await self.bot.db.set_bot_config('live_queue_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('live_queue_message_id', message_id=None)

        # Update the settings cache directly
        self.bot.settings_cache['live_queue_channel_id'] = channel.id
        self.bot.settings_cache['live_queue_message_id'] = None

        # Run immediately to create the message and get its ID
        await self.update_live_queue()

        embed = discord.Embed(title="✅ Live Queue Channel Set", description=f"The public live queue display will now be managed in {channel.mention}.", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="setup-live-queue", description="[ADMIN] Set the channel for the public live queue display.")
    @app_commands.describe(channel="The text channel to use for the live queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_live_queue(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """(Alias for /setqueuechannel) Sets the channel for the live queue."""
        # This command just calls the other command's logic
        await self.set_queue_channel(interaction, channel)

    @tasks.loop(seconds=20)
    async def update_live_queue(self):
        """Periodically fetches the queue and updates the live queue message."""
        if not self.live_queue_channel_id:
            return

        channel = self.bot.get_channel(self.live_queue_channel_id)
        if not channel:
            logging.error(f"Live queue channel {self.live_queue_channel_id} not found.")
            return

        try:
            songs = await self.bot.db.get_all_active_queue_songs()

            embed = discord.Embed(title="🎵 Live Queue Order", description="Here is the upcoming list of songs to be played.", color=discord.Color.dark_purple())
            embed.timestamp = discord.utils.utcnow()

            if not songs:
                embed.description = "The queue is currently empty. Submit a song to get it started!"
            else:
                song_list = []
                for i, song in enumerate(songs[:25], 1): # Display up to 25 songs
                    is_skip = "skip" in song['queue_line'].lower()
                    skip_indicator = " `(Skip)`" if is_skip else ""
                    song_list.append(f"**{i}.** {song['artist_name']} - {song['song_name']}{skip_indicator}")

                embed.description = "\n".join(song_list)
                if len(songs) > 25:
                    embed.set_footer(text=f"...and {len(songs) - 25} more.")

            message_to_edit = None
            if self.live_queue_message_id:
                try:
                    message_to_edit = await channel.fetch_message(self.live_queue_message_id)
                    await message_to_edit.edit(embed=embed)
                except discord.NotFound:
                    self.live_queue_message_id = None # Message was deleted
                except Exception as e:
                    logging.error(f"Error editing live queue message: {e}", exc_info=True)
                    self.live_queue_message_id = None # Assume message is gone

            if not self.live_queue_message_id:
                await channel.purge(limit=5, check=lambda m: m.author == self.bot.user and m.pinned)
                new_message = await channel.send(embed=embed)
                self.live_queue_message_id = new_message.id
                # Save the new message ID to the database with its specific key
                await self.bot.db.set_bot_config('live_queue_message_id', message_id=new_message.id)
                self.bot.settings_cache['live_queue_message_id'] = new_message.id # Update cache
                try:
                    await new_message.pin()
                except discord.Forbidden:
                    logging.warning(f"Could not pin the live queue message in channel {self.live_queue_channel_id}.")

        except Exception as e:
            logging.error(f"Failed to update live queue display: {e}", exc_info=True)

    @update_live_queue.before_loop
    async def before_update_live_queue(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(LiveQueueCog(bot))