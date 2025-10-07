import discord
import logging
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, Any

# --- Constants ---
# Map gift coin values to the queue they unlock.
GIFT_TIER_MAP = {
    100: "25+ Skip",
    50: "20 Skip",
    25: "15 Skip",
    10: "10 Skip",
    1: "5 Skip",
}

# Points awarded for different interactions
INTERACTION_POINTS = {
    "share": 3,
    "comment": 2,
    "like": 1,
}

class TikTokCog(commands.Cog):
    """Handles TikTok Live integration and engagement rewards."""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        logging.info("--- TikTokCog IS BEING INITIALIZED ---")
        self.bot.tiktok_client: Optional[Any] = None
        self.viewer_scores: Dict[str, float] = {}  # {tiktok_username: minutes_watched}
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        if self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.stop())
        if self.watch_time_scorekeeper.is_running():
            self.watch_time_scorekeeper.cancel()
        if self.realtime_resort_task.is_running():
            self.realtime_resort_task.cancel()

    @property
    def is_connected(self) -> bool:
        """Check if the TikTok client is connected."""
        return self._is_connected.is_set()

    # --- Admin Command Group ---
    tiktok = app_commands.Group(name="tiktok", description="Commands for managing TikTok Live integration.")

    @tiktok.command(name="status", description="Check the status of the TikTok LIVE connection.")
    async def status(self, interaction: discord.Interaction):
        """Checks and reports the current TikTok Live connection status."""
        if self.is_connected and self.bot.tiktok_client and hasattr(self.bot.tiktok_client, 'unique_id'):
            status_message = f"🟢 Connected to **{self.bot.tiktok_client.unique_id}**'s LIVE."
        else:
            status_message = "🔴 Disconnected."
        await interaction.response.send_message(status_message, ephemeral=True)

    @tiktok.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(unique_id="The @unique_id of the TikTok user to connect to.")
    async def connect(self, interaction: discord.Interaction, unique_id: str):
        """Connects the bot to a specified TikTok Live stream in the background."""
        if self.is_connected:
            await interaction.response.send_message("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        # Respond immediately to the user
        await interaction.response.send_message(f"🚀 Attempting to connect to `@{unique_id}`'s LIVE stream in the background. Use `/tiktok status` to check the connection.", ephemeral=True)

        # Start the connection process in a background task
        asyncio.create_task(self._background_connect(unique_id))

    async def _background_connect(self, unique_id: str):
        """The actual connection logic that runs in the background."""
        # Defer the import until it's actually used
        from TikTokLive import TikTokLiveClient
        from TikTokLive.types.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent

        if self.bot.tiktok_client:
            await self.bot.tiktok_client.stop()

        try:
            clean_unique_id = unique_id.strip().lstrip('@')
            self.bot.tiktok_client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
            self._add_listeners(CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent)
            await self.bot.tiktok_client.start()

        except Exception as e:
            logging.error(f"Failed to connect to TikTok in background: {e}", exc_info=True)
            await self._cleanup_connection()

    @tiktok.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnects the bot from the TikTok Live stream."""
        if not self.is_connected:
            await interaction.response.send_message("Not currently connected to any stream.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self._cleanup_connection()
        await interaction.followup.send("🔌 Successfully disconnected from the TikTok LIVE stream.", ephemeral=True)

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
        logging.info("TIKTOK: Connection cleaned up.")

    def _add_listeners(self, CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent):
        """Adds all necessary event listeners to the TikTok client."""
        if not self.bot.tiktok_client:
            return

        async def on_connect_wrapper(event: ConnectEvent): await self.on_connect(event)
        async def on_disconnect_wrapper(event: DisconnectEvent): await self.on_disconnect(event)
        async def on_like_wrapper(event: LikeEvent): await self.on_like(event)
        async def on_comment_wrapper(event: CommentEvent): await self.on_comment(event)
        async def on_share_wrapper(event: ShareEvent): await self.on_share(event)
        async def on_gift_wrapper(event: GiftEvent): await self.on_gift(event)

        self.bot.tiktok_client.add_listener("connect", on_connect_wrapper)
        self.bot.tiktok_client.add_listener("disconnect", on_disconnect_wrapper)
        self.bot.tiktok_client.add_listener("like", on_like_wrapper)
        self.bot.tiktok_client.add_listener("comment", on_comment_wrapper)
        self.bot.tiktok_client.add_listener("share", on_share_wrapper)
        self.bot.tiktok_client.add_listener("gift", on_gift_wrapper)

    # --- TikTok Event Handlers ---
    async def on_connect(self, _):
        logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")
        self._is_connected.set()
        if not self.watch_time_scorekeeper.is_running(): self.watch_time_scorekeeper.start()
        if not self.realtime_resort_task.is_running(): self.realtime_resort_task.start()

    async def on_disconnect(self, _):
        logging.info("TIKTOK: Disconnected from stream.")
        await self._cleanup_connection()

    async def _handle_interaction(self, user, points: float):
        if not user or not hasattr(user, 'unique_id'): return
        submission = await self.bot.db.find_active_submission_by_tiktok_user(user.unique_id)
        if submission: await self.bot.db.add_interaction_score(submission['public_id'], points)

    async def on_like(self, event): await self._handle_interaction(event.user, INTERACTION_POINTS["like"] * event.like_count)
    async def on_comment(self, event): await self._handle_interaction(event.user, INTERACTION_POINTS["comment"])
    async def on_share(self, event): await self._handle_interaction(event.user, INTERACTION_POINTS["share"])

    async def on_gift(self, event):
        if event.gift.streakable and not event.gift.streaking: return
        target_line_name: Optional[str] = None
        for coins, line_name in sorted(GIFT_TIER_MAP.items(), key=lambda item: item[0], reverse=True):
            if event.gift.diamond_count >= coins:
                target_line_name = line_name
                break
        if not target_line_name: return
        submission = await self.bot.db.find_active_submission_by_tiktok_user(event.user.unique_id)
        if not submission: return
        original_line = await self.bot.db.move_submission(submission['public_id'], target_line_name)
        if original_line and original_line != target_line_name:
            logging.info(f"TIKTOK: Rewarded {event.user.unique_id} with a move to {target_line_name} for a {event.gift.diamond_count}-coin gift.")
            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog:
                await queue_view_cog.create_or_update_queue_view(original_line)
                await queue_view_cog.create_or_update_queue_view(target_line_name)

    # --- Background Tasks ---
    @tasks.loop(minutes=1)
    async def watch_time_scorekeeper(self):
        if not self.is_connected or not self.bot.tiktok_client: return
        try:
            for user in self.bot.tiktok_client.viewers:
                self.viewer_scores[user.unique_id] = self.viewer_scores.get(user.unique_id, 0) + 1
        except Exception as e: logging.error(f"Error in watch_time_scorekeeper: {e}")

    @tasks.loop(seconds=30)
    async def realtime_resort_task(self):
        if not self.is_connected: return
        try:
            from database import QueueLine
            await self.bot.db.update_free_line_scores(self.viewer_scores)
            queue_view_cog = self.bot.get_cog('QueueViewCog')
            if queue_view_cog: await queue_view_cog.create_or_update_queue_view(QueueLine.FREE.value)
        except Exception as e: logging.error(f"Error in realtime_resort_task: {e}")

async def setup(bot):
    await bot.add_cog(TikTokCog(bot))