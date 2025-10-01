"""
Custom checks for application commands
"""
import discord
from discord import app_commands

async def check_submissions_open(interaction: discord.Interaction) -> bool:
    """
    Reusable check to see if submissions are open.
    Sends a message to the user if they are closed.
    Returns True if open, False otherwise.
    """
    bot = interaction.client

    if not hasattr(bot, 'db'):
        await interaction.response.send_message(
            "❌ A critical error occurred: Database not found.",
            ephemeral=True
        )
        return False

    are_open = await bot.db.are_submissions_open()
    if not are_open:
        await interaction.response.send_message(
            "❌ Submissions are currently closed. Please try again later.",
            ephemeral=True
        )
        return False
    return True


def submissions_open():
    """
    Decorator check to see if music submissions are currently open.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        return await check_submissions_open(interaction)

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