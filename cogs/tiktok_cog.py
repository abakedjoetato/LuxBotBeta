import discord
import logging
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict, Any
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent
from TikTokLive.errors import UserNotFoundError, LiveNotFoundError

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

@app_commands.default_permissions(administrator=True)
class TikTokCog(commands.GroupCog, name="tiktok", description="Commands for managing TikTok Live integration."):
    """Handles TikTok Live integration and engagement rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        logging.info("--- TikTokCog IS BEING INITIALIZED ---")
        self.bot.tiktok_client: Optional[TikTokLiveClient] = None
        self.viewer_scores: Dict[str, float] = {}  # {tiktok_username: minutes_watched}
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None
        self._connect_interaction: Optional[discord.Interaction] = None
        super().__init__()

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

    def _create_status_embed(self, title: str, description: str, color: discord.Color) -> discord.Embed:
        """Helper function to create a standardized status embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="TikTok Live Integration | Luxurious Radio")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @app_commands.command(name="status", description="Check the status of the TikTok LIVE connection.")
    async def status(self, interaction: discord.Interaction):
        """Checks and reports the current TikTok Live connection status."""
        if self.is_connected and self.bot.tiktok_client and hasattr(self.bot.tiktok_client, 'unique_id'):
            status_message = f"🟢 Connected to **{self.bot.tiktok_client.unique_id}**'s LIVE."
        else:
            status_message = "🔴 Disconnected."
        await interaction.response.send_message(status_message, ephemeral=True)

    @app_commands.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(unique_id="The @unique_id of the TikTok user to connect to.")
    async def connect(self, interaction: discord.Interaction, unique_id: str):
        """Connects the bot to a specified TikTok Live stream with real-time status updates."""
        if self.is_connected:
            await interaction.response.send_message("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        embed = self._create_status_embed("⏳ Connecting...", "Status: Initializing...", discord.Color.light_grey())
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Run the connection process in a background asyncio.Task
        self._connection_task = asyncio.create_task(self._background_connect(interaction, unique_id))

    async def _background_connect(self, interaction: discord.Interaction, unique_id: str):
        """
        Asynchronous method to handle the TikTok connection.
        This is designed to be run in a background task.
        """
        async def edit_status(title, description, color):
            await interaction.edit_original_response(embed=self._create_status_embed(title, description, color))

        try:
            await edit_status("⏳ Connecting...", "Status: Creating TikTok Client...", discord.Color.blue())
            clean_unique_id = unique_id.strip().lstrip('@')

            client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
            self.bot.tiktok_client = client

            # Add event listeners directly using the event classes
            client.add_listener(ConnectEvent, self.on_connect)
            client.add_listener(DisconnectEvent, self.on_disconnect)
            client.add_listener(LikeEvent, self.on_like)
            client.add_listener(CommentEvent, self.on_comment)
            client.add_listener(ShareEvent, self.on_share)
            client.add_listener(GiftEvent, self.on_gift)

            # Store the interaction object to be used by the on_connect handler
            self._connect_interaction = interaction

            await edit_status("⏳ Connecting...", "Status: Awaiting connection to TikTok...", discord.Color.orange())
            await client.start()

        except UserNotFoundError:
            await edit_status("❌ Connection Failed", f"**Reason:** TikTok user `@{unique_id}` was not found.", discord.Color.red())
            await self._cleanup_connection()
        except LiveNotFoundError:
            await edit_status("❌ Connection Failed", f"**Reason:** User `@{unique_id}` is not currently LIVE.", discord.Color.red())
            await self._cleanup_connection()
        except Exception as e:
            logging.error(f"Failed to connect to TikTok in background: {e}", exc_info=True)
            await edit_status("❌ Connection Failed", f"**Reason:** An unexpected error occurred.\n```\n{e}\n```", discord.Color.red())
            await self._cleanup_connection()

    @app_commands.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        if not self.is_connected:
            await interaction.response.send_message("Not currently connected to any stream.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self._cleanup_connection()
        await interaction.followup.send("🔌 Successfully disconnected from the TikTok LIVE stream.", ephemeral=True)

    async def _cleanup_connection(self):
        if self.bot.tiktok_client:
            await self.bot.tiktok_client.stop()
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        self.bot.tiktok_client = None
        self._is_connected.clear()

        if self.watch_time_scorekeeper.is_running(): self.watch_time_scorekeeper.cancel()
        if self.realtime_resort_task.is_running(): self.realtime_resort_task.cancel()

        self.viewer_scores.clear()
        self._connect_interaction = None
        logging.info("TIKTOK: Connection cleaned up.")

    # --- Event Handlers ---
    async def on_connect(self, _: ConnectEvent):
        """Handles the connection event from the TikTok client."""
        self._is_connected.set()
        logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")

        if self._connect_interaction:
            await self._connect_interaction.edit_original_response(
                embed=self._create_status_embed(
                    "✅ Connected!",
                    f"Successfully connected to **{self.bot.tiktok_client.unique_id}**'s LIVE stream.",
                    discord.Color.green()
                )
            )

        if not self.watch_time_scorekeeper.is_running(): self.watch_time_scorekeeper.start()
        if not self.realtime_resort_task.is_running(): self.realtime_resort_task.start()

    async def on_disconnect(self, _: DisconnectEvent):
        logging.info("TIKTOK: Disconnected from stream.")
        await self._cleanup_connection()

    async def _handle_interaction(self, user, points: float):
        if not user or not hasattr(user, 'unique_id'): return
        submission = await self.bot.db.find_active_submission_by_tiktok_user(user.unique_id)
        if submission: await self.bot.db.add_interaction_score(submission['public_id'], points)

    async def on_like(self, event: LikeEvent): await self._handle_interaction(event.user, INTERACTION_POINTS["like"] * event.like_count)
    async def on_comment(self, event: CommentEvent): await self._handle_interaction(event.user, INTERACTION_POINTS["comment"])
    async def on_share(self, event: ShareEvent): await self._handle_interaction(event.user, INTERACTION_POINTS["share"])

    async def on_gift(self, event: GiftEvent):
        # If the gift is streakable, we only want to process it when the streak has ended.
        if event.gift.streakable and event.streaking:
            return

        # Process the gift reward
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
            viewers = self.bot.tiktok_client.viewers
            for user in viewers:
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