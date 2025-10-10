import discord
import logging
import asyncio
import time
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Dict
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, 
    ShareEvent, FollowEvent, JoinEvent, SubscribeEvent, LiveEndEvent,
    RoomUserSeqEvent, PollEvent, LinkMicBattleEvent
)
from TikTokLive.client.errors import UserNotFoundError, UserOfflineError
from database import QueueLine

# --- Constants ---
# Tiered gift logic: Maps coin amounts to skip line rewards
GIFT_TIER_MAP = {
    6000: QueueLine.TWENTYFIVEPLUSSKIP.value,  # 6000+ coins → 25+ Skip
    5000: QueueLine.TWENTYSKIP.value,           # 5000-5999 coins → 20 Skip
    4000: QueueLine.FIFTEENSKIP.value,          # 4000-4999 coins → 15 Skip
    2000: QueueLine.TENSKIP.value,              # 2000-3999 coins → 10 Skip
    1000: QueueLine.FIVESKIP.value,             # 1000-1999 coins → 5 Skip
}

INTERACTION_POINTS = {
    "like": 1,
    "comment": 2,
    "share": 5,
    "follow": 10,
    "subscribe": 25,  # Subscriptions are high value
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
        self._retry_enabled: bool = False
        self._retry_count: int = 0
        self._connection_start_time: Optional[float] = None
        self._user_initiated_disconnect: bool = False
        self.score_sync_task.start()
        self.points_backup_task.start()  # FIXED BY JULES: Start periodic backup task
        super().__init__()

    # FIXED BY JULES
    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.score_sync_task.cancel()
        self.points_backup_task.cancel()  # FIXED BY JULES: Cancel backup task on unload
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()

        # If connected, trigger the disconnection. The on_disconnect event will handle the cleanup.
        if self.is_connected and self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.disconnect())

    @property
    def is_connected(self) -> bool:
        return self._is_connected.is_set()

    async def _send_debug_notification(self, embed: discord.Embed):
        """Send a notification embed to the debug channel if configured."""
        debug_channel_id = self.bot.settings_cache.get('debug_channel_id')
        if not debug_channel_id:
            return
        
        channel = self.bot.get_channel(int(debug_channel_id))
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                logging.error(f"Missing permissions to send to debug channel {debug_channel_id}")
            except Exception as e:
                logging.error(f"Failed to send debug notification: {e}")

    def _create_status_embed(self, title: str, description: str, color: discord.Color) -> discord.Embed:
        """Helper function to create a standardized status embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="TikTok Live Integration | Luxurious Radio")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @app_commands.command(name="connect", description="Connect to a TikTok LIVE stream.")
    @app_commands.describe(
        unique_id="The @unique_id of the TikTok user to connect to.",
        persistent="Keep retrying until the user goes live (default: True)"
    )
    async def connect(self, interaction: discord.Interaction, unique_id: str, persistent: bool = True):
        """Connects the bot to a specified TikTok Live stream with optional persistent retry."""
        await interaction.response.defer(ephemeral=True)
        
        if self.is_connected:
            await interaction.followup.send("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        if self._connection_task and not self._connection_task.done():
            await interaction.followup.send("A connection attempt is already in progress. Use `/tiktok status` to check progress or `/tiktok disconnect` to cancel.", ephemeral=True)
            return

        self._retry_enabled = persistent
        self._retry_count = 0
        self._connection_start_time = time.time()
        
        embed = self._create_status_embed("⏳ Connecting...", "Status: Initializing connection...", discord.Color.light_grey())
        await interaction.edit_original_response(embed=embed)
        self._connection_task = asyncio.create_task(self._background_connect(interaction, unique_id))

    async def _background_connect(self, interaction: discord.Interaction, unique_id: str):
        """Asynchronous method to handle the TikTok connection with retry logic."""
        async def edit_status(title, description, color):
            try:
                await interaction.edit_original_response(embed=self._create_status_embed(title, description, color))
            except discord.NotFound:
                logging.warning("Connection status message was deleted")

        clean_unique_id = unique_id.strip().lstrip('@')
        self.live_host_username = clean_unique_id
        
        while True:
            try:
                self._retry_count += 1
                elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
                
                if self._retry_count == 1:
                    await edit_status("⏳ Connecting...", "Status: Creating TikTok Client...", discord.Color.blue())
                else:
                    retry_msg = f"Status: Retry attempt #{self._retry_count} (elapsed: {elapsed}s)\nWaiting for `@{clean_unique_id}` to go live..."
                    await edit_status("🔄 Retrying Connection...", retry_msg, discord.Color.orange())

                client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")
                self.bot.tiktok_client = client

                # Add all event listeners
                client.add_listener(ConnectEvent, self.on_connect)
                client.add_listener(DisconnectEvent, self.on_disconnect)
                client.add_listener(JoinEvent, self.on_join)
                client.add_listener(LikeEvent, self.on_like)
                client.add_listener(CommentEvent, self.on_comment)
                client.add_listener(ShareEvent, self.on_share)
                client.add_listener(GiftEvent, self.on_gift)
                client.add_listener(FollowEvent, self.on_follow)
                client.add_listener(SubscribeEvent, self.on_subscribe)
                client.add_listener(LiveEndEvent, self.on_live_end)
                client.add_listener(RoomUserSeqEvent, self.on_viewer_update)
                client.add_listener(PollEvent, self.on_poll)
                client.add_listener(LinkMicBattleEvent, self.on_mic_battle)
                self._connect_interaction = interaction

                await edit_status("⏳ Connecting...", f"Status: Attempting connection to `@{clean_unique_id}`...", discord.Color.blue())
                await client.start()
                
                # If we get here, connection succeeded
                break

            except UserNotFoundError:
                await edit_status("❌ Connection Failed", f"**Reason:** TikTok user `@{unique_id}` was not found.\n\nThis username doesn't exist on TikTok.", discord.Color.red())
                self._reset_state()
                break
                
            except UserOfflineError:
                if not self._retry_enabled:
                    await edit_status("❌ Connection Failed", f"**Reason:** User `@{unique_id}` is not currently LIVE.\n\nEnable persistent mode to keep retrying.", discord.Color.red())
                    self._reset_state()
                    break
                
                # Retry logic for offline user
                if self._retry_count >= 3:
                    # After 3 attempts, update status less frequently
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(10)
                continue
                
            except asyncio.CancelledError:
                await edit_status("🛑 Connection Cancelled", "The connection attempt was manually cancelled.", discord.Color.red())
                self._reset_state()
                raise
                
            except Exception as e:
                logging.error(f"Failed to connect to TikTok in background: {e}", exc_info=True)
                
                if self._retry_enabled and self._retry_count < 5:
                    await asyncio.sleep(15)
                    continue
                else:
                    await edit_status("❌ Connection Failed", f"**Reason:** An unexpected error occurred.\n```\n{str(e)[:200]}\n```", discord.Color.red())
                    self._reset_state()
                    break
            
            finally:
                # Cleanup if we're not connected and not retrying
                if not self.is_connected and not self._retry_enabled:
                    self._reset_state()

    @app_commands.command(name="status", description="Check the current TikTok connection status.")
    async def status(self, interaction: discord.Interaction):
        """Display the current TikTok connection status with detailed information."""
        await interaction.response.defer(ephemeral=True)
        
        if self.is_connected and self.bot.tiktok_client:
            elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
            
            embed = discord.Embed(
                title="✅ TikTok Connection Active",
                description=f"Connected to **@{self.live_host_username}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Room ID", value=f"`{self.bot.tiktok_client.room_id}`", inline=True)
            embed.add_field(name="Session ID", value=f"`{self.current_session_id or 'N/A'}`", inline=True)
            embed.add_field(name="Connection Uptime", value=uptime_str, inline=True)
            embed.set_footer(text="Use /tiktok disconnect to end the session")
        elif self._connection_task and not self._connection_task.done():
            elapsed = int(time.time() - self._connection_start_time) if self._connection_start_time else 0
            status_text = f"Attempting to connect to **@{self.live_host_username or 'Unknown'}**"
            
            embed = discord.Embed(
                title="🔄 Connection In Progress",
                description=status_text,
                color=discord.Color.orange()
            )
            embed.add_field(name="Retry Count", value=f"`{self._retry_count}`", inline=True)
            embed.add_field(name="Persistent Mode", value="✅ Enabled" if self._retry_enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Elapsed Time", value=f"`{elapsed}s`", inline=True)
            embed.set_footer(text="Use /tiktok disconnect to cancel the connection attempt")
        else:
            embed = discord.Embed(
                title="❌ Not Connected",
                description="The bot is not currently connected to any TikTok LIVE stream.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Use /tiktok connect to start a connection")
        
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="disconnect", description="Disconnect from the TikTok LIVE stream.")
    async def disconnect(self, interaction: discord.Interaction):
        """Signals the TikTok client to disconnect or cancel connection attempt."""
        await interaction.response.defer(ephemeral=True)
        
        # Check if there's an active connection
        if self.is_connected and self.bot.tiktok_client:
            self._user_initiated_disconnect = True
            await interaction.followup.send("🔌 Disconnecting from TikTok LIVE... Session summary will be posted shortly.", ephemeral=True)
            await self.bot.tiktok_client.disconnect()
            return
        
        # Check if there's a connection attempt in progress
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            await interaction.followup.send("🛑 Connection attempt cancelled successfully.", ephemeral=True)
            return
        
        # Not connected or attempting to connect
        await interaction.followup.send("Not currently connected or attempting to connect to any stream.", ephemeral=True)

    def _reset_state(self):
        """Resets all internal state variables for the connection."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        
        self._connection_task = None
        self.bot.tiktok_client = None
        self._is_connected.clear()
        self.current_session_id = None
        self.live_host_username = None
        self._connect_interaction = None
        self._retry_enabled = False
        self._retry_count = 0
        self._connection_start_time = None
        self._user_initiated_disconnect = False
        logging.info("TIKTOK: Internal connection state has been reset.")

    async def _cleanup_connection(self):
        """Handles cleanup when disconnecting from TikTok LIVE."""
        if self.current_session_id:
            await self.bot.db.end_live_session(self.current_session_id)
            summary = await self.bot.db.get_live_session_summary(self.current_session_id)
            await self._post_live_summary(summary)
        self._reset_state()

    async def _post_live_summary(self, summary: Dict[str, int]):
        """Posts the live session summary to the post-live metrics channel."""
        metrics_channel_id = self.bot.settings_cache.get('post_live_metrics_channel_id')
        if not metrics_channel_id:
            logging.warning("Post-live metrics channel not configured. Use /setup-post-live-metrics to set it up.")
            return
        
        channel = self.bot.get_channel(int(metrics_channel_id))
        if not channel:
            logging.error(f"Post-live metrics channel {metrics_channel_id} not found.")
            return

        # FIXED BY JULES: Get ALL TikTok handles (linked and unlinked) sorted by engagement
        all_handles_stats = await self.bot.db.get_session_all_handles_stats(self.current_session_id)
        
        if not all_handles_stats:
            # No interactions at all
            embed = discord.Embed(
                title=f"📊 Post-Live Metrics: @{self.live_host_username}",
                description="No interactions were recorded during this session.",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Session ID: {self.current_session_id}")
            embed.timestamp = discord.utils.utcnow()
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                logging.error(f"Missing permissions to send metrics to channel {metrics_channel_id}")
            return

        def format_watch_time(seconds: float) -> str:
            """Format watch time from seconds to human-readable format."""
            if seconds is None or seconds == 0:
                return "0s"
            total_seconds = int(seconds)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            secs = total_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                return f"{minutes}m {secs}s"
            else:
                return f"{secs}s"

        # FIXED BY JULES: Build enhanced metrics table with ALL handles (linked and unlinked)
        linked_count = sum(1 for h in all_handles_stats if h['linked_discord_id'] is not None)
        unlinked_count = sum(1 for h in all_handles_stats if h['linked_discord_id'] is None)
        
        embed = discord.Embed(
            title=f"📊 Post-Live Metrics: @{self.live_host_username}",
            description=f"**Session Summary**\nTotal participants: {len(all_handles_stats)} ({linked_count} linked, {unlinked_count} unlinked)\nSorted by engagement (coins > interactions)",
            color=discord.Color.blurple()
        )
        
        # Add table header with new columns
        table_lines = [
            "```",
            "TikTok Handle     | Lvl | Watch | Like | Cmt | Shr | Fol | Sub | Gft | Coins",
            "-" * 85
        ]
        
        # Add handle rows (limit to 20 to fit Discord embed limits)
        for handle_data in all_handles_stats[:20]:
            tiktok_handle = handle_data['tiktok_username'][:17]
            user_level = handle_data.get('user_level', 0) or 0
            watch_time = format_watch_time(handle_data.get('watch_time_seconds', 0))
            
            row = (
                f"{tiktok_handle:<17} | {user_level:<3} | {watch_time:<5} | "
                f"{int(handle_data['likes']):<4} | {int(handle_data['comments']):<3} | "
                f"{int(handle_data['shares']):<3} | {int(handle_data.get('follows', 0)):<3} | "
                f"{int(handle_data.get('subscribes', 0)):<3} | {int(handle_data.get('gifts', 0)):<3} | {int(handle_data['gift_coins']):<5}"
            )
            table_lines.append(row)
        
        table_lines.append("```")
        
        if len(all_handles_stats) > 20:
            table_lines.append(f"\n*...and {len(all_handles_stats) - 20} more participant(s)*")
        
        # Join table lines and check length
        table_content = "\n".join(table_lines)
        
        # Discord embed field value limit is 1024 characters
        if len(table_content) > 1024:
            # Truncate the table to fit within limit
            lines_to_keep = table_lines[:3]  # Keep header and separator
            max_data_rows = 10  # Limit to 10 data rows
            
            for i, line in enumerate(table_lines[3:], start=3):
                if i >= 3 + max_data_rows:
                    break
                if len("\n".join(lines_to_keep + [line] + ["```"])) > 1000:
                    break
                lines_to_keep.append(line)
            
            lines_to_keep.append("```")
            lines_to_keep.append(f"\n*...showing {len(lines_to_keep) - 4} of {len(all_handles_stats)} participants (truncated to fit)*")
            table_content = "\n".join(lines_to_keep)
        
        embed.add_field(
            name="User Interaction Metrics",
            value=table_content,
            inline=False
        )
        
        # Get viewer count statistics
        viewer_stats = await self.bot.db.get_session_viewer_stats(self.current_session_id)
        
        # Add overall session stats as fields
        embed.add_field(name="👍 Likes", value=f"{summary.get('like', 0):,}", inline=True)
        embed.add_field(name="💬 Comments", value=f"{summary.get('comment', 0):,}", inline=True)
        embed.add_field(name="📣 Shares", value=f"{summary.get('share', 0):,}", inline=True)
        embed.add_field(name="➕ Follows", value=f"{summary.get('follow', 0):,}", inline=True)
        embed.add_field(name="⭐ Subscribes", value=f"{summary.get('subscribe', 0):,}", inline=True)
        embed.add_field(name="🎁 Gifts", value=f"{summary.get('gift', 0):,}", inline=True)
        embed.add_field(name="💎 Coins", value=f"{summary.get('gift_coins', 0):,}", inline=True)
        
        # Add viewer statistics if available
        if viewer_stats['snapshot_count'] > 0:
            embed.add_field(
                name="👥 Viewers",
                value=f"Peak: {viewer_stats['max_viewers']:,}\nAvg: {viewer_stats['avg_viewers']:,}\nMin: {viewer_stats['min_viewers']:,}",
                inline=True
            )
        
        embed.set_footer(text=f"Session ID: {self.current_session_id}")
        embed.timestamp = discord.utils.utcnow()

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logging.error(f"Missing permissions to send metrics to channel {metrics_channel_id}")

    # --- Event Handlers ---
    async def on_connect(self, _: ConnectEvent):
        """Handles the connection event, starting a new live session."""
        self._is_connected.set()
        logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")

        if self.live_host_username:
            self.current_session_id = await self.bot.db.start_live_session(self.live_host_username)
            logging.info(f"TIKTOK: Started live session with ID {self.current_session_id}")
            
            # Send connection success notification to debug channel
            embed = discord.Embed(
                title="✅ TikTok Stream Connected",
                description=f"Successfully connected to TikTok LIVE stream.",
                color=discord.Color.green()
            )
            embed.add_field(name="Username", value=f"@{self.live_host_username}", inline=True)
            embed.add_field(name="Room ID", value=f"{self.bot.tiktok_client.room_id}", inline=True)
            embed.add_field(name="Session ID", value=f"{self.current_session_id}", inline=True)
            embed.set_footer(text="Monitoring interactions and engagement")
            embed.timestamp = discord.utils.utcnow()
            
            await self._send_debug_notification(embed)

        if self._connect_interaction:
            await self._connect_interaction.edit_original_response(
                embed=self._create_status_embed("✅ Connected!", f"Successfully connected to **{self.bot.tiktok_client.unique_id}**'s LIVE stream.", discord.Color.green())
            )

    async def on_disconnect(self, _: DisconnectEvent):
        """Handles the disconnect event from TikTok LIVE."""
        was_user_initiated = self._user_initiated_disconnect
        
        if was_user_initiated:
            # ENHANCED MONITORING: Clear disconnect status
            logging.info("🔌 TIKTOK DISCONNECTED: User-initiated disconnect from stream. Cleaning up...")
        else:
            logging.warning("TIKTOK: Unexpected disconnect from stream (stream may have ended). Cleaning up...")
            
            # Send notification to debug channel for unexpected disconnects
            if self.live_host_username and self._connection_start_time:
                elapsed = int(time.time() - self._connection_start_time)
                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
                
                embed = discord.Embed(
                    title="⚠️ TikTok Stream Disconnected",
                    description=f"The TikTok LIVE stream has ended or connection was lost.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Username", value=f"@{self.live_host_username}", inline=True)
                embed.add_field(name="Connection Duration", value=uptime_str, inline=True)
                embed.add_field(name="Session ID", value=f"{self.current_session_id or 'N/A'}", inline=True)
                embed.set_footer(text="Post-live metrics will be posted to the configured metrics channel")
                embed.timestamp = discord.utils.utcnow()
                
                await self._send_debug_notification(embed)
        
        await self._cleanup_connection()

    async def _handle_interaction(self, event, interaction_type: str, points: int, value: Optional[str] = None, coin_value: Optional[int] = None):
        """Generic interaction logger and point awarder with comprehensive debug logging."""
        if not self.current_session_id or not hasattr(event, 'user') or not hasattr(event.user, 'unique_id'):
            return

        try:
            # Extract user level if available
            user_level = None
            if hasattr(event, 'user') and hasattr(event.user, 'badge'):
                user_level = getattr(event.user.badge, 'level', None)
            
            # DEBUG: Log complete event data
            logging.debug(f"TIKTOK EVENT DEBUG [{interaction_type.upper()}]:")
            logging.debug(f"  User: {event.user.unique_id}")
            logging.debug(f"  Level: {user_level}")
            logging.debug(f"  Points: {points}")
            logging.debug(f"  Value: {value}")
            logging.debug(f"  Coins: {coin_value}")
            logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
            
            tiktok_account_id = await self.bot.db.upsert_tiktok_account(event.user.unique_id)
            await self.bot.db.log_tiktok_interaction(self.current_session_id, tiktok_account_id, interaction_type, value, coin_value, user_level)

            # Update user level if available
            if user_level is not None:
                await self.bot.db.update_tiktok_user_level(event.user.unique_id, user_level)

            # Add points to TikTok handle directly (regardless of Discord link)
            await self.bot.db.add_points_to_tiktok_handle(event.user.unique_id, points)
            
            # Also add points to linked Discord user if exists
            discord_id = await self.bot.db.get_discord_id_from_handle(event.user.unique_id)
            if discord_id:
                await self.bot.db.add_points_to_user(discord_id, points)
                
            logging.info(f"TIKTOK: {interaction_type.capitalize()} from {event.user.unique_id} (Level {user_level}) - {points} points")
        except TypeError as e:
            # ENHANCED MONITORING: Handle nickName vs nick_name mismatch from TikTok API
            if 'nickName' in str(e) or 'nick_name' in str(e):
                logging.warning(f"🔄 SCHEMA MISMATCH DETECTED: TikTok API changed user data format")
                logging.warning(f"   Error: {e}")
                logging.warning(f"   Event type: {interaction_type}")
                logging.warning(f"   Raw event user data: {vars(event.user) if hasattr(event, 'user') and hasattr(event.user, '__dict__') else 'N/A'}")
                logging.warning(f"   🛡️ Attempting fallback processing to preserve data...")
                
                # Continue processing with whatever data we can extract
                try:
                    unique_id = getattr(event.user, 'unique_id', None) if hasattr(event, 'user') else None
                    if unique_id:
                        tiktok_account_id = await self.bot.db.upsert_tiktok_account(unique_id)
                        await self.bot.db.log_tiktok_interaction(
                            self.current_session_id, 
                            tiktok_account_id, 
                            interaction_type, 
                            value, 
                            coin_value,
                            None  # user_level
                        )
                        await self.bot.db.add_points_to_tiktok_handle(unique_id, points)
                        discord_id = await self.bot.db.get_discord_id_from_handle(unique_id)
                        if discord_id:
                            await self.bot.db.add_points_to_user(discord_id, points)
                        logging.info(f"✅ FALLBACK SUCCESS: {interaction_type.capitalize()} from @{unique_id} processed - {points} points awarded")
                except Exception as fallback_error:
                    logging.error(f"❌ FALLBACK FAILED for {interaction_type}: {fallback_error}", exc_info=True)
            else:
                logging.error(f"Failed to handle TikTok interaction ({interaction_type}): {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Failed to handle TikTok interaction ({interaction_type}): {e}", exc_info=True)

    async def on_join(self, event: JoinEvent):
        """Captures TikTok handles when users join the stream (no points awarded for joining)."""
        if not self.current_session_id or not hasattr(event, 'user') or not hasattr(event.user, 'unique_id'):
            return
        
        try:
            # Just capture the handle in the database, no points awarded
            await self.bot.db.upsert_tiktok_account(event.user.unique_id)
            
            # ENHANCED MONITORING: Confirmation message for join events
            logging.info(f"👋 JOIN EVENT: @{event.user.unique_id} entered the stream (handle captured)")
            logging.debug(f"TIKTOK EVENT DEBUG [JOIN]:")
            logging.debug(f"  User: {event.user.unique_id}")
            logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
        except Exception as e:
            logging.error(f"Failed to capture TikTok join event: {e}", exc_info=True)

    async def on_like(self, event: LikeEvent):
        await self._handle_interaction(event, 'like', INTERACTION_POINTS['like'])

    async def on_comment(self, event: CommentEvent):
        # ENHANCED MONITORING: Log comment reception
        logging.info(f"💬 COMMENT EVENT: @{event.user.unique_id if hasattr(event, 'user') and hasattr(event.user, 'unique_id') else 'unknown'} - '{event.comment if hasattr(event, 'comment') else 'N/A'}'")
        await self._handle_interaction(event, 'comment', INTERACTION_POINTS['comment'], value=event.comment)

    async def on_share(self, event: ShareEvent):
        await self._handle_interaction(event, 'share', INTERACTION_POINTS['share'])

    async def on_follow(self, event: FollowEvent):
        await self._handle_interaction(event, 'follow', INTERACTION_POINTS['follow'])

    async def on_gift(self, event: GiftEvent):
        # Safe check for streakable attribute (may not exist on all gift types)
        try:
            is_streakable = hasattr(event.gift, 'streakable') and getattr(event.gift, 'streakable', False)
            is_streaking = hasattr(event, 'streaking') and getattr(event, 'streaking', False)
            
            # Skip if this is a streakable gift and the streak is still ongoing
            if is_streakable and is_streaking:
                return
        except AttributeError as e:
            logging.warning(f"Gift streakable check failed (gift: {event.gift.name if hasattr(event.gift, 'name') else 'unknown'}): {e}")

        # Award points for all gifts
        # Updated point logic: 2 points per coin for gifts under 1000, otherwise 1 point per coin
        try:
            diamond_count = getattr(event.gift, 'diamond_count', 0)
            gift_name = getattr(event.gift, 'name', 'Unknown Gift')
            
            if diamond_count < 1000:
                points = diamond_count * 2
            else:
                points = diamond_count

            await self._handle_interaction(event, 'gift', points, value=gift_name, coin_value=diamond_count)
        except Exception as e:
            logging.error(f"Error processing gift points: {e}", exc_info=True)
            return

        # Tiered skip logic
        target_line_name: Optional[str] = None
        try:
            diamond_count = getattr(event.gift, 'diamond_count', 0)
            for coins, line_name in sorted(GIFT_TIER_MAP.items(), key=lambda item: item[0], reverse=True):
                if diamond_count >= coins:
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
                        logging.info(f"TIKTOK: Rewarded user {discord_id} with move to {target_line_name} for a {diamond_count}-coin gift.")
                        user = self.bot.get_user(discord_id)
                        if user:
                            try:
                                await user.send(f"🎉 Thank you for the {diamond_count}-coin gift! Your submission **{submission['artist_name']} - {submission['song_name']}** has been moved to the **{target_line_name}** queue as a reward.")
                            except discord.Forbidden:
                                pass # Can't send DMs, oh well
                except Exception as e:
                    logging.error(f"Error processing tiered gift reward: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error in tiered skip logic: {e}", exc_info=True)
    
    async def on_subscribe(self, event: SubscribeEvent):
        """Handles user subscriptions to the streamer."""
        logging.debug(f"TIKTOK EVENT DEBUG [SUBSCRIBE]:")
        logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
        await self._handle_interaction(event, 'subscribe', INTERACTION_POINTS['subscribe'])
    
    async def on_live_end(self, event: LiveEndEvent):
        """Handles the LiveEndEvent when the stream officially ends."""
        logging.info("TIKTOK: LiveEndEvent received - stream officially ended")
        logging.debug(f"TIKTOK EVENT DEBUG [LIVE_END]:")
        logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
        # The disconnect handler will clean everything up
    
    async def on_viewer_update(self, event: RoomUserSeqEvent):
        """Handles viewer count updates and logs them periodically."""
        if not self.current_session_id:
            return
        
        try:
            # Get viewer count from the event itself
            viewer_count = getattr(event, 'viewer_count', 0)
            
            # ENHANCED MONITORING: Validate viewer count data
            if viewer_count == 0:
                logging.warning(f"⚠️ VIEWER COUNT WARNING: Received 0 viewers - stream may be offline or data unavailable")
                logging.warning(f"Event data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
            elif viewer_count > 0:
                logging.info(f"📊 VIEWER COUNT UPDATE: {viewer_count} active viewers")
            
            # DEBUG: Log viewer count updates
            logging.debug(f"TIKTOK EVENT DEBUG [VIEWER_UPDATE]:")
            logging.debug(f"  Viewer Count: {viewer_count}")
            logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
            
            # Log viewer count snapshot to database
            await self.bot.db.log_viewer_count(self.current_session_id, viewer_count)
            logging.debug(f"TIKTOK: Viewer count update - {viewer_count} viewers")
        except Exception as e:
            logging.error(f"Failed to handle viewer update: {e}", exc_info=True)
    
    async def on_poll(self, event: PollEvent):
        """Handles poll events from the stream."""
        if not self.current_session_id:
            return
        
        try:
            # Extract poll data
            poll_data = {
                'question': getattr(event, 'question', 'Unknown'),
                'options': getattr(event, 'options', []),
                'duration': getattr(event, 'duration', 0)
            }
            
            logging.info(f"TIKTOK: Poll started - {poll_data['question']}")
            logging.debug(f"TIKTOK EVENT DEBUG [POLL]:")
            logging.debug(f"  Question: {poll_data['question']}")
            logging.debug(f"  Options: {poll_data['options']}")
            logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
            
            # Log as a special interaction (no specific user)
            import json
            if hasattr(event, 'user') and hasattr(event.user, 'unique_id'):
                tiktok_account_id = await self.bot.db.upsert_tiktok_account(event.user.unique_id)
                await self.bot.db.log_tiktok_interaction(
                    self.current_session_id, 
                    tiktok_account_id, 
                    'poll', 
                    json.dumps(poll_data)
                )
        except Exception as e:
            logging.error(f"Failed to handle poll event: {e}", exc_info=True)
    
    async def on_mic_battle(self, event: LinkMicBattleEvent):
        """Handles mic battle events from the stream."""
        if not self.current_session_id:
            return
        
        try:
            # Extract battle data
            battle_data = {
                'battle_users': getattr(event, 'battle_users', []),
                'status': getattr(event, 'status', 'unknown')
            }
            
            logging.info(f"TIKTOK: Mic Battle event - Status: {battle_data['status']}")
            logging.debug(f"TIKTOK EVENT DEBUG [MIC_BATTLE]:")
            logging.debug(f"  Battle Users: {battle_data['battle_users']}")
            logging.debug(f"  Status: {battle_data['status']}")
            logging.debug(f"  Full Event Data: {vars(event) if hasattr(event, '__dict__') else 'N/A'}")
            
            # Log as a special interaction
            import json
            if hasattr(event, 'user') and hasattr(event.user, 'unique_id'):
                tiktok_account_id = await self.bot.db.upsert_tiktok_account(event.user.unique_id)
                await self.bot.db.log_tiktok_interaction(
                    self.current_session_id, 
                    tiktok_account_id, 
                    'mic_battle', 
                    json.dumps(battle_data)
                )
        except Exception as e:
            logging.error(f"Failed to handle mic battle event: {e}", exc_info=True)

    # --- Background Tasks ---
    # FIXED BY Replit: Points tracking with periodic sync - verified working
    @tasks.loop(seconds=15)
    async def score_sync_task(self):
        """Periodically syncs the user points with the submission scores in the free queue."""
        try:
            await self.bot.db.sync_submission_scores()
        except Exception as e:
            logging.error(f"Error in score_sync_task: {e}", exc_info=True)
    
    # FIXED BY JULES: Periodic backup task for points tracking data
    @tasks.loop(hours=1)
    async def points_backup_task(self):
        """Periodically creates a backup log of points data for recovery purposes."""
        try:
            import json
            from datetime import datetime
            
            # Get all user points
            async with self.bot.db.pool.acquire() as conn:
                user_points = await conn.fetch("SELECT user_id, points FROM user_points WHERE points > 0")
                tiktok_points = await conn.fetch("SELECT handle_name, points, linked_discord_id FROM tiktok_accounts WHERE points > 0")
            
            backup_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_points": [{"user_id": row['user_id'], "points": row['points']} for row in user_points],
                "tiktok_points": [{"handle": row['handle_name'], "points": row['points'], "linked_discord_id": row['linked_discord_id']} for row in tiktok_points]
            }
            
            # Write to backup file (rotating, keep last 24 backups)
            backup_file = f"points_backup_{datetime.utcnow().strftime('%Y%m%d_%H')}.json"
            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            logging.info(f"Points backup completed: {len(user_points)} users, {len(tiktok_points)} TikTok handles")
        except Exception as e:
            logging.error(f"Error in points_backup_task: {e}", exc_info=True)

    @score_sync_task.before_loop
    async def before_score_sync_task(self):
        await self.bot.wait_until_ready()
    
    # FIXED BY JULES: Ensure backup task waits for bot to be ready
    @points_backup_task.before_loop
    async def before_points_backup_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TikTokCog(bot))