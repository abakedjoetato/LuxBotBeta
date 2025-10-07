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
from cogs.queue_view import PaginatedQueueView

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

    def __init__(self):
        # Define intents
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix='!', intents=intents, help_command=None)

        # Initialize database
        self.db = Database()
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
            'cogs.queue_view', 'cogs.submission_cog', 'cogs.queue_cog',
            'cogs.admin_cog', 'cogs.moderation_cog', 'cogs.tiktok_cog'
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
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                await self._send_trace(f"Synced {len(synced)} command(s) to guild {guild_id}.")
            else:
                synced = await self.tree.sync()
                await self._send_trace(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            await self._send_trace(f"Failed to sync commands: {e}", is_error=True)
        await self._send_trace("Finished syncing commands.")

    async def on_ready(self):
        """Called when bot is ready"""
        # --- Find debug channel and flush logs ---
        if not self.debug_channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name="bot-debug")
                if channel:
                    self.debug_channel = channel
                    break

        if self.debug_channel and self.startup_trace_log:
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

            self.add_view(PaginatedQueueView(self, queue_line="dummy"))
            await self._send_trace("Persistent views registered.")

            queue_view_cog = self.get_cog('QueueViewCog')
            if queue_view_cog:
                # FIX: Run the slow initialization in the background
                asyncio.create_task(queue_view_cog.initialize_all_views())
                await self._send_trace("Queue view initialization started in background.")
            else:
                await self._send_trace("QueueViewCog NOT found.", is_error=True)

            self.initial_startup = False
            await self._send_trace("Initial startup tasks complete.")

    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands

        logging.error(f"Command error: {error}")

        if hasattr(ctx, 'send'):
            await ctx.send(f"An error occurred: {str(error)}")

async def main():
    """Main function to run the bot"""
    # Force a new commit to trigger a reboot
    # Check for bot token
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logging.error("DISCORD_BOT_TOKEN environment variable not found!")
        logging.info("Please set your Discord bot token in the environment variables.")
        logging.info("You can get a bot token from https://discord.com/developers/applications")
        return

    # Create and run bot
    bot = MusicQueueBot()

    try:
        await bot.start(token)
    except Exception as e:
        logging.error(f"Bot failed to start: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}")