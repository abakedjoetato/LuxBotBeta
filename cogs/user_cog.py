"""
User Cog - Handles user-centric commands like linking accounts and managing profiles.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

class UserCog(commands.Cog):
    """Cog for user-facing commands like linking accounts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="link-tiktok", description="Link your Discord account to a TikTok handle.")
    @app_commands.describe(handle="Your TikTok handle (e.g., @username).")
    async def link_tiktok(self, interaction: discord.Interaction, handle: str):
        """Links a user's Discord account to a TikTok handle that has been seen on stream."""
        await interaction.response.defer(ephemeral=True)

        clean_handle = handle.strip().lstrip('@')

        if not clean_handle:
            await interaction.followup.send("❌ TikTok handle cannot be empty.", ephemeral=True)
            return

        try:
            success, message = await self.bot.db.link_tiktok_account(interaction.user.id, clean_handle)
            if success:
                embed = discord.Embed(title="✅ TikTok Account Linked", description=message, color=discord.Color.green())
            else:
                embed = discord.Embed(title="❌ Linking Failed", description=message, color=discord.Color.red())

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error during TikTok linking for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)

    @app_commands.command(name="unlink-tiktok", description="Unlink a TikTok handle from your Discord account.")
    @app_commands.describe(handle="The TikTok handle to unlink.")
    async def unlink_tiktok(self, interaction: discord.Interaction, handle: str):
        """Unlinks a TikTok handle from the user's Discord account."""
        await interaction.response.defer(ephemeral=True)

        clean_handle = handle.strip().lstrip('@')

        if not clean_handle:
            await interaction.followup.send("❌ TikTok handle cannot be empty.", ephemeral=True)
            return

        try:
            success, message = await self.bot.db.unlink_tiktok_account(interaction.user.id, clean_handle)
            if success:
                embed = discord.Embed(title="✅ TikTok Account Unlinked", description=message, color=discord.Color.green())
            else:
                embed = discord.Embed(title="❌ Unlinking Failed", description=message, color=discord.Color.red())

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error during TikTok unlinking for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)

    @app_commands.command(name="my-tiktok-handles", description="View your linked TikTok handles.")
    async def my_tiktok_handles(self, interaction: discord.Interaction):
        """Shows the user all of their currently linked TikTok handles."""
        await interaction.response.defer(ephemeral=True)
        try:
            handles = await self.bot.db.get_linked_tiktok_handles(interaction.user.id)
            if not handles:
                embed = discord.Embed(title="Linked TikTok Accounts", description="You have no TikTok handles linked to your Discord account.", color=discord.Color.blue())
            else:
                embed = discord.Embed(title="Linked TikTok Accounts", description="\n".join([f"• `{handle}`" for handle in handles]), color=discord.Color.green())

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Error fetching linked handles for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send("An unexpected error occurred while fetching your linked accounts.", ephemeral=True)

    @app_commands.command(name="resetpoints", description="[ADMIN] Reset a user's engagement points to zero.")
    @app_commands.describe(user="The Discord user whose points you want to reset.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_points(self, interaction: discord.Interaction, user: discord.Member):
        """Allows an admin to manually reset a user's engagement points."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.db.reset_user_points(user.id)
            embed = discord.Embed(
                title="✅ Points Reset",
                description=f"Successfully reset the engagement points for {user.mention} to zero.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Error resetting points for user {user.id} by admin {interaction.user.id}: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while resetting points for {user.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserCog(bot))