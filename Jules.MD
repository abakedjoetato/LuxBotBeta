AGENTS.md
🚀 Project Overview
This project is a sophisticated, Python-based Discord bot that acts as a powerful monitoring tool for TikTok Live streams. The bot's core purpose is to allow users to subscribe to TikTok creators. When a subscribed creator goes live, the bot will automatically post a rich, customizable notification in a designated Discord channel, potentially pinging a specific role.

This document serves as a comprehensive guide for an AI coding agent (Jules) to understand the project's architecture, advanced best practices, and development workflow, now centered around a PostgreSQL database.

⚙️ Core Technologies
Language: Python 3.10+

Discord Library: discord.py v2.0+

TikTok API: TikTokLive (Unofficial Python Wrapper)

Database: PostgreSQL

PostgreSQL Driver: asyncpg for high-performance, asynchronous database operations.

Environment Variables: python-dotenv for managing secrets.

🗂️ Project Structure
The project structure is updated to reflect an external database instead of a local file.

/
├── .venv/
├── .env
├── AGENTS.md
├── main.py
├── requirements.txt
└── cogs/
    ├── __init__.py
    └── tiktok_cog.py
main.py: The entry point. Handles environment loading, establishing the database connection pool, bot initialization, and loading cogs.

cogs/tiktok_cog.py: Contains all user-facing slash commands (/subscribe, /list, etc.) and the core TikTok monitoring logic.

.env: Stores secrets. It is critical that this file is correctly configured.

DISCORD_TOKEN

DB_HOST

DB_PORT

DB_USER

DB_PASSWORD

DB_NAME

💡 Advanced discord.py Best Practices
To build a robust and user-friendly bot, we will adhere to modern discord.py practices.

1. PostgreSQL for Robust Persistence
We will use asyncpg to interact with our PostgreSQL database. PostgreSQL offers superior scalability, true concurrency, and data integrity compared to file-based databases, making it ideal for a production-level bot.

Action: A connection pool is essential for managing database connections efficiently in an async environment. The bot will initialize an asyncpg connection pool on startup and pass it to the cogs for use in all database transactions.

2. Persistent Views
Standard UI components (like buttons) time out and stop working after a bot restarts. Persistent Views solve this. They are attached to a message and remain functional indefinitely.

Why it's important: We can have a "Live Status" message with a "Refresh" button that always works, or a subscription list with "Unsubscribe" buttons next to each name.

Implementation:

Subclass discord.ui.View.

Define a custom_id for each component.

In the View's __init__, call super().__init__(timeout=None).

The bot must register the view in its setup_hook to "re-discover" it after a restart.

Example Snippet (for context):

Python

class PersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Click Me", style=discord.ButtonStyle.green, custom_id="persistent:button_green")
    async def green_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("This button will always work!", ephemeral=True)

# In your bot's setup_hook in main.py:
class MyBot(commands.Bot):
    async def setup_hook(self):
        # The database pool should be created before this
        self.add_view(PersistentView())
3. Global Error Handling
To prevent the bot from crashing on unexpected errors and to provide clean feedback to users, we will implement a global error handler for application commands.

Action: Use the bot.tree.on_error decorator in main.py to catch all slash command errors, log them, and respond to the user with a helpful, ephemeral message.

⚠️ Deep Dive: Unofficial TikTok Live API
The TikTokLive library is powerful but requires careful implementation due to its unofficial nature and blocking behavior.

1. The Concurrency Challenge: discord.py vs. TikTokLive
Both discord.py and TikTokLive have a blocking .run() method to start their event loops. The only correct way to integrate them is to run each TikTokLiveClient as a background task within the discord.py event loop.

Implementation:

Create a function to initialize and start a TikTokLiveClient for a given TikTok user.

In the bot's on_ready event (or setup_hook), iterate through the subscriptions in the database.

For each subscription, launch its monitoring function using asyncio.create_task().

2. Managing Multiple Clients
The bot must monitor many TikTok users simultaneously. We will manage a dictionary of active clients.

Architecture: Maintain a dictionary like self.active_monitors = {} where keys are TikTok unique_ids and values are the asyncio.Task objects running the client. This allows us to start, stop, and check the status of each monitor.

3. Robust Event Handling & Stability
Since the API is unofficial, it can fail. The code must be defensive.

Error Handling: Wrap all client.run() calls in try...except blocks. If a client disconnects or throws an error, log it and implement a retry mechanism with an exponential backoff (e.g., wait 1 min, then 2 mins, then 5 mins before reconnecting).

Key Events to Handle: connect, disconnect, live_end.

Graceful Shutdown: When the bot is shutting down, ensure all active TikTokLiveClient tasks are cancelled properly.

✅ Tasks and Commands for Jules
When working on this project, your primary goal is to build a robust, persistent, and user-friendly bot using PostgreSQL.

Database Setup: Create a database.py utility file. This file will be responsible for creating and managing the asyncpg connection pool. It should also contain functions for initializing the necessary tables (e.g., a subscriptions table with columns for guild_id, channel_id, tiktok_username, etc.).

Command: /subscribe [tiktok_username] [channel] [role_to_ping]

Adds a new TikTok creator to monitor for a specific channel.

Must save this information to the PostgreSQL database using the connection pool.

Must start a new background monitoring task for this user if one isn't already active for them.

Command: /unsubscribe [tiktok_username]

Removes a subscription from the current channel.

Updates the PostgreSQL database.

If no other channels are subscribed to this TikToker, shut down and remove the corresponding monitoring task.

Implement Persistent Views: For status messages or subscription lists, use persistent views with buttons for actions like "Refresh Status" or "Unsubscribe."
