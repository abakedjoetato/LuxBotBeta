"""
Debug Cog - Provides commands for bot debugging and administration.
"""
import discord
from discord.ext import commands
from discord import app_commands
from .checks import is_admin

class DebugCog(commands.Cog):
    """A cog for bot debugging and administration."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setdebugchannel", description="[ADMIN] Sets the channel for bot debug logs.")
    @app_commands.describe(channel="The channel to send debug logs to.")
    @is_admin()
    async def set_debug_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the debug channel."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.db.set_bot_config('debug_channel_id', channel_id=channel.id)
            self.bot.settings_cache['debug_channel_id'] = channel.id
            await interaction.followup.send(f"✅ Debug channel has been set to {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="cleandebugchannel", description="[ADMIN] Clears all messages from the debug channel.")
    @is_admin()
    async def clear_debug_channel(self, interaction: discord.Interaction):
        """Clears the debug channel."""
        await interaction.response.defer(ephemeral=True)
        debug_channel_id = self.bot.settings_cache.get('debug_channel_id')
        if not debug_channel_id:
            await interaction.followup.send("❌ Debug channel is not set. Use `/setdebugchannel` first.", ephemeral=True)
            return

        channel = self.bot.get_channel(debug_channel_id)
        if not channel:
            await interaction.followup.send("❌ Debug channel not found. It might have been deleted.", ephemeral=True)
            return

        try:
            # Purge messages
            deleted = await channel.purge()
            await interaction.followup.send(f"✅ Cleared {len(deleted)} messages from {channel.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(DebugCog(bot))