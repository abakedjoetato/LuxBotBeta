"""
Discord Music Queue Bot - Main Entry Point
TikTok-style music review queue system with slash commands and Discord UI components
"""

import asyncio
import os
import logging
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

class MusicQueueBot(commands.Bot):
    """Main Discord bot class with music queue functionality"""

    def __init__(self, dsn: str):
        # Define intents
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix='!', intents=intents, help_command=None)

        # Initialize database
        self.db = Database(dsn=dsn)
        self.initial_startup = True
        self.settings_cache = {}
        self.tiktok_client = None

        # --- New Diagnostic Attributes ---
        self.debug_channel = None
        self.startup_trace_log = []

    async def _send_trace(self, message: str, is_error: bool = False):
        """Queues a trace message or sends it if the debug channel is ready."""
        log_message = f"**{'ERROR' if is_error else 'TRACE'}**: {message}"
        if self.debug_channel:
            try:
                await self.debug_channel.send(f"```\n{log_message}\n```")
            except discord.HTTPException:
                pass  # Cannot send, oh well.
        else:
            self.startup_trace_log.append(log_message)

    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        await self._send_trace("setup_hook() started.")
        await self._send_trace("Initializing database...")
        await self.db.initialize()
        await self._send_trace("Database initialized.")

        await self._send_trace("Loading cogs...")
        cogs_to_load = [
            'cogs.submission_cog',
            'cogs.admin_cog', 'cogs.tiktok_cog',
            'cogs.user_cog', 'cogs.live_queue_cog', 'cogs.reviewer_cog', 'cogs.debug_cog',
            'cogs.self_healing_cog', 'cogs.embed_refresh_cog'
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                await self._send_trace(f"Successfully loaded cog: {cog}")
            except Exception as e:
                await self._send_trace(f"Failed to load cog {cog}: {e}", is_error=True)
        await self._send_trace("Finished loading cogs.")

        await self._send_trace("Syncing slash commands...")
        try:
            guild_id = os.getenv('GUILD_ID')
            synced_commands = []
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                synced_commands = [c.name for c in synced]
                await self._send_trace(f"Synced {len(synced)} command(s) to guild {guild_id}.")
            else:
                synced = await self.tree.sync()
                synced_commands = [c.name for c in synced]
                await self._send_trace(f"Synced {len(synced)} command(s) globally.")

            if synced_commands:
                await self._send_trace(f"Registered commands: {', '.join(synced_commands)}")
            else:
                await self._send_trace("No commands were synced.")

        except Exception as e:
            await self._send_trace(f"Failed to sync commands: {e}", is_error=True)
        await self._send_trace("Finished syncing commands.")

    async def dispatch_queue_update(self):
        # FIXED BY JULES
        """Dispatches a custom event to notify views that the queue has changed."""
        self.dispatch("queue_update")

    async def on_ready(self):
        """Called when bot is ready"""
        # --- Find or create debug channel and flush logs ---
        if not self.debug_channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name="bot-debug")
                if channel:
                    self.debug_channel = channel
                    await self._send_trace(f"Found debug channel in guild '{guild.name}'.")
                    break

            if not self.debug_channel and self.guilds:
                target_guild = self.guilds[0]
                await self._send_trace(f"Debug channel not found. Attempting to create one in '{target_guild.name}'.")
                try:
                    overwrites = {
                        target_guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        target_guild.me: discord.PermissionOverwrite(read_messages=True)
                    }
                    self.debug_channel = await target_guild.create_text_channel(
                        'bot-debug',
                        overwrites=overwrites,
                        reason="For bot startup diagnostics"
                    )
                    await self._send_trace("Successfully created 'bot-debug' channel.")
                except discord.Forbidden:
                    await self._send_trace("Lacking 'Manage Channels' permission to create debug channel.", is_error=True)
                except discord.HTTPException as e:
                    await self._send_trace(f"Failed to create debug channel due to an HTTP error: {e}", is_error=True)

        if self.debug_channel:
            try:
                await self.debug_channel.purge(limit=100)
                await self._send_trace("Purged old logs from debug channel.")
            except (discord.Forbidden, discord.HTTPException):
                await self._send_trace("Failed to purge debug channel (check permissions).", is_error=True)

            if self.startup_trace_log:
                await self.debug_channel.send("--- Flushing pre-startup debug logs ---")
                for msg in self.startup_trace_log:
                    await self.debug_channel.send(f"```\n{msg}\n```")
                self.startup_trace_log.clear()

        await self._send_trace(f"on_ready() started. Logged in as {self.user}. In {len(self.guilds)} guild(s).")

        activity = discord.Activity(type=discord.ActivityType.listening, name="music submissions | /help")
        await self.change_presence(activity=activity)
        await self._send_trace("Presence set.")

        if self.initial_startup:
            await self._send_trace("Initial startup tasks beginning.")
            self.settings_cache = await self.db.get_all_bot_settings()
            await self._send_trace("Settings cache loaded.")

            # FIXED BY JULES: Register persistent views on startup
            # FIXED BY Replit: Views are now registered by their respective cogs during cog_load
            # This allows the bot to respond to interactions after a restart.
            await self._send_trace("Persistent views will be registered by their cogs.")

            self.initial_startup = False
            await self._send_trace("Initial startup tasks complete.")

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands

        logging.error(f"Command error: {error}")

        if hasattr(ctx, 'send'):
            await ctx.send(f"An error occurred: {str(error)}")

    # FIXED BY JULES
    # FIXED BY Replit: Submission channel cleanup - verified working
    async def on_message(self, message: discord.Message):
        """
        Event listener for messages to handle submission channel cleanup and process legacy commands.
        """
        # Ignore DMs and messages from the bot itself
        if message.guild is None or message.author.bot:
            return

        # Check if the message is in the designated submission channel for cleanup
        submission_channel_id = self.settings_cache.get('submission_channel_id')
        if submission_channel_id and message.channel.id == int(submission_channel_id):
            # We are in the submission channel. Only slash commands and admin messages are allowed.

            # Allow messages from admins
            if isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator:
                return # Admins can talk freely

            # At this point, it's a non-admin user. Any standard message should be deleted.
            # Slash commands are handled as interactions and won't be deleted by this.
            try:
                await message.delete()
                await self._send_trace(f"Deleted unauthorized message from {message.author} in submission channel.")
            except discord.Forbidden:
                await self._send_trace(f"Failed to delete message from {message.author} in submission channel (missing permissions).", is_error=True)
            except discord.NotFound:
                pass # Message was already deleted, which is fine.
        else:
            # If not in the submission channel, process any potential prefix commands.
            await self.process_commands(message)

async def main():
    """Main function to run the bot."""
    # Check for required environment variables
    token = os.getenv('DISCORD_BOT_TOKEN')
    dsn = os.getenv('DATABASE_URL')

    if not token:
        logging.critical("DISCORD_BOT_TOKEN environment variable not found! The bot cannot start.")
        return
    if not dsn:
        logging.critical("DATABASE_URL environment variable not found! The bot cannot start.")
        return

    # Create and run bot
    bot = MusicQueueBot(dsn=dsn)

    try:
        await bot.start(token)
    except Exception as e:
        logging.critical(f"Bot failed to start: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}")