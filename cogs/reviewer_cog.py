# FIXED BY JULES
"""
Reviewer Cog - Manages the persistent views for the reviewer channel.
This includes two separate, auto-updating views: one for the main active queue
and one for the pending skips queue.
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
        self.current_page = 0  # Reset to first page on update
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


# --- Concrete View Implementations ---

class ReviewerMainQueueView(BasePaginatorView):
    """A persistent view for the main reviewer queue (all active songs)."""
    def __init__(self, bot):
        super().__init__(bot, "reviewer_main_queue")

    async def get_queue_data(self) -> List[Dict[str, Any]]:
        return await self.bot.db.get_all_active_queue_songs(detailed=True)

    def create_embed(self, queue_data: List[Dict[str, Any]]) -> discord.Embed:
        self.total_pages = math.ceil(len(queue_data) / self.page_size) or 1
        embed = discord.Embed(title="[Reviewer] Main Active Queue", color=discord.Color.orange())
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The main queue is empty."
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            start_index = self.current_page * self.page_size
            end_index = start_index + self.page_size
            page_items = queue_data[start_index:end_index]

            song_list = []
            for i, song in enumerate(page_items, start=start_index + 1):
                score = f"**Score:** {song['total_score']:.0f} | " if song['queue_line'] == QueueLine.FREE.value else ""
                submitter = f"**By:** {song['username']} (`{song['tiktok_username'] or 'N/A'}`)"
                song_list.append(f"**{i}.** `#{song['public_id']}` {song['artist_name']} - {song['song_name']} `({song['queue_line']})`\n> {score}{submitter}")

            embed.description = "\n".join(song_list)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Total Songs: {len(queue_data)}")
            self.previous_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page >= self.total_pages - 1

        return embed


class PendingSkipsView(BasePaginatorView):
    """A persistent view for the 'Pending Skips' queue."""
    def __init__(self, bot):
        super().__init__(bot, "pending_skips_queue")

    async def get_queue_data(self) -> List[Dict[str, Any]]:
        return await self.bot.db.get_queue_submissions(QueueLine.PENDING_SKIPS.value)

    def create_embed(self, queue_data: List[Dict[str, Any]]) -> discord.Embed:
        self.total_pages = math.ceil(len(queue_data) / self.page_size) or 1
        embed = discord.Embed(title="[Reviewer] Pending Skips Queue", color=discord.Color.blue())
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The pending skips queue is empty."
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            start_index = self.current_page * self.page_size
            end_index = start_index + self.page_size
            page_items = queue_data[start_index:end_index]

            song_list = []
            for i, song in enumerate(page_items, start=start_index + 1):
                 submitter = f"**By:** {song['username']} (`{song['tiktok_username'] or 'N/A'}`)"
                 song_list.append(f"**{i}.** `#{song['public_id']}` {song['artist_name']} - {song['song_name']}\n> {submitter}")

            embed.description = "\n".join(song_list)
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Total Pending: {len(queue_data)}")
            self.previous_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page >= self.total_pages - 1

        return embed


# --- Cog Implementation ---

class ReviewerCog(commands.Cog):
    """Cog for setting up and managing the reviewer channel views."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.main_queue_view = ReviewerMainQueueView(bot)
        self.pending_skips_view = PendingSkipsView(bot)

    async def cog_load(self):
        """On cog load, find the queue messages if they exist and restart the persistent views."""
        await self.bot._send_trace("ReviewerCog cog_load started.")

        main_queue_msg_id = self.bot.settings_cache.get('reviewer_main_queue_message_id')
        pending_skips_msg_id = self.bot.settings_cache.get('reviewer_pending_skips_message_id')
        channel_id = self.bot.settings_cache.get('reviewer_channel_id')

        if not channel_id:
            return

        try:
            channel = await self.bot.fetch_channel(channel_id)

            if main_queue_msg_id:
                main_message = await channel.fetch_message(main_queue_msg_id)
                await self.main_queue_view.start(main_message)
                logging.info(f"Re-attached ReviewerMainQueueView to message {main_message.id}")

            if pending_skips_msg_id:
                pending_message = await channel.fetch_message(pending_skips_msg_id)
                await self.pending_skips_view.start(pending_message)
                logging.info(f"Re-attached PendingSkipsView to message {pending_message.id}")

        except (discord.NotFound, discord.Forbidden) as e:
            logging.error(f"Failed to re-attach reviewer views: {e}. A new setup is required.")
        except Exception as e:
            logging.error(f"An unexpected error occurred re-attaching reviewer views: {e}", exc_info=True)

    def cog_unload(self):
        """Unload listeners when the cog is removed."""
        self.main_queue_view.cog_unload()
        self.pending_skips_view.cog_unload()

    @app_commands.command(name="setup-reviewer-channel", description="[ADMIN] Sets up the two persistent queue views for reviewers.")
    @app_commands.describe(channel="The text channel to use for the reviewer views.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_reviewer_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets up the main queue and pending skips views in the specified channel."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Purge old bot messages to keep the channel clean
            await channel.purge(limit=10, check=lambda m: m.author == self.bot.user)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I need permission to 'Manage Messages' to clean up the channel first.", ephemeral=True)
            return
        except Exception as e:
            logging.error(f"Error purging reviewer channel: {e}", exc_info=True)

        try:
            # Post Main Queue View
            main_embed = discord.Embed(title="[Reviewer] Main Active Queue", description="Initializing...", color=discord.Color.light_grey())
            main_message = await channel.send(embed=main_embed)

            # Post Pending Skips View
            pending_embed = discord.Embed(title="[Reviewer] Pending Skips Queue", description="Initializing...", color=discord.Color.light_grey())
            pending_message = await channel.send(embed=pending_embed)

        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I don't have permission to send messages in that channel.", ephemeral=True)
            return

        # Save settings to DB
        await self.bot.db.set_bot_config('reviewer_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('reviewer_main_queue_message_id', message_id=main_message.id)
        await self.bot.db.set_bot_config('reviewer_pending_skips_message_id', message_id=pending_message.id)

        # Update cache
        self.bot.settings_cache['reviewer_channel_id'] = channel.id
        self.bot.settings_cache['reviewer_main_queue_message_id'] = main_message.id
        self.bot.settings_cache['reviewer_pending_skips_message_id'] = pending_message.id

        # Start the views
        await self.main_queue_view.start(main_message)
        await self.pending_skips_view.start(pending_message)

        await interaction.followup.send(f"✅ Reviewer views have been successfully set up in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewerCog(bot))