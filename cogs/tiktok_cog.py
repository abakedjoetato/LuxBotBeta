"""
TikTok Cog - Integrates with TikTok Live to reward user engagement.
"""
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent
from typing import Optional, Dict
from database import QueueLine

# --- Constants ---
# Map gift coin values to the queue they unlock.
# This is a flexible system. Add or change values as needed.
# The keys are the minimum coin value for that tier.
GIFT_TIER_MAP = {
    100: QueueLine.TWENTYFIVEPLUSSKIP,
    50: QueueLine.TWENTYSKIP,
    25: QueueLine.FIFTEENSKIP,
    10: QueueLine.TENSKIP,
    1: QueueLine.FIVESKIP,
}

# Points awarded for different interactions
INTERACTION_POINTS = {
    "share": 3,
    "comment": 2,
    "like": 1,
}

class TikTokCog(commands.Cog):
    """Cog for handling TikTok Live integration and engagement rewards."""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        # These attributes are initialized in main.py
        # self.bot.tiktok_client: Optional[TikTokLiveClient] = None
        # self.bot.currently_playing_submission_id: Optional[str] = None
        self.viewer_scores: Dict[str, float] = {}  # {tiktok_username: minutes_watched}
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None

    # --- Teardown and State Management ---
    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        if self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.stop())
        self.watch_time_scorekeeper.cancel()
        self.realtime_resort_task.cancel()

    @property
    def is_connected(self) -> bool:
        """Check if the TikTok client is connected."""
        return self._is_connected.is_set()

    # --- Admin Command Group ---
    tiktok = app_commands.Group(name="tiktok", description="Commands for managing TikTok Live integration.")

    @tiktok.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(unique_id="The @unique_id of the TikTok user to connect to.")
    async def connect(self, interaction: discord.Interaction, unique_id: str):
        """Connects the bot to a specified TikTok Live stream."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        if self.is_connected:
            await interaction.followup.send("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        if self.bot.tiktok_client:
             await self.bot.tiktok_client.stop()

        try:
            clean_unique_id = unique_id.strip().lstrip('@')
            self.bot.tiktok_client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
            self._add_listeners()
            self._connection_task = asyncio.create_task(self.bot.tiktok_client.start())

            await asyncio.wait_for(self._is_connected.wait(), timeout=15.0)

            await interaction.followup.send(f"✅ Successfully connected to `@{clean_unique_id}`'s LIVE stream. Engagement tracking is active.", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("Connection timed out. Please check the `unique_id` and ensure the user is LIVE.", ephemeral=True)
            await self._cleanup_connection()
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect: {e}", ephemeral=True)
            await self._cleanup_connection()

    @tiktok.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnects the bot from the TikTok Live stream."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self.is_connected:
            await interaction.followup.send("Not currently connected to any stream.", ephemeral=True)
            return

        await self._cleanup_connection()
        await interaction.followup.send("🔌 Successfully disconnected from the TikTok LIVE stream.", ephemeral=True)

    @tiktok.command(name="status", description="Check the status of the TikTok LIVE connection.")
    async def status(self, interaction: discord.Interaction):
        """Checks and reports the current TikTok Live connection status."""
        if self.is_connected and self.bot.tiktok_client:
            status_message = f"🟢 Connected to **{self.bot.tiktok_client.unique_id}**'s LIVE."
        else:
            status_message = "🔴 Disconnected."
        await interaction.response.send_message(status_message, ephemeral=True)

    async def _cleanup_connection(self):
        """Helper to stop the client and reset state."""
        if self.bot.tiktok_client:
            await self.bot.tiktok_client.stop()
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        self.bot.tiktok_client = None
        self._is_connected.clear()
        if self.watch_time_scorekeeper.is_running():
            self.watch_time_scorekeeper.cancel()
        if self.realtime_resort_task.is_running():
            self.realtime_resort_task.cancel()
        self.viewer_scores.clear()
        self.bot.currently_playing_submission_id = None
        print("TIKTOK: Connection cleaned up.")

    def _add_listeners(self):
        """Adds all necessary event listeners to the TikTok client."""
        if not self.bot.tiktok_client:
            return

        self.bot.tiktok_client.add_listener("connect", self.on_connect)
        self.bot.tiktok_client.add_listener("disconnect", self.on_disconnect)
        self.bot.tiktok_client.add_listener("like", self.on_like)
        self.bot.tiktok_client.add_listener("comment", self.on_comment)
        self.bot.tiktok_client.add_listener("share", self.on_share)
        self.bot.tiktok_client.add_listener("gift", self.on_gift)

    # --- TikTok Event Handlers ---
    async def on_connect(self, _: ConnectEvent):
        """Handles the connection event from the TikTok client."""
        print(f"TIKTOK: Connected to {self.bot.tiktok_client.room_id}")
        self._is_connected.set()
        if not self.watch_time_scorekeeper.is_running():
            self.watch_time_scorekeeper.start()
        if not self.realtime_resort_task.is_running():
            self.realtime_resort_task.start()

    async def on_disconnect(self, _: DisconnectEvent):
        """Handles the disconnection event."""
        print("TIKTOK: Disconnected from stream.")
        await self._cleanup_connection()

    async def on_like(self, event: LikeEvent):
        """Handles like events and adds to interaction score."""
        if self.bot.currently_playing_submission_id:
            await self.bot.db.add_interaction_score(
                self.bot.currently_playing_submission_id,
                INTERACTION_POINTS["like"] * event.like_count
            )

    async def on_comment(self, event: CommentEvent):
        """Handles comment events and adds to interaction score."""
        if self.bot.currently_playing_submission_id:
            await self.bot.db.add_interaction_score(
                self.bot.currently_playing_submission_id,
                INTERACTION_POINTS["comment"]
            )

    async def on_share(self, event: ShareEvent):
        """Handles share events and adds to interaction score."""
        if self.bot.currently_playing_submission_id:
            await self.bot.db.add_interaction_score(
                self.bot.currently_playing_submission_id,
                INTERACTION_POINTS["share"]
            )

    async def on_gift(self, event: GiftEvent):
        """Handles gift events and rewards users by moving them to priority queues."""
        if event.gift.streakable and not event.gift.streaking:
            return

        target_line: Optional[QueueLine] = None
        for coins, line in sorted(GIFT_TIER_MAP.items(), key=lambda item: item[0], reverse=True):
            if event.gift.diamond_count >= coins:
                target_line = line
                break

        if not target_line:
            return

        submission = await self.bot.db.find_active_submission_by_tiktok_user(event.user.unique_id)
        if not submission:
            return

        original_line = await self.bot.db.move_submission(submission['public_id'], target_line.value)
        if original_line and original_line != target_line.value:
            print(f"TIKTOK: Rewarded {event.user.unique_id} with a move to {target_line.value} for a {event.gift.diamond_count}-coin gift.")
            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(original_line)
                await queue_view_cog.create_or_update_queue_view(target_line.value)

    # --- Background Tasks ---
    @tasks.loop(minutes=1)
    async def watch_time_scorekeeper(self):
        """Periodically updates the watch time for all viewers in the stream."""
        if not self.is_connected or not self.bot.tiktok_client:
            return

        try:
            for user in self.bot.tiktok_client.viewers:
                self.viewer_scores[user.unique_id] = self.viewer_scores.get(user.unique_id, 0) + 1
        except Exception as e:
            print(f"Error in watch_time_scorekeeper: {e}")

    @tasks.loop(seconds=30)
    async def realtime_resort_task(self):
        """Periodically recalculates scores and updates the free line queue view."""
        if not self.is_connected:
            return

        try:
            await self.bot.db.update_free_line_scores(self.viewer_scores)

            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(QueueLine.FREE.value)
        except Exception as e:
            print(f"Error in realtime_resort_task: {e}")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(TikTokCog(bot))