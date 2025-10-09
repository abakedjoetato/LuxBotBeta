import discord
import logging
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent, FollowEvent
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
from database import QueueLine

# --- Constants ---
# Re-implementing the tiered gift logic as requested
GIFT_TIER_MAP = {
    5000: QueueLine.TWENTYFIVEPLUSSKIP.value,
    2000: QueueLine.TENSKIP.value,
    1000: QueueLine.FIVESKIP.value,
}

INTERACTION_POINTS = {
    "like": 1,
    "comment": 2,
    "share": 5,
    "follow": 10,
}

@app_commands.default_permissions(administrator=True)
class TikTokCog(commands.GroupCog, name="tiktok", description="Commands for managing TikTok Live integration."):
    """Handles TikTok Live integration, interaction logging, and engagement rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        logging.info("--- TikTokCog IS BEING INITIALIZED ---")
        self.bot.tiktok_client: Optional[TikTokLiveClient] = None
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None
        self._connect_interaction: Optional[discord.Interaction] = None
        self.current_session_id: Optional[int] = None
        self.live_host_username: Optional[str] = None
        self.score_sync_task.start()
        super().__init__()

    # FIXED BY JULES
    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.score_sync_task.cancel()
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        # If connected, trigger the disconnection. The on_disconnect event will handle the cleanup.
        if self.is_connected and self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.disconnect())

    @property
    def is_connected(self) -> bool:
        return self._is_connected.is_set()

    # ... (rest of the connection and status logic remains the same) ...
    def _create_status_embed(self, title: str, description: str, color: discord.Color) -> discord.Embed:
        """Helper function to create a standardized status embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="TikTok Live Integration | Luxurious Radio")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @app_commands.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(unique_id="The @unique_id of the TikTok user to connect to.")
    async def connect(self, interaction: discord.Interaction, unique_id: str):
        """Connects the bot to a specified TikTok Live stream with real-time status updates."""
        if self.is_connected:
            await interaction.response.send_message("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        embed = self._create_status_embed("⏳ Connecting...", "Status: Initializing...", discord.Color.light_grey())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self._connection_task = asyncio.create_task(self._background_connect(interaction, unique_id))

    async def _background_connect(self, interaction: discord.Interaction, unique_id: str):
        """Asynchronous method to handle the TikTok connection."""
        async def edit_status(title, description, color):
            await interaction.edit_original_response(embed=self._create_status_embed(title, description, color))

        try:
            await edit_status("⏳ Connecting...", "Status: Creating TikTok Client...", discord.Color.blue())
            clean_unique_id = unique_id.strip().lstrip('@')
            self.live_host_username = clean_unique_id

            client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
            self.bot.tiktok_client = client

            # Add all event listeners
            client.add_listener(ConnectEvent, self.on_connect)
            client.add_listener(DisconnectEvent, self.on_disconnect)
            client.add_listener(LikeEvent, self.on_like)
            client.add_listener(CommentEvent, self.on_comment)
            client.add_listener(ShareEvent, self.on_share)
            client.add_listener(GiftEvent, self.on_gift)
            client.add_listener(FollowEvent, self.on_follow)
            self._connect_interaction = interaction

            await edit_status("⏳ Connecting...", "Status: Awaiting connection to TikTok...", discord.Color.orange())
            await client.start()

        except UserNotFoundError:
            await edit_status("❌ Connection Failed", f"**Reason:** TikTok user `@{unique_id}` was not found.", discord.Color.red())
        except UserOfflineError:
            await edit_status("❌ Connection Failed", f"**Reason:** User `@{unique_id}` is not currently LIVE.", discord.Color.red())
        except Exception as e:
            logging.error(f"Failed to connect to TikTok in background: {e}", exc_info=True)
            await edit_status("❌ Connection Failed", f"**Reason:** An unexpected error occurred.\n```\n{e}\n```", discord.Color.red())
        finally:
            # If the connection task fails and the disconnect event was not received,
            # we need to manually reset the state.
            if not self.is_connected:
                self._reset_state()

    # FIXED BY JULES
    @app_commands.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        """Signals the TikTok client to disconnect. The on_disconnect event will handle all cleanup."""
        if not self.is_connected or not self.bot.tiktok_client:
            await interaction.response.send_message("Not currently connected to any stream.", ephemeral=True)
            return

        await interaction.response.send_message("🔌 Disconnecting... The bot will disconnect and post a session summary shortly.", ephemeral=True)

        # This will trigger the on_disconnect event, which is the single source of truth for cleanup.
        await self.bot.tiktok_client.disconnect()

    def _reset_state(self):
        """Resets all internal state variables for the connection."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        self.bot.tiktok_client = None
        self._is_connected.clear()
        self.current_session_id = None
        self.live_host_username = None
        self._connect_interaction = None
        logging.info("TIKTOK: Internal connection state has been reset.")

    async def _post_live_summary(self, summary: Dict[str, int]):
        """Posts the live session summary to the admin/debug channel."""
        debug_channel_id = self.bot.settings_cache.get('debug_channel_id')
        if not debug_channel_id: return
        channel = self.bot.get_channel(int(debug_channel_id))
        if not channel: return

        # --- Overall Summary (Existing) ---
        overall_embed = discord.Embed(
            title=f"📈 Overall Live Summary for {self.live_host_username}",
            description="Summary of all interactions during the last session.",
            color=discord.Color.blurple()
        )
        overall_embed.add_field(name="Likes", value=f"{summary.get('like', 0):,}", inline=True)
        overall_embed.add_field(name="Comments", value=f"{summary.get('comment', 0):,}", inline=True)
        overall_embed.add_field(name="Shares", value=f"{summary.get('share', 0):,}", inline=True)
        overall_embed.add_field(name="Follows", value=f"{summary.get('follow', 0):,}", inline=True)
        overall_embed.add_field(name="Gifts Received", value=f"{summary.get('gift', 0):,}", inline=True)
        overall_embed.add_field(name="Total Coins", value=f"{summary.get('gift_coins', 0):,}", inline=True)
        overall_embed.set_footer(text=f"Session ID: {self.current_session_id}")
        overall_embed.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=overall_embed)
        except discord.Forbidden:
            logging.error(f"Missing permissions to send summary to channel {debug_channel_id}")
            return # Can't send anything if we don't have perms

        # --- Per-User Summary (New) ---
        user_stats = await self.bot.db.get_session_user_stats(self.current_session_id)
        submission_counts = await self.bot.db.get_session_submission_counts(self.current_session_id)

        if not user_stats:
            return # No users to report on

        user_embed = discord.Embed(
            title=f"👥 Per-User Stats for {self.live_host_username}",
            description="Top contributors for the last session.",
            color=discord.Color.dark_green()
        )
        user_embed.set_footer(text=f"Session ID: {self.current_session_id}")
        user_embed.timestamp = discord.utils.utcnow()

        description_lines = []
        for i, user_data in enumerate(user_stats[:10]): # Top 10 contributors
            discord_id = user_data['linked_discord_id']
            user = self.bot.get_user(discord_id) or f"ID: {discord_id}"
            subs = submission_counts.get(discord_id, 0)

            stats_line = (
                f"**{i+1}. {user}** (`{user_data['tiktok_username']}`)\n"
                f"> Subs: `{subs}` | Likes: `{user_data['likes']}` | Comments: `{user_data['comments']}` | "
                f"Shares: `{user_data['shares']}` | Coins: `{int(user_data['gift_coins'])}`\n"
            )
            description_lines.append(stats_line)

        user_embed.description = "\n".join(description_lines)
        if len(user_stats) > 10:
            user_embed.description += f"\n...and {len(user_stats) - 10} more contributors."

        try:
            await channel.send(embed=user_embed)
        except discord.Forbidden:
            logging.error(f"Missing permissions to send per-user summary to channel {debug_channel_id}")

    # --- Event Handlers ---
    async def on_connect(self, _: ConnectEvent):
        """Handles the connection event, starting a new live session."""
        self._is_connected.set()
        logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")

        if self.live_host_username:
            self.current_session_id = await self.bot.db.start_live_session(self.live_host_username)
            logging.info(f"TIKTOK: Started live session with ID {self.current_session_id}")

        if self._connect_interaction:
            await self._connect_interaction.edit_original_response(
                embed=self._create_status_embed("✅ Connected!", f"Successfully connected to **{self.bot.tiktok_client.unique_id}**'s LIVE stream.", discord.Color.green())
            )

    async def on_disconnect(self, _: DisconnectEvent):
        logging.info("TIKTOK: Disconnected from stream. Cleaning up...")
        await self._cleanup_connection()

    async def _handle_interaction(self, event, interaction_type: str, points: int, value: Optional[str] = None, coin_value: Optional[int] = None):
        """Generic interaction logger and point awarder."""
        if not self.current_session_id or not hasattr(event, 'user') or not hasattr(event.user, 'unique_id'):
            return

        try:
            tiktok_account_id = await self.bot.db.upsert_tiktok_account(event.user.unique_id)
            await self.bot.db.log_tiktok_interaction(self.current_session_id, tiktok_account_id, interaction_type, value, coin_value)

            discord_id = await self.bot.db.get_discord_id_from_handle(event.user.unique_id)
            if discord_id:
                await self.bot.db.add_points_to_user(discord_id, points)
        except Exception as e:
            logging.error(f"Failed to handle TikTok interaction ({interaction_type}): {e}", exc_info=True)

    async def on_like(self, event: LikeEvent):
        await self._handle_interaction(event, 'like', INTERACTION_POINTS['like'])

    async def on_comment(self, event: CommentEvent):
        await self._handle_interaction(event, 'comment', INTERACTION_POINTS['comment'], value=event.comment)

    async def on_share(self, event: ShareEvent):
        await self._handle_interaction(event, 'share', INTERACTION_POINTS['share'])

    async def on_follow(self, event: FollowEvent):
        await self._handle_interaction(event, 'follow', INTERACTION_POINTS['follow'])

    async def on_gift(self, event: GiftEvent):
        if event.gift.streakable and event.streaking: return

        # Award points for all gifts
        # Updated point logic: 2 points per coin for gifts under 1000, otherwise 1 point per coin
        if event.gift.diamond_count < 1000:
            points = event.gift.diamond_count * 2
        else:
            points = event.gift.diamond_count

        await self._handle_interaction(event, 'gift', points, value=event.gift.name, coin_value=event.gift.diamond_count)

        # Tiered skip logic
        target_line_name: Optional[str] = None
        for coins, line_name in sorted(GIFT_TIER_MAP.items(), key=lambda item: item[0], reverse=True):
            if event.gift.diamond_count >= coins:
                target_line_name = line_name
                break

        if target_line_name:
            try:
                discord_id = await self.bot.db.get_discord_id_from_handle(event.user.unique_id)
                if not discord_id: return

                submission = await self.bot.db.find_gift_rewardable_submission(discord_id)
                if not submission: return

                original_line = await self.bot.db.move_submission(submission['public_id'], target_line_name)
                if original_line and original_line != target_line_name:
                    await self.bot.dispatch_queue_update() # FIXED BY JULES
                    logging.info(f"TIKTOK: Rewarded user {discord_id} with move to {target_line_name} for a {event.gift.diamond_count}-coin gift.")
                    user = self.bot.get_user(discord_id)
                    if user:
                        try:
                            await user.send(f"🎉 Thank you for the {event.gift.diamond_count}-coin gift! Your submission **{submission['artist_name']} - {submission['song_name']}** has been moved to the **{target_line_name}** queue as a reward.")
                        except discord.Forbidden:
                            pass # Can't send DMs, oh well
            except Exception as e:
                logging.error(f"Error processing tiered gift reward: {e}", exc_info=True)

    # --- Background Tasks ---
    # FIXED BY Replit: Points tracking with periodic sync - verified working
    @tasks.loop(seconds=15)
    async def score_sync_task(self):
        """Periodically syncs the user points with the submission scores in the free queue."""
        try:
            await self.bot.db.sync_submission_scores()
        except Exception as e:
            logging.error(f"Error in score_sync_task: {e}", exc_info=True)

    @score_sync_task.before_loop
    async def before_score_sync_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TikTokCog(bot))