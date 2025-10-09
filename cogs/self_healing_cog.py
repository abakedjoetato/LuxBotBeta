"""
Self-Healing Cog for Discord Music Queue Bot
Manages persistent view channels, auto-cleanup, and reconnection logic.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta

class SelfHealingCog(commands.Cog):
    """Cog for self-healing persistent view channels."""
    
    def __init__(self, bot):
        self.bot = bot
        self.persistent_channels: Dict[str, Dict[str, int]] = {}
        self.healing_in_progress = False
        
    async def cog_load(self):
        """On cog load, register the cog."""
        logging.info("SelfHealingCog loaded.")
    
    @commands.Cog.listener('on_ready')
    async def on_ready_heal(self):
        """Perform auto-healing after settings are loaded."""
        # Only run once (on initial startup)
        if not hasattr(self, '_auto_heal_ran'):
            self._auto_heal_ran = True
            logging.info("SelfHealingCog ready. Starting auto-healing sequence...")
            await self.auto_heal_on_startup()
    
    def get_persistent_channel_configs(self) -> List[Dict]:
        """Get all persistent channel configurations from settings."""
        configs = []
        
        # Reviewer channel config
        reviewer_channel_id = self.bot.settings_cache.get('reviewer_channel_id')
        if reviewer_channel_id:
            configs.append({
                'name': 'Reviewer Channel',
                'channel_id': reviewer_channel_id,
                'message_ids': [
                    self.bot.settings_cache.get('reviewer_main_queue_message_id'),
                    self.bot.settings_cache.get('reviewer_pending_skips_message_id')
                ],
                'message_keys': [
                    'reviewer_main_queue_message_id',
                    'reviewer_pending_skips_message_id'
                ],
                'allow_admin': True
            })
        
        # Live queue channel config
        live_queue_channel_id = self.bot.settings_cache.get('public_live_queue_channel_id')
        if live_queue_channel_id:
            configs.append({
                'name': 'Live Queue Channel',
                'channel_id': live_queue_channel_id,
                'message_ids': [
                    self.bot.settings_cache.get('public_live_queue_message_id')
                ],
                'message_keys': [
                    'public_live_queue_message_id'
                ],
                'allow_admin': True
            })
        
        # Debug channel (read-only for users)
        debug_channel_id = self.bot.settings_cache.get('debug_channel_id')
        if debug_channel_id:
            configs.append({
                'name': 'Debug Channel',
                'channel_id': debug_channel_id,
                'message_ids': [],
                'message_keys': [],
                'allow_admin': True,
                'cleanup_only': True  # Only cleanup, no persistent messages
            })
        
        # Metrics channel (read-only for users)
        metrics_channel_id = self.bot.settings_cache.get('post_live_metrics_channel_id')
        if metrics_channel_id:
            configs.append({
                'name': 'Metrics Channel',
                'channel_id': metrics_channel_id,
                'message_ids': [],
                'message_keys': [],
                'allow_admin': True,
                'cleanup_only': True
            })
        
        return configs
    
    async def auto_heal_on_startup(self):
        """Auto-healing sequence that runs on bot startup."""
        if self.healing_in_progress:
            logging.warning("Healing already in progress, skipping auto-heal.")
            return
        
        self.healing_in_progress = True
        try:
            logging.info("🏥 Starting auto-healing sequence...")
            
            # Wait a bit for other cogs to load
            import asyncio
            await asyncio.sleep(3)
            
            configs = self.get_persistent_channel_configs()
            
            for config in configs:
                await self.heal_channel(config)
            
            # Re-register all persistent views to ensure they're active
            await self.reregister_persistent_views()
            
            logging.info("✅ Auto-healing sequence completed successfully (views re-registered).")
        except Exception as e:
            logging.error(f"❌ Error during auto-healing: {e}", exc_info=True)
        finally:
            self.healing_in_progress = False
    
    async def heal_channel(self, config: Dict) -> Tuple[int, int]:
        """
        Heal a specific persistent channel.
        Returns: (cleaned_messages, reconnected_views)
        """
        channel_id = config['channel_id']
        channel_name = config['name']
        
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.bot.fetch_channel(int(channel_id))
            
            if not channel:
                logging.error(f"❌ {channel_name}: Channel not found (ID: {channel_id})")
                return (0, 0)
            
            logging.info(f"🔧 Healing {channel_name} (#{channel.name})...")
            
            # Step 1: Cleanup excess messages
            cleaned = await self.cleanup_channel_messages(channel, config)
            
            # Step 2: Verify/reconnect persistent views
            reconnected = 0
            if not config.get('cleanup_only', False):
                reconnected = await self.verify_persistent_views(channel, config)
            
            logging.info(f"✅ {channel_name}: Cleaned {cleaned} messages, reconnected {reconnected} views")
            return (cleaned, reconnected)
            
        except discord.Forbidden:
            logging.error(f"❌ {channel_name}: Missing permissions to access channel")
            return (0, 0)
        except Exception as e:
            logging.error(f"❌ {channel_name}: Error during healing: {e}", exc_info=True)
            return (0, 0)
    
    async def cleanup_channel_messages(self, channel: discord.TextChannel, config: Dict) -> int:
        """
        Clean up excess messages in a persistent channel.
        Keeps: Official persistent view messages and admin/mod messages.
        """
        # Convert message IDs to int for proper comparison
        official_message_ids = [int(mid) for mid in config.get('message_ids', []) if mid]
        allow_admin = config.get('allow_admin', True)
        
        messages_to_delete = []
        
        try:
            # Fetch recent messages (last 100)
            async for message in channel.history(limit=100):
                # Skip official persistent view messages
                if message.id in official_message_ids:
                    continue
                
                # Skip pinned messages
                if message.pinned:
                    continue
                
                # Skip admin/mod messages if configured
                if allow_admin and message.author.guild_permissions.administrator:
                    continue
                
                # Skip mod messages (users with manage_messages permission)
                if allow_admin and message.author.guild_permissions.manage_messages:
                    continue
                
                # Delete bot's old messages (older than 5 minutes)
                if message.author == self.bot.user:
                    message_age = datetime.utcnow() - message.created_at.replace(tzinfo=None)
                    if message_age > timedelta(minutes=5):
                        messages_to_delete.append(message)
                    continue
                
                # Delete regular user messages
                if not message.author.bot:
                    messages_to_delete.append(message)
            
            # Bulk delete messages (Discord limit: max 100 messages, not older than 14 days)
            if messages_to_delete:
                # Filter out messages older than 14 days (Discord limitation)
                recent_messages = [
                    m for m in messages_to_delete 
                    if (datetime.utcnow() - m.created_at.replace(tzinfo=None)) < timedelta(days=14)
                ]
                old_messages = [
                    m for m in messages_to_delete 
                    if (datetime.utcnow() - m.created_at.replace(tzinfo=None)) >= timedelta(days=14)
                ]
                
                # Bulk delete recent messages
                if recent_messages:
                    if len(recent_messages) == 1:
                        await recent_messages[0].delete()
                    else:
                        await channel.delete_messages(recent_messages)
                
                # Individual delete for old messages
                for msg in old_messages:
                    try:
                        await msg.delete()
                    except:
                        pass
                
                return len(messages_to_delete)
            
            return 0
            
        except discord.Forbidden:
            logging.error(f"Missing permissions to delete messages in {channel.name}")
            return 0
        except Exception as e:
            logging.error(f"Error cleaning up {channel.name}: {e}", exc_info=True)
            return 0
    
    async def verify_persistent_views(self, channel: discord.TextChannel, config: Dict) -> int:
        """
        Verify that persistent view messages exist and re-register views.
        Returns: Number of views reconnected.
        """
        reconnected = 0
        
        for message_key in config.get('message_keys', []):
            message_id = self.bot.settings_cache.get(message_key)
            if not message_id:
                logging.warning(f"⚠️ {message_key} not set in settings")
                continue
            
            try:
                message = await channel.fetch_message(int(message_id))
                
                # Verify message has components (views)
                if not message.components:
                    logging.warning(f"⚠️ Message {message_id} missing components, may need recreation")
                
                reconnected += 1
                
            except discord.NotFound:
                logging.error(f"❌ Persistent view message {message_id} not found, needs recreation")
                # Clear invalid message ID from settings
                await self.bot.db.set_bot_config(message_key, value=None, channel_id=None, message_id=None)
                self.bot.settings_cache[message_key] = None
            except Exception as e:
                logging.error(f"❌ Error verifying message {message_id}: {e}")
        
        return reconnected
    
    async def reregister_persistent_views(self):
        """Re-register all persistent views to ensure they're active."""
        try:
            # Re-register LiveQueueCog views
            live_queue_cog = self.bot.get_cog('LiveQueueCog')
            if live_queue_cog:
                from cogs.live_queue_cog import PublicQueueView
                self.bot.add_view(PublicQueueView(live_queue_cog))
                logging.info("✅ Re-registered LiveQueueCog views")
            
            # Re-register ReviewerCog views
            reviewer_cog = self.bot.get_cog('ReviewerCog')
            if reviewer_cog:
                from cogs.reviewer_cog import ReviewerMainQueueView, PendingSkipsView
                self.bot.add_view(ReviewerMainQueueView(reviewer_cog))
                self.bot.add_view(PendingSkipsView(reviewer_cog))
                logging.info("✅ Re-registered ReviewerCog views")
            
            # Re-register SubmissionCog views (if needed)
            submission_cog = self.bot.get_cog('SubmissionCog')
            if submission_cog and hasattr(submission_cog, 'submission_view'):
                self.bot.add_view(submission_cog.submission_view)
                logging.info("✅ Re-registered SubmissionCog views")
                
        except Exception as e:
            logging.error(f"Error re-registering persistent views: {e}", exc_info=True)
    
    @app_commands.command(name="selfheal", description="[ADMIN] Manually trigger self-healing for persistent view channels.")
    @app_commands.checks.has_permissions(administrator=True)
    async def selfheal_command(self, interaction: discord.Interaction):
        """Manual self-healing trigger for administrators."""
        await interaction.response.defer(ephemeral=True)
        
        if self.healing_in_progress:
            await interaction.followup.send("⚠️ Healing is already in progress. Please wait...", ephemeral=True)
            return
        
        self.healing_in_progress = True
        
        try:
            embed = discord.Embed(
                title="🏥 Self-Healing Started",
                description="Scanning and healing persistent view channels...",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            configs = self.get_persistent_channel_configs()
            
            total_cleaned = 0
            total_reconnected = 0
            results = []
            
            for config in configs:
                cleaned, reconnected = await self.heal_channel(config)
                total_cleaned += cleaned
                total_reconnected += reconnected
                
                status = "✅" if (cleaned > 0 or reconnected > 0) else "⏭️"
                results.append(f"{status} **{config['name']}**: {cleaned} cleaned, {reconnected} verified")
            
            # Re-register all persistent views to ensure they're active
            await self.reregister_persistent_views()
            
            result_embed = discord.Embed(
                title="✅ Self-Healing Complete",
                description=f"**Summary:**\n"
                           f"🧹 Total messages cleaned: **{total_cleaned}**\n"
                           f"🔗 Total views verified: **{total_reconnected}**\n"
                           f"♻️ Persistent views re-registered\n\n"
                           f"**Channel Details:**\n" + "\n".join(results),
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            result_embed.set_footer(text="Self-healing completed")
            
            await interaction.edit_original_response(embed=result_embed)
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Self-Healing Error",
                description=f"An error occurred during self-healing:\n```{str(e)}```",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=error_embed)
            logging.error(f"Self-heal command error: {e}", exc_info=True)
        finally:
            self.healing_in_progress = False

async def setup(bot):
    await bot.add_cog(SelfHealingCog(bot))
