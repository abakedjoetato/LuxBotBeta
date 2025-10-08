"""
Discord Music Queue Bot - Main Entry Point
TikTok-style music review queue system with slash commands and Discord UI components
"""

import asyncio
import os
import logging
import traceback
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from database import Database
from cogs.queue_view import PaginatedQueueView
import aiohttp

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

        # Initialize database with the connection URL from environment variables
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is not set.")
        self.db = Database(db_url)

        self.initial_startup = True
        self.settings_cache = {}
        self.tiktok_client = None
        self.http_session = None

    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        logging.info("setup_hook() started.")
        self.http_session = aiohttp.ClientSession()
        logging.info("HTTP session started.")
        logging.info("Initializing database...")
        await self.db.initialize()
        logging.info("Database initialized.")

        logging.info("Loading cogs...")
        cogs_to_load = [
            'cogs.queue_view', 'cogs.submission_cog', 'cogs.queue_cog',
            'cogs.admin_cog', 'cogs.moderation_cog', 'cogs.tiktok_cog',
            'cogs.debug_cog'
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logging.info(f"Successfully loaded cog: {cog}")
            except Exception as e:
                logging.error(f"Failed to load cog {cog}: {e}", exc_info=True)
        logging.info("Finished loading cogs.")

        logging.info("Syncing slash commands...")
        try:
            guild_id = os.getenv('GUILD_ID')
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logging.info(f"Synced {len(synced)} command(s) to guild {guild_id}.")
            else:
                synced = await self.tree.sync()
                logging.info(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            logging.error(f"Failed to sync commands: {e}", exc_info=True)
        logging.info("Finished syncing commands.")

    async def on_ready(self):
        """Called when bot is ready"""
        logging.info(f"on_ready() started. Logged in as {self.user}. In {len(self.guilds)} guild(s).")

        activity = discord.Activity(type=discord.ActivityType.listening, name="music submissions | /help")
        await self.change_presence(activity=activity)
        logging.info("Presence set.")

        if self.initial_startup:
            logging.info("Initial startup tasks beginning.")
            self.settings_cache = await self.db.get_all_bot_settings()
            logging.info("Settings cache loaded.")

            self.add_view(PaginatedQueueView(self, queue_line="dummy"))
            logging.info("Persistent views registered.")

            queue_view_cog = self.get_cog('QueueViewCog')
            if queue_view_cog:
                asyncio.create_task(queue_view_cog.initialize_all_views())
                logging.info("Queue view initialization started in background.")
            else:
                logging.error("QueueViewCog NOT found.")

            self.initial_startup = False
            logging.info("Initial startup tasks complete.")

    async def _log_error_to_channel(self, error: Exception, context_object):
        """Helper function to log an error to the debug channel."""
        debug_channel_id = self.settings_cache.get('debug_channel_id')
        if not debug_channel_id:
            return  # No debug channel set

        channel = self.get_channel(debug_channel_id)
        if not channel:
            logging.warning(f"Debug channel with ID {debug_channel_id} not found.")
            return

        traceback_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        # Truncate if too long for a single message
        if len(traceback_str) > 1900:
            traceback_str = traceback_str[:1900] + "\n... (truncated)"

        embed = discord.Embed(
            title="Bot Error Report",
            description=f"An error occurred.",
            color=discord.Color.red()
        )
        if isinstance(context_object, discord.Interaction):
            embed.add_field(name="Command", value=f"`{context_object.command.name}`", inline=False)
            embed.add_field(name="User", value=context_object.user.mention, inline=False)
        elif isinstance(context_object, commands.Context):
            embed.add_field(name="Command", value=f"`{context_object.command.name}`", inline=False)
            embed.add_field(name="User", value=context_object.author.mention, inline=False)

        embed.add_field(name="Traceback", value=f"```python\n{traceback_str}\n```", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logging.error("Failed to send error log to debug channel due to permissions.")
        except Exception as e:
            logging.error(f"An unexpected error occurred while logging to debug channel: {e}")

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for slash commands."""
        logging.error(f"Slash command error: {error}", exc_info=True)
        await self._log_error_to_channel(error, interaction)

        # Send a user-friendly message
        if interaction.response.is_done():
            await interaction.followup.send("An unexpected error occurred. The developers have been notified.", ephemeral=True)
        else:
            await interaction.response.send_message("An unexpected error occurred. The developers have been notified.", ephemeral=True)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Global error handler for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return # Ignore commands that don't exist

        logging.error(f"Command error: {error}", exc_info=True)
        await self._log_error_to_channel(error, ctx)

        if hasattr(ctx, 'send'):
            await ctx.send("An unexpected error occurred. The developers have been notified.")

    async def close(self):
        """Gracefully close bot connections."""
        if self.http_session:
            await self.http_session.close()
            logging.info("HTTP session closed.")
        logging.info("Closing database connection pool...")
        await self.db.close()
        await super().close()

async def main():
    """Main function to run the bot"""
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logging.critical("DISCORD_BOT_TOKEN environment variable not found!")
        return

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.critical("DATABASE_URL environment variable not found!")
        return

    bot = MusicQueueBot()
    try:
        await bot.start(token)
    except Exception as e:
        logging.critical(f"Bot failed to start: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested by user.")
    except Exception as e:
        logging.critical(f"Fatal error in main loop: {e}", exc_info=True)