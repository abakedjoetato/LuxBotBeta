"""
Queue View - Paginated queue display system with Discord Views
"""

import discord
from discord.ext import commands
import math
from typing import List, Dict, Any, Optional
from database import QueueLine
import datetime

# A unique identifier for our queue view messages
QUEUE_VIEW_EMBED_FOOTER_ID = "Luxurious_Radio_Queue_View_v1"

class PaginatedQueueView(discord.ui.View):
    """Discord View for paginated queue display with navigation buttons"""
    
    def __init__(self, bot, queue_line: str, entries_per_page: int = 10):
        super().__init__(timeout=None)  # Never timeout
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
                # Determine which timestamp to use
                is_songs_played = self.queue_line == QueueLine.SONGS_PLAYED.value
                time_to_display = sub.get('played_time') if is_songs_played else sub.get('submission_time')
                time_prefix = "Played" if is_songs_played else "Submitted"

                timestamp_str = ""
                if time_to_display:
                    try:
                        ts = datetime.datetime.fromisoformat(time_to_display)
                        timestamp_str = f" ({time_prefix} <t:{int(ts.timestamp())}:R>)"
                    except (ValueError, TypeError):
                        pass # Keep timestamp_str empty if parsing fails

                tiktok_str = ""
                if sub.get('tiktok_username'):
                    # Escape underscores in the username to prevent unintended markdown italics
                    escaped_tiktok_user = sub['tiktok_username'].replace('_', r'\_')
                    tiktok_str = f" (TikTok: *{escaped_tiktok_user}*)"

                description_lines.append(
                    f"**{i}.** `#{sub['public_id']}`: **{sub['artist_name']} – {sub['song_name']}** "
                    f"by *{sub['username']}*{tiktok_str}{timestamp_str}{link_text}"
                )
            embed.description = "\n".join(description_lines)
        
        footer_text = f"Total submissions: {len(self.submissions)}"
        if self.total_pages > 1:
            footer_text = f"Page {self.current_page} of {self.total_pages} | {footer_text}"
        
        if is_expired:
            embed.description = "This interactive view has expired. Please use the command again to get a new one."
            footer_text = "View has expired"

        # Add our unique identifier to the footer text
        embed.set_footer(text=f"{footer_text} | {QUEUE_VIEW_EMBED_FOOTER_ID} | Luxurious Radio By Emerald Beats")
        embed.timestamp = discord.utils.utcnow()
        return embed
    
    def _get_line_color(self) -> discord.Color:
        """Get color for queue line embed"""
        colors = {
            QueueLine.TWENTYFIVEPLUSSKIP.value: discord.Color.red(),
            QueueLine.TWENTYSKIP.value: discord.Color.dark_orange(),
            QueueLine.FIFTEENSKIP.value: discord.Color.orange(),
            QueueLine.TENSKIP.value: discord.Color.gold(),
            QueueLine.FIVESKIP.value: discord.Color.yellow(),
            QueueLine.FREE.value: discord.Color.green(),
            QueueLine.SONGS_PLAYED.value: discord.Color.purple()
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

    async def initialize_all_views(self):
        """
        Scans all configured queue channels, cleans up old views,
        and ensures a single, active view is present and correctly pinned.
        This should be called on bot startup.
        """
        print("Initializing all queue views...")
        for queue_line in QueueLine:
            # All queues, including Pending Skips, will now have a persistent view.
            channel_settings = await self.bot.db.get_channel_for_line(queue_line.value)
            if not (channel_settings and channel_settings['channel_id']):
                continue

            channel = self.bot.get_channel(channel_settings['channel_id'])
            if not channel:
                print(f"Channel {channel_settings['channel_id']} for {queue_line.value} not found.")
                continue

            # Health check the channel
            await self._health_check_channel(channel, queue_line.value)
    
    async def _health_check_channel(self, channel: discord.TextChannel, queue_line: str):
        """Ensures a channel has one valid, pinned queue view message."""
        try:
            pinned_messages = await channel.pins()
        except discord.Forbidden:
            print(f"Cannot read pinned messages in {channel.name}. Skipping health check.")
            return
        except discord.HTTPException as e:
            print(f"Failed to fetch pins for {channel.name}: {e}")
            return

        valid_queue_message = None

        # Find our queue message among the pins
        for msg in pinned_messages:
            if msg.author.id == self.bot.user.id and msg.embeds:
                footer = msg.embeds[0].footer.text or ""
                if QUEUE_VIEW_EMBED_FOOTER_ID in footer:
                    if valid_queue_message is None:
                        valid_queue_message = msg # Found our first valid message
                    else:
                        # Found a duplicate, unpin it
                        print(f"Found duplicate queue view in {channel.name}. Unpinning older one.")
                        await msg.unpin(reason="Cleaning up duplicate queue view.")

        # Now, ensure the one we found is the one in the DB
        if valid_queue_message:
            await self.bot.db.update_pinned_message(queue_line, valid_queue_message.id)

        # Determine if this channel should be aggressively cleaned.
        now_playing_channel_id = self.bot.settings_cache.get('now_playing_channel_id')
        bookmark_channel_id = self.bot.settings_cache.get('bookmark_channel_id')

        # List of channel IDs that should never be purged.
        channel_cleanup_exempt_ids = [now_playing_channel_id, bookmark_channel_id]

        # List of queue types that should never be purged.
        queue_type_cleanup_exempt = [QueueLine.SONGS_PLAYED.value]

        is_exempt = (
            channel.id in channel_cleanup_exempt_ids or
            queue_line in queue_type_cleanup_exempt
        )

        # Aggressive Cleanup: For non-exempt queues, remove all other messages.
        if not is_exempt:
            try:
                # This check ensures we don't delete the message we want to keep.
                def is_not_the_queue_view(m):
                    return m.id != (valid_queue_message.id if valid_queue_message else None)

                purged = await channel.purge(limit=None, check=is_not_the_queue_view, bulk=True)
                if len(purged) > 0:
                    print(f"Aggressively purged {len(purged)} message(s) from channel: {channel.name}")
            except discord.Forbidden:
                print(f"Lacking permissions to purge messages in {channel.name}.")
            except discord.HTTPException as e:
                print(f"HTTP error while purging {channel.name}: {e}")

        # Finally, create or update the view to ensure it's fresh and has working buttons.
        await self.create_or_update_queue_view(queue_line)


    async def create_or_update_queue_view(self, queue_line: str):
        """Create or update a paginated queue view in its designated channel."""
        channel_settings = await self.bot.db.get_channel_for_line(queue_line)
        if not (channel_settings and channel_settings['channel_id']):
            return
            
        channel = self.bot.get_channel(channel_settings['channel_id'])
        if not channel:
            return

        entries_per_page = 25 if queue_line == QueueLine.SONGS_PLAYED.value else 10
        view = PaginatedQueueView(self.bot, queue_line, entries_per_page=entries_per_page)
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