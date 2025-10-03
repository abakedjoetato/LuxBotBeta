# Discord Music Queue Bot

A TikTok-style music review queue system built with Discord.py v2.x featuring slash commands, interactive modals, and real-time queue management.

## Features

### User Features
- **Submit Music**: Use `/submit` to open an interactive form for music submissions
- **View Queue**: Use `/myqueue` to see all your active submissions across queue lines
- **Help**: Use `/help` to see available commands and queue information

### Queue System
- **Four Priority Lines**:
  - **BackToBack**: Highest priority queue
  - **DoubleSkip**: High priority queue
  - **Skip**: Medium priority queue  
  - **Free**: Standard submissions (1 per user limit)

### Admin Features
- **Queue Management**: Move submissions between lines with `/move`
- **Remove Submissions**: Remove submissions with `/remove`
- **Next Review**: Get next submission to review with `/next` (follows priority order)
- **Channel Setup**: Configure queue line channels with `/setline`

### Technical Features
- Real-time auto-updating pinned embeds in designated channels
- SQLite database for persistent storage
- Async/await for concurrency-safe operations
- Discord UI Modals and interactive components
- Comprehensive error handling and validation

## Setup on Replit

### 1. Environment Variables
Set the following environment variable in your Replit project:
- `DISCORD_BOT_TOKEN`: Your Discord bot token

To get a Discord bot token:
1. Go to https://discord.com/developers/applications
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Add the token to your Replit environment variables

### 2. Bot Permissions
Your Discord bot needs the following permissions:
- Send Messages
- Use Slash Commands
- Manage Messages (for pinning)
- Read Message History
- Embed Links

### 3. Running the Bot
1. Install dependencies: `pip install -r requirements.txt`
2. Run the bot: `python main.py`

The bot will automatically:
- Initialize the SQLite database
- Load all command cogs
- Sync slash commands with Discord
- Set presence activity

## Usage

### Initial Setup
1. Use `/setline` commands to configure channels for each queue line
2. Users can start submitting music with `/submit`
3. Admins can manage the queue with admin commands

### Queue Management
- Submissions are processed in priority order: BackToBack → DoubleSkip → Skip → Free
- Each queue line displays real-time updates in its designated channel
- Users can only have one submission in the Free line
- Admins can move submissions between any lines

## Project Structure

```
├── main.py                 # Bot entry point and initialization
├── database.py            # SQLite database operations
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── cogs/
    ├── submission_cog.py  # User submission commands
    ├── queue_cog.py      # Queue display and user commands
    └── admin_cog.py      # Administrative commands
```

## Dependencies

- `discord.py>=2.3.2`: Discord API wrapper with slash command support
- `aiosqlite>=0.19.0`: Async SQLite database operations
- `python-dotenv>=1.0.0`: Environment variable management

## Commands Reference

### User Commands
- `/submit` - Open submission form (Artist, Song, Link/File)
- `/myqueue` - View your submissions across all lines
- `/help` - Show help information

### Admin Commands
- `/setline [line] [#channel]` - Set channel for queue line
- `/move [submission_id] [target_line]` - Move submission between lines
- `/remove [submission_id]` - Remove submission from queue
- `/next` - Get next submission to review (priority order)

## Database Schema

The bot uses SQLite with the following tables:
- `submissions`: Store music submissions with metadata
- `channel_settings`: Map queue lines to Discord channels
- `bot_settings`: Store bot configuration options