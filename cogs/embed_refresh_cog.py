"""
Embed Refresh Cog - Auto-updates all persistent embeds every 10 seconds.
Implements rate limit protection and delta checking for performance.
"""

import discord
import asyncio
import hashlib
import logging
from discord.ext import commands, tasks
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class EmbedRefreshCog(commands.Cog):
    """Cog for auto-refreshing persistent embeds every 10 seconds."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.refresh_count = 0
        self.error_count = 0
        self.last_status_log = datetime.utcnow()
        self.rate_limit_delay = 1.0  # 1 second between embed updates to prevent rate limits
        
    async def cog_load(self):
        """Start the auto-refresh loop when the cog loads."""
        logging.info("EmbedRefreshCog loaded. Starting auto-refresh loop...")
        self.auto_refresh_loop.start()
        
    async def cog_unload(self):
        """Stop the auto-refresh loop when the cog unloads."""
        self.auto_refresh_loop.cancel()
        logging.info("EmbedRefreshCog unloaded. Auto-refresh loop stopped.")
    
    @tasks.loop(seconds=10)
    async def auto_refresh_loop(self):
        """Main auto-refresh loop that runs every 10 seconds."""
        try:
            active_embeds = await self.bot.db.get_all_active_persistent_embeds()
            
            if not active_embeds:
                return
            
            # Refresh each active embed with rate limit protection
            for embed_data in active_embeds:
                try:
                    await self._refresh_single_embed(embed_data)
                    await asyncio.sleep(self.rate_limit_delay)
                except discord.NotFound:
                    # Message was deleted - deactivate this embed
                    await self.bot.db.deactivate_persistent_embed(
                        embed_data['embed_type'],
                        embed_data['channel_id']
                    )
                    logging.warning(
                        f"Embed {embed_data['embed_type']} in channel {embed_data['channel_id']} "
                        f"was deleted. Deactivated from auto-refresh."
                    )
                except discord.Forbidden:
                    logging.error(
                        f"No permission to edit embed {embed_data['embed_type']} in channel {embed_data['channel_id']}"
                    )
                except Exception as e:
                    self.error_count += 1
                    logging.error(
                        f"Failed to refresh embed {embed_data['embed_type']}: {e}",
                        exc_info=True
                    )
            
            # Log status every minute
            if (datetime.utcnow() - self.last_status_log).total_seconds() >= 60:
                logging.info(
                    f"📊 Auto-Refresh Status: {len(active_embeds)} active embeds | "
                    f"{self.refresh_count} total refreshes | {self.error_count} errors"
                )
                self.last_status_log = datetime.utcnow()
                
        except Exception as e:
            logging.error(f"Error in auto_refresh_loop: {e}", exc_info=True)
    
    @auto_refresh_loop.before_loop
    async def before_auto_refresh_loop(self):
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()
        logging.info("✅ Auto-refresh loop ready to start.")
    
    async def _refresh_single_embed(self, embed_data: Dict[str, Any]) -> None:
        """Refresh a single persistent embed."""
        embed_type = embed_data['embed_type']
        channel_id = embed_data['channel_id']
        message_id = embed_data['message_id']
        stored_page = embed_data['current_page']
        
        # Get the channel and message
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logging.warning(f"Channel {channel_id} not found for embed {embed_type}")
            return
        
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            # Message deleted - will be handled in the caller
            raise
        except Exception as e:
            logging.error(f"Failed to fetch message {message_id}: {e}")
            return
        
        # Route to appropriate refresh method based on embed type
        if embed_type == 'public_live_queue':
            await self._refresh_public_queue(channel, message, stored_page)
        elif embed_type == 'reviewer_main_queue':
            await self._refresh_reviewer_main_queue(channel, message, stored_page)
        elif embed_type == 'reviewer_pending_skips':
            await self._refresh_reviewer_pending_skips(channel, message, stored_page)
        else:
            logging.warning(f"Unknown embed type: {embed_type}")
            return
        
        self.refresh_count += 1
    
    async def _refresh_public_queue(self, channel: discord.TextChannel, message: discord.Message, page: int) -> None:
        """Refresh the public live queue embed."""
        cog = self.bot.get_cog('LiveQueueCog')
        if not cog:
            return
        
        # Update the cog's current page from database
        cog.current_page = page
        cog.queue_message = message
        
        # Call the update method with from_auto_refresh=True
        await cog.update_display(from_auto_refresh=True)
    
    async def _refresh_reviewer_main_queue(self, channel: discord.TextChannel, message: discord.Message, page: int) -> None:
        """Refresh the reviewer main queue embed."""
        cog = self.bot.get_cog('ReviewerCog')
        if not cog:
            return
        
        # Update the cog's current page from database
        cog.main_queue_page = page
        cog.main_queue_message = message
        
        # Call the update method with from_auto_refresh=True
        await cog.update_main_queue_display(from_auto_refresh=True)
    
    async def _refresh_reviewer_pending_skips(self, channel: discord.TextChannel, message: discord.Message, page: int) -> None:
        """Refresh the reviewer pending skips embed."""
        cog = self.bot.get_cog('ReviewerCog')
        if not cog:
            return
        
        # Update the cog's current page from database
        cog.pending_skips_page = page
        cog.pending_skips_message = message
        
        # Call the update method with from_auto_refresh=True
        await cog.update_pending_skips_display(from_auto_refresh=True)
    
    @commands.command(name="refresh-stats")
    @commands.has_permissions(administrator=True)
    async def refresh_stats(self, ctx: commands.Context):
        """Display auto-refresh statistics."""
        active_embeds = await self.bot.db.get_all_active_persistent_embeds()
        
        embed = discord.Embed(
            title="🔄 Auto-Refresh Statistics",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="Active Embeds", value=str(len(active_embeds)), inline=True)
        embed.add_field(name="Total Refreshes", value=str(self.refresh_count), inline=True)
        embed.add_field(name="Error Count", value=str(self.error_count), inline=True)
        embed.add_field(name="Refresh Interval", value="Every 5 seconds", inline=True)
        embed.add_field(name="Rate Limit Delay", value=f"{int(self.rate_limit_delay * 1000)}ms between embeds", inline=True)
        
        if active_embeds:
            embed_list = "\n".join([
                f"• **{e['embed_type']}** in <#{e['channel_id']}> (Page {e['current_page']})"
                for e in active_embeds
            ])
            embed.add_field(name="Active Embed List", value=embed_list, inline=False)
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedRefreshCog(bot))
