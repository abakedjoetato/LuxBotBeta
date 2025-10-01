"""
Custom checks for application commands
"""
import discord
from discord import app_commands

def submissions_open():
    """
    Check if music submissions are currently open.
    This is a decorator for app commands.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        # The bot instance should be available through the interaction's client attribute
        bot = interaction.client

        # Check if the database is available
        if not hasattr(bot, 'db'):
            # This should not happen in normal operation
            await interaction.response.send_message(
                "❌ A critical error occurred: Database not found.",
                ephemeral=True
            )
            return False

        # Check the submission status
        are_open = await bot.db.are_submissions_open()
        if not are_open:
            await interaction.response.send_message(
                "❌ Submissions are currently closed. Please try again later.",
                ephemeral=True
            )
            return False

        return True

    return app_commands.check(predicate)

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