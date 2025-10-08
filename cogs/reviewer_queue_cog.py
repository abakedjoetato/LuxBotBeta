"""
Reviewer Queue Cog
Handles the display of a detailed, persistent queue for staff review.
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from typing import List, Dict, Optional

from database import Database, QueueLine

class ReviewerQueueCog(commands.Cog):
    """A cog for managing the detailed reviewer queue display."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Database = bot.db
        self.reviewer_queue_task.start()
        self.last_message_content = ""

    def cog_unload(self):
        self.reviewer_queue_task.cancel()

    @app_commands.command(name="setreviewerchannel", description="[ADMIN] Sets the channel for the detailed reviewer queue.")
    @commands.has_permissions(administrator=True)
    async def set_reviewer_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the channel for the reviewer queue message."""
        await self.db.set_bot_config('reviewer_queue_channel_id', channel_id=channel.id)
        await self.db.set_bot_config('reviewer_queue_message_id', message_id=None)
        self.bot.settings_cache['reviewer_queue_channel_id'] = channel.id
        self.bot.settings_cache['reviewer_queue_message_id'] = None
        embed = discord.Embed(title="✅ Reviewer Queue Channel Set", description=f"The detailed reviewer queue will now be displayed in {channel.mention}.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _generate_reviewer_embeds(self) -> List[discord.Embed]:
        """Generates a list of embeds for the detailed reviewer queue."""
        submissions = await self.db.get_all_active_queue_songs(detailed=True)

        if not submissions:
            return [discord.Embed(title="Reviewer Queue", description="The queue is currently empty.", color=discord.Color.blue())]

        embeds = []
        current_embed = discord.Embed(title="Live Reviewer Queue", color=discord.Color.dark_purple())
        current_description = ""

        for sub in submissions:
            # Format the entry with all the details
            entry = (
                f"**#{sub['public_id']} | {sub['artist_name']} - {sub['song_name']}**\n"
                f"> **Queue:** {sub['queue_line']} | **Score:** {sub.get('total_score', 0)}\n"
                f"> **Submitter:** {sub['username']} (`{sub['user_id']}`)\n"
            )
            if sub['link_or_file'].startswith("http"):
                entry += f"> **Link:** [Click Here]({sub['link_or_file']})\n"
            if sub.get('note'):
                entry += f"> **Note:** *{sub['note']}*\n"
            entry += "---\n"

            # Discord embed description limit is 4096 characters. We'll be safe.
            if len(current_description) + len(entry) > 4000:
                current_embed.description = current_description
                embeds.append(current_embed)
                current_embed = discord.Embed(title="Live Reviewer Queue (Cont.)", color=discord.Color.dark_purple())
                current_description = ""

            current_description += entry

        current_embed.description = current_description
        current_embed.set_footer(text="This is a detailed view for reviewers.")
        current_embed.timestamp = discord.utils.utcnow()
        embeds.append(current_embed)

        return embeds

    @tasks.loop(seconds=15)
    async def reviewer_queue_task(self):
        """The main background task to update the reviewer queue message."""
        channel_id = self.bot.settings_cache.get('reviewer_queue_channel_id')
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logging.warning(f"Reviewer queue channel with ID {channel_id} not found.")
            return

        try:
            new_embeds = await self._generate_reviewer_embeds()
            new_content = "".join([str(e.to_dict()) for e in new_embeds])

            if new_content == self.last_message_content:
                return

            message_id = self.bot.settings_cache.get('reviewer_queue_message_id')
            message: Optional[discord.Message] = None

            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    # Ensure the message is still pinned
                    if not message.pinned:
                        await message.pin(reason="Re-pinning reviewer queue message.")
                except discord.NotFound:
                    message = None # Message was deleted, create a new one

            if message:
                await message.edit(embeds=new_embeds)
            else:
                message = await channel.send(embeds=new_embeds)
                await message.pin()
                await self.db.set_bot_config('reviewer_queue_message_id', message_id=message.id)
                self.bot.settings_cache['reviewer_queue_message_id'] = message.id

            self.last_message_content = new_content

        except discord.errors.Forbidden:
            logging.error(f"Missing permissions to manage reviewer queue in channel {channel_id}.")
        except Exception as e:
            logging.error(f"An error occurred in the reviewer queue task: {e}", exc_info=True)

    @reviewer_queue_task.before_loop
    async def before_reviewer_queue_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewerQueueCog(bot))