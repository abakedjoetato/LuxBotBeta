# FIXED BY JULES
"""
Reviewer Cog - Manages the persistent views for the reviewer channel.
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

# --- View Classes (Simplified and Stateless) ---

class ReviewerMainQueueView(discord.ui.View):
    """A stateless view for the main reviewer queue. Delegates actions to the cog."""
    def __init__(self, cog: 'ReviewerCog'):
        super().__init__(timeout=None)
        self.cog = cog
        self.previous_button.custom_id = "reviewer_main_queue_prev"
        self.next_button.custom_id = "reviewer_main_queue_next"
        self.refresh_button.custom_id = "reviewer_main_queue_refresh"

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_main_queue_display(interaction=interaction, page_offset=-1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_main_queue_display(interaction=interaction, page_offset=1)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_main_queue_display(interaction=interaction, reset_page=True)


class PendingSkipsView(discord.ui.View):
    """A stateless view for the pending skips queue. Delegates actions to the cog."""
    def __init__(self, cog: 'ReviewerCog'):
        super().__init__(timeout=None)
        self.cog = cog
        self.previous_button.custom_id = "pending_skips_queue_prev"
        self.next_button.custom_id = "pending_skips_queue_next"
        self.refresh_button.custom_id = "pending_skips_queue_refresh"

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_pending_skips_display(interaction=interaction, page_offset=-1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_pending_skips_display(interaction=interaction, page_offset=1)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.update_pending_skips_display(interaction=interaction, reset_page=True)


# --- Cog Implementation (Manages State and Logic) ---

class ReviewerCog(commands.Cog):
    """Cog for setting up and managing the reviewer channel views."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.main_queue_message: Optional[discord.Message] = None
        self.pending_skips_message: Optional[discord.Message] = None
        self.main_queue_page = 0
        self.pending_skips_page = 0

    async def cog_load(self):
        """On cog load, register persistent views and find the queue messages if they exist."""
        await self.bot._send_trace("ReviewerCog cog_load started.")
        
        # FIXED BY Replit: Register persistent views for this cog
        self.bot.add_view(ReviewerMainQueueView(self))
        self.bot.add_view(PendingSkipsView(self))
        await self.bot._send_trace("Registered ReviewerCog persistent views.")
        
        channel_id = self.bot.settings_cache.get('reviewer_channel_id')
        if not channel_id:
            return

        try:
            channel = await self.bot.fetch_channel(channel_id)

            main_id = self.bot.settings_cache.get('reviewer_main_queue_message_id')
            if main_id:
                self.main_queue_message = await channel.fetch_message(main_id)

            pending_id = self.bot.settings_cache.get('reviewer_pending_skips_message_id')
            if pending_id:
                self.pending_skips_message = await channel.fetch_message(pending_id)

            logging.info("Successfully loaded reviewer message objects.")
        except (discord.NotFound, discord.Forbidden) as e:
            logging.error(f"Failed to load reviewer messages on startup: {e}. A new setup is required.")
        except Exception as e:
            logging.error(f"An unexpected error occurred loading reviewer messages: {e}", exc_info=True)

    @commands.Cog.listener('on_queue_update')
    async def on_queue_update(self):
        """Listener for the custom queue update event."""
        logging.info("ReviewerCog received queue_update event. Refreshing displays.")
        await self.update_main_queue_display(reset_page=True)
        await self.update_pending_skips_display(reset_page=True)

    # --- Main Queue Display Logic ---
    async def update_main_queue_display(self, interaction: Optional[discord.Interaction] = None, page_offset: int = 0, reset_page: bool = False):
        if not self.main_queue_message:
            return

        if reset_page:
            self.main_queue_page = 0
        else:
            self.main_queue_page += page_offset

        queue_data = await self.bot.db.get_all_active_queue_songs(detailed=True)
        total_pages = math.ceil(len(queue_data) / 10) or 1
        self.main_queue_page = max(0, min(self.main_queue_page, total_pages - 1))

        embed = discord.Embed(title="[Reviewer] Main Active Queue", color=discord.Color.orange())
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The main queue is empty."
        else:
            start_index = self.main_queue_page * 10
            page_items = queue_data[start_index : start_index + 10]

            song_list = []
            for i, song in enumerate(page_items, start=start_index + 1):
                score = f"**Score:** {song['total_score']:.0f} | " if song['queue_line'] == QueueLine.FREE.value else ""
                submitter = f"**By:** {song['username']} (`{song['tiktok_username'] or 'N/A'}`)"
                song_list.append(f"**{i}.** `#{song['public_id']}` {song['artist_name']} - {song['song_name']} `({song['queue_line']})`\n> {score}{submitter}")
            embed.description = "\n".join(song_list)

        embed.set_footer(text=f"Page {self.main_queue_page + 1}/{total_pages} | Total Songs: {len(queue_data)}")

        view = ReviewerMainQueueView(self)
        view.previous_button.disabled = self.main_queue_page == 0
        view.next_button.disabled = self.main_queue_page >= total_pages - 1

        if interaction:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self.main_queue_message.edit(embed=embed, view=view)

    # --- Pending Skips Display Logic ---
    async def update_pending_skips_display(self, interaction: Optional[discord.Interaction] = None, page_offset: int = 0, reset_page: bool = False):
        if not self.pending_skips_message:
            return

        if reset_page:
            self.pending_skips_page = 0
        else:
            self.pending_skips_page += page_offset

        queue_data = await self.bot.db.get_queue_submissions(QueueLine.PENDING_SKIPS.value)
        total_pages = math.ceil(len(queue_data) / 10) or 1
        self.pending_skips_page = max(0, min(self.pending_skips_page, total_pages - 1))

        embed = discord.Embed(title="[Reviewer] Pending Skips Queue", color=discord.Color.blue())
        embed.timestamp = discord.utils.utcnow()

        if not queue_data:
            embed.description = "The pending skips queue is empty."
        else:
            start_index = self.pending_skips_page * 10
            page_items = queue_data[start_index : start_index + 10]
            song_list = [f"**{i}.** `#{song['public_id']}` {song['artist_name']} - {song['song_name']}\n> **By:** {song['username']} (`{song['tiktok_username'] or 'N/A'}`)" for i, song in enumerate(page_items, start=start_index + 1)]
            embed.description = "\n".join(song_list)

        embed.set_footer(text=f"Page {self.pending_skips_page + 1}/{total_pages} | Total Pending: {len(queue_data)}")

        view = PendingSkipsView(self)
        view.previous_button.disabled = self.pending_skips_page == 0
        view.next_button.disabled = self.pending_skips_page >= total_pages - 1

        if interaction:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self.pending_skips_message.edit(embed=embed, view=view)

    @app_commands.command(name="setup-reviewer-channel", description="[ADMIN] Sets up the two persistent queue views for reviewers.")
    @app_commands.describe(channel="The text channel to use for the reviewer views.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_reviewer_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets up the main queue and pending skips views in the specified channel."""
        await interaction.response.defer(ephemeral=True)

        try:
            await channel.purge(limit=10, check=lambda m: m.author == self.bot.user)
        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I need 'Manage Messages' permission.", ephemeral=True)
            return

        try:
            # Post Main Queue View
            main_embed = discord.Embed(title="[Reviewer] Main Active Queue", description="Initializing...", color=discord.Color.light_grey())
            self.main_queue_message = await channel.send(embed=main_embed, view=ReviewerMainQueueView(self))

            # Post Pending Skips View
            pending_embed = discord.Embed(title="[Reviewer] Pending Skips Queue", description="Initializing...", color=discord.Color.light_grey())
            self.pending_skips_message = await channel.send(embed=pending_embed, view=PendingSkipsView(self))

        except discord.Forbidden:
            await interaction.followup.send("❌ **Error:** I don't have permission to send messages in that channel.", ephemeral=True)
            return

        # Save settings
        await self.bot.db.set_bot_config('reviewer_channel_id', channel_id=channel.id)
        await self.bot.db.set_bot_config('reviewer_main_queue_message_id', message_id=self.main_queue_message.id)
        await self.bot.db.set_bot_config('reviewer_pending_skips_message_id', message_id=self.pending_skips_message.id)
        self.bot.settings_cache['reviewer_channel_id'] = channel.id
        self.bot.settings_cache['reviewer_main_queue_message_id'] = self.main_queue_message.id
        self.bot.settings_cache['reviewer_pending_skips_message_id'] = self.pending_skips_message.id

        # Initial update
        await self.update_main_queue_display(reset_page=True)
        await self.update_pending_skips_display(reset_page=True)

        await interaction.followup.send(f"✅ Reviewer views have been successfully set up in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewerCog(bot))