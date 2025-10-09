Of course! Here is the text reformatted using Markdown for better readability.

Discord Music Queue Bot
A sophisticated, TikTok-integrated music review queue system for Discord, built with Discord.py v2.x. This bot features slash commands, persistent interactive views, real-time queue management, and engagement-based rewards.

Features
User Features
Submit Music: Use /submit for links or /submitfile for audio files.

Manage Submissions: Use /my-submissions to view your submission history, remove active songs, or permanently delete past entries.

Link TikTok Account: Use /link-tiktok to link your Discord account to your TikTok handle, with autocomplete for available handles.

View Linked Handles: Use /my-tiktok-handles to see all your linked TikTok accounts.

Help: Use /help to see a list of available user-facing commands.

Queue & Engagement System
Dynamic Skip Tiers: Submissions can be promoted to various skip tiers (5 Skip, 10 Skip, etc.) based on TikTok gift values during a live stream.

Engagement-Based Free Line: The "Free" queue is sorted by user engagement points. Users who interact more on the linked TikTok live stream (likes, comments, shares, gifts) will have their songs prioritized.

Persistent, Auto-Updating Views: The bot uses modern, persistent discord.ui.Views for all queue displays. These views update in real-time whenever the queue changes, without needing to be re-created.

Admin Features
Advanced Queue Management: Move submissions between any line with /move and remove them with /remove.

Next-Up Workflow: Use /next to pull the next song based on the priority order (Skips > Free Line by points).

TikTok Live Integration: Connect the bot to a TikTok live stream with /tiktok connect and disconnect with /tiktok disconnect.

Persistent View Setup:

/setup-live-queue: Creates the public-facing, paginated queue display.

/setup-reviewer-channel: Creates a dedicated channel for admins with two views: one for the main active queue and one for pending skips.

Channel & Bot Configuration: Use various /set... commands to configure channels for submissions, bookmarks, and now-playing announcements.

Technical Features
Unofficial TikTok API: Leverages the TikTokLive library to connect to TikTok's Webcast service and listen for live events.

PostgreSQL Database: Uses a robust PostgreSQL database for all persistent data storage, managed via asyncpg.

Event-Driven Architecture: Core actions (like queue changes) dispatch a queue_update event, which all persistent views listen for to refresh their state instantly.

Comprehensive Admin Controls: Granular control over bot settings, channels, and queues.

Setup on Replit
1. Environment Variables
   Set the following environment variables in your Replit project's "Secrets" tab:

DISCORD_BOT_TOKEN: Your Discord bot token.

DATABASE_URL: Your PostgreSQL connection string (e.g., postgres://user:password@host:port/database).

GUILD_ID (Optional): The ID of your Discord server for faster slash command syncing during development.

2. Bot Permissions
   Your Discord bot needs the following permissions in your server:

Send Messages

Manage Messages

Read Message History

Embed Links

Attach Files

Use Application Commands

3. Running the Bot
   The .replit file is configured to run python main.py automatically. Simply press the "Run" button. The bot will:

Install dependencies from requirements.txt.

Connect to the PostgreSQL database.

Load all command cogs.

Register and sync slash commands.

Usage
Initial Setup
Use /setup-live-queue in your public queue channel.

Use /setup-reviewer-channel in your private admin/reviewer channel.

Use /set-submission-channel to designate a channel for submissions, which will be auto-moderated.

Instruct users to link their TikTok accounts with /link-tiktok to participate in the engagement point system.

Queue Management
Submissions are processed in priority order: Highest Skip Tier → Lowest Skip Tier → Free Line (by engagement points).

All queue views update automatically when a song is added, played, moved, or removed.

Project Structure
├── main.py                 # Bot entry point, setup, and event handling
├── database.py             # PostgreSQL database operations and schema
├── requirements.txt        # Python dependencies
├── README.md               # This file
└── cogs/
├── submission_cog.py   # User submission commands and modals
├── live_queue_cog.py   # Manages the public-facing persistent queue view
├── reviewer_cog.py     # Manages the two persistent views for reviewers
├── admin_cog.py        # Administrative commands for management
├── user_cog.py         # User account commands (linking, etc.)
└── tiktok_cog.py       # Handles TikTok API connection and event processing
Dependencies
discord.py>=2.3.2: Discord API wrapper.

asyncpg>=0.27.0: Asynchronous PostgreSQL database driver.

TikTokLive>=2.2.1: Unofficial library for the TikTok LIVE API.

python-dotenv>=1.0.0: Environment variable management.

psycopg2-binary: Required for PostgreSQL connection.

Commands Reference
A full list of commands can be discovered through Discord's slash command interface. Key commands are listed in the "Features" section above.

Database Schema
The bot uses a PostgreSQL database with the following primary tables:

submissions: Stores all historical and active song submissions with their metadata, including status, score, and associated TikTok handle.

tiktok_accounts: Stores all TikTok handles seen by the bot, along with their linked Discord ID.

tiktok_interactions: Logs all engagement events (likes, comments, gifts, etc.) from a live session for calculating points.

live_sessions: Records the start and end times of each TikTok LIVE stream the bot connects to.

user_points: Stores the current engagement point total for each Discord user.

bot_config: A key-value store for all bot settings, such as channel and message IDs for persistent views.
