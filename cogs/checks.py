"""
Custom checks for application commands
"""
import discord
from discord import app_commands

def is_admin():
    """
    Check if the user has admin permissions (manage_guild).
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not (hasattr(interaction.user, 'guild_permissions') and
                interaction.user.guild_permissions and
                interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)