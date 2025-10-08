"""
Reviewer Queue Cog
Handles the display of a detailed, persistent queue for staff review.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import List, Dict, Optional, Any

from database import Database, QueueLine

ITEMS_PER_PAGE = 10

class ReviewerView(discord.ui.View):
    """A persistent, paginated view for the main reviewer queue."""
    def __init__(self, db: Database):
        super().__init__(timeout=None)
        self.db = db
        self.current_page = 0

    async def generate_embed(self) -> discord.Embed:
        """Generates the embed for the current page."""
        submissions = await self.db.get_all_active_queue_songs(detailed=True)

        if not submissions:
            self.cleanup_buttons()
            return discord.Embed(title="Reviewer Queue", description="The queue is currently empty.", color=discord.Color.blue())

        total_pages = (len(submissions) - 1) // ITEMS_PER_PAGE
        self.current_page = max(0, min(self.current_page, total_pages))

        start_index = self.current_page * ITEMS_PER_PAGE
        end_index = start_index + ITEMS_PER_PAGE
        page_submissions = submissions[start_index:end_index]

        embed = discord.Embed(title=f"Live Reviewer Queue (Page {self.current_page + 1}/{total_pages + 1})", color=discord.Color.dark_purple())
        description = ""
        for sub in page_submissions:
            stats = await self.db.get_user_lifetime_stats(sub['user_id'])
            stats_line = f"👍{stats['like']} 💬{stats['comment']} 🔗{stats['share']} 🪙{stats['gift_coins']}"
            entry = (
                f"**#{sub['public_id']} | {sub['artist_name']} - {sub['song_name']}**\n"
                f"> **Submitter:** {sub['username']} (`{sub['user_id']}`)\n"
                f"> **Queue:** `{sub['queue_line']}` | **Score:** `{sub.get('total_score', 0)}`\n"
            )
            if sub.get('tiktok_username'):
                entry += f"> **TikTok:** `{sub['tiktok_username']}`\n"
            entry += f"> **Lifetime Stats:** {stats_line}\n"
            if sub['link_or_file'].startswith("http"):
                entry += f"> **Link:** [Click Here]({sub['link_or_file']})\n"
            if sub.get('note'):
                entry += f"> **Note:** *{sub['note']}*\n"
            entry += "---\n"
            description += entry

        embed.description = description
        embed.set_footer(text="Use the buttons to navigate or refresh.")
        embed.timestamp = discord.utils.utcnow()

        self.update_button_states(total_pages)
        return embed

    def cleanup_buttons(self):
        """Disables all buttons."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def update_button_states(self, total_pages: int):
        """Enables/disables buttons based on the current page."""
        self.prev_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= total_pages

    async def update_message(self, interaction: discord.Interaction):
        """Updates the message with the new embed and view state."""
        embed = await self.generate_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="< Prev", style=discord.ButtonStyle.primary, custom_id="rq_prev_page")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.success, custom_id="rq_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction)

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.primary, custom_id="rq_next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.update_message(interaction)

class PendingSkipsView(discord.ui.View):
    """A persistent, paginated view for the pending skips queue."""
    def __init__(self, db: Database):
        super().__init__(timeout=None)
        self.db = db
        self.current_page = 0

    async def generate_embed(self) -> discord.Embed:
        """Generates the embed for the current page."""
        submissions = await self.db.get_queue_submissions(QueueLine.PENDING_SKIPS.value)

        if not submissions:
            self.cleanup_buttons()
            return discord.Embed(title="Pending Skips Queue", description="The queue is currently empty.", color=discord.Color.blue())

        total_pages = (len(submissions) - 1) // ITEMS_PER_PAGE
        self.current_page = max(0, min(self.current_page, total_pages))

        start_index = self.current_page * ITEMS_PER_PAGE
        end_index = start_index + ITEMS_PER_PAGE
        page_submissions = submissions[start_index:end_index]

        embed = discord.Embed(title=f"Pending Skips Queue (Page {self.current_page + 1}/{total_pages + 1})", color=discord.Color.orange())
        description = ""
        for sub in page_submissions:
            stats = await self.db.get_user_lifetime_stats(sub['user_id'])
            stats_line = f"👍{stats['like']} 💬{stats['comment']} 🔗{stats['share']} 🪙{stats['gift_coins']}"
            entry = (
                f"**#{sub['public_id']} | {sub['artist_name']} - {sub['song_name']}**\n"
                f"> **Submitter:** {sub['username']} (`{sub['user_id']}`)\n"
            )
            if sub.get('tiktok_username'):
                entry += f"> **TikTok:** `{sub['tiktok_username']}`\n"
            entry += f"> **Lifetime Stats:** {stats_line}\n"
            if sub['link_or_file'].startswith("http"):
                entry += f"> **Link:** [Click Here]({sub['link_or_file']})\n"
            if sub.get('note'):
                entry += f"> **Note:** *{sub['note']}*\n"
            entry += "---\n"
            description += entry

        embed.description = description
        embed.set_footer(text="Use the buttons to navigate or refresh.")
        embed.timestamp = discord.utils.utcnow()

        self.update_button_states(total_pages)
        return embed

    def cleanup_buttons(self):
        """Disables all buttons."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def update_button_states(self, total_pages: int):
        """Enables/disables buttons based on the current page."""
        self.prev_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= total_pages

    async def update_message(self, interaction: discord.Interaction):
        """Updates the message with the new embed and view state."""
        embed = await self.generate_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="< Prev", style=discord.ButtonStyle.primary, custom_id="psq_prev_page")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.success, custom_id="psq_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_message(interaction)

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.primary, custom_id="psq_next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.update_message(interaction)

class ReviewerQueueCog(commands.Cog):
    """A cog for managing the detailed reviewer queue display."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db
        # Register the persistent views
        bot.add_view(ReviewerView(bot.db))
        bot.add_view(PendingSkipsView(bot.db))

    def cog_unload(self):
        # No tasks to cancel anymore
        pass

    @app_commands.command(name="setreviewerchannel", description="[ADMIN] Sets the channel for the detailed reviewer queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_reviewer_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the channel for the reviewer queue message."""
        # Purge old bot messages in the channel
        await channel.purge(limit=10, check=lambda m: m.author == self.bot.user)

        view = ReviewerView(self.db)
        embed = await view.generate_embed()

        message = await channel.send(embed=embed, view=view)

        await self.db.set_bot_config('reviewer_queue_channel_id', channel_id=channel.id)
        await self.db.set_bot_config('reviewer_queue_message_id', message_id=message.id)
        self.bot.settings_cache['reviewer_queue_channel_id'] = channel.id
        self.bot.settings_cache['reviewer_queue_message_id'] = message.id

        response_embed = discord.Embed(title="✅ Reviewer Queue Channel Set", description=f"The reviewer queue has been set up in {channel.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=response_embed, ephemeral=True)

    @app_commands.command(name="setpendingskipschannel", description="[ADMIN] Sets the channel for the pending skips queue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_pending_skips_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the channel for the pending skips queue message."""
        # Purge old bot messages in the channel
        await channel.purge(limit=10, check=lambda m: m.author == self.bot.user)

        view = PendingSkipsView(self.db)
        embed = await view.generate_embed()

        message = await channel.send(embed=embed, view=view)

        await self.db.set_bot_config('pending_skips_channel_id', channel_id=channel.id)
        await self.db.set_bot_config('pending_skips_message_id', message_id=message.id)
        self.bot.settings_cache['pending_skips_channel_id'] = channel.id
        self.bot.settings_cache['pending_skips_message_id'] = message.id

        response_embed = discord.Embed(title="✅ Pending Skips Channel Set", description=f"The pending skips queue has been set up in {channel.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=response_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewerQueueCog(bot))