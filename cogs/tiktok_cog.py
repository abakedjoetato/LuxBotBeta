import discord
import logging
from discord.ext import commands
from discord import app_commands

class TikTokCog(commands.Cog):
    """A minimal cog for debugging the TikTok command loading issue."""

    def __init__(self, bot):
        self.bot = bot
        logging.info("--- MINIMAL TikTokCog IS BEING INITIALIZED ---")

    # Define the command group
    tiktok = app_commands.Group(name="tiktok", description="Commands for managing TikTok Live integration.")

    @tiktok.command(name="status", description="Check the status of the TikTok LIVE connection.")
    async def status(self, interaction: discord.Interaction):
        """A simple, static command to test if the cog and command group are loading."""
        await interaction.response.send_message("🔴 Status: Minimal cog is loaded, but not connected.", ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(TikTokCog(bot))