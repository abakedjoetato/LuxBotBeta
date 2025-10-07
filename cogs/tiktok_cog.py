import discord
import logging
import asyncio
from discord.ext import commands
from discord import app_commands
from typing import Optional, Any

class TikTokCog(commands.Cog):
    """A cog for debugging the TikTok command loading issue. Step 2: Add connection logic."""

    def __init__(self, bot):
        self.bot = bot
        logging.info("--- TikTokCog with Connection Logic IS BEING INITIALIZED ---")
        self.bot.tiktok_client: Optional[Any] = None
        self._is_connected = asyncio.Event()
        self._connection_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        if self.bot.tiktok_client:
            asyncio.create_task(self.bot.tiktok_client.stop())

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
        """Connects the bot to a specified TikTok Live stream."""
        # Defer the import until the command is actually used
        from TikTokLive import TikTokLiveClient
        from TikTokLive.types.events import ConnectEvent, DisconnectEvent

        await interaction.response.defer(ephemeral=True, thinking=True)

        if self.is_connected:
            await interaction.followup.send("Already connected to a TikTok LIVE. Please disconnect first.", ephemeral=True)
            return

        if self.bot.tiktok_client:
             await self.bot.tiktok_client.stop()

        try:
            clean_unique_id = unique_id.strip().lstrip('@')
            self.bot.tiktok_client = TikTokLiveClient(unique_id=f"@{clean_unique_id}")

            # Add only the essential listeners
            # We need to wrap the event handlers to pass the event types without a top-level import
            async def on_connect_wrapper(event: ConnectEvent):
                await self.on_connect(event)

            async def on_disconnect_wrapper(event: DisconnectEvent):
                await self.on_disconnect(event)

            self.bot.tiktok_client.add_listener("connect", on_connect_wrapper)
            self.bot.tiktok_client.add_listener("disconnect", on_disconnect_wrapper)

            self._connection_task = asyncio.create_task(self.bot.tiktok_client.start())

            await asyncio.wait_for(self._is_connected.wait(), timeout=15.0)

            await interaction.followup.send(f"✅ Successfully connected to `@{clean_unique_id}`'s LIVE stream.", ephemeral=True)

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

    async def _cleanup_connection(self):
        """Helper to stop the client and reset state."""
        if self.bot.tiktok_client:
            await self.bot.tiktok_client.stop()
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        self.bot.tiktok_client = None
        self._is_connected.clear()
        logging.info("TIKTOK: Connection cleaned up.")

    # --- TikTok Event Handlers ---
    async def on_connect(self, _):
        """Handles the connection event from the TikTok client."""
        if self.bot.tiktok_client:
            logging.info(f"TIKTOK: Connected to room ID {self.bot.tiktok_client.room_id}")
        self._is_connected.set()

    async def on_disconnect(self, _):
        """Handles the disconnection event."""
        logging.info("TIKTOK: Disconnected from stream.")
        await self._cleanup_connection()


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(TikTokCog(bot))