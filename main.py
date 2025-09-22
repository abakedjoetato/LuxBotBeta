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
    
    def __init__(self):
        # Define intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(
            command_prefix='!',  # Fallback prefix, we're using slash commands
            intents=intents,
            help_command=None
        )
        
        # Initialize database
        self.db = Database()
        
    async def setup_hook(self):
        """Setup hook called when bot is starting"""
        # Initialize database
        await self.db.initialize()
        
        # Load cogs
        try:
            await self.load_extension('cogs.submission_cog')
            await self.load_extension('cogs.queue_cog')
            await self.load_extension('cogs.admin_cog')
            logging.info("All cogs loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load cogs: {e}")
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logging.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logging.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when bot is ready"""
        logging.info(f'{self.user} has connected to Discord!')
        logging.info(f'Bot is in {len(self.guilds)} guild(s)')
        
        # Set bot activity
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="music submissions | /help"
        )
        await self.change_presence(activity=activity)
    
    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        
        logging.error(f"Command error: {error}")
        
        if hasattr(ctx, 'send'):
            await ctx.send(f"An error occurred: {str(error)}")

async def main():
    """Main function to run the bot"""
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