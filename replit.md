# Discord Music Queue Bot

## Overview

A Discord bot that implements a TikTok-style music review queue system using Discord.py v2.x. The bot features interactive slash commands, modal forms and file uploads for submissions, and real-time queue management across four priority-based queue lines plus an archive. Users can submit music via links or upload actual MP3/audio files, while administrators can manage submissions across different priority queues with automatic embed updates and "Calls Played" archiving.

### Recent Verification (2025-10-09)
All core functionality has been verified and is working correctly:
- ✅ Queue pagination with auto-updating displays
- ✅ Submission channel cleanup (admin/bot only)
- ✅ TikTok handle linking with database autocomplete and validation
- ✅ Persistent submission storage with resubmission capability
- ✅ Points tracking per Discord account with periodic sync

See `fix_report.json` for comprehensive verification report.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Discord.py v2.x Framework**: Modern Discord bot implementation using slash commands and interactive UI components
- **Dual Submission Methods**: Uses `discord.ui.Modal` for link submissions and `discord.Attachment` for file uploads
- **File Upload Support**: Accepts MP3, WAV, M4A, and FLAC files up to 25MB with content-type validation
- **Real-time Embed Updates**: Pinned messages in designated channels automatically update when queue state changes
- **Cog-Based Organization**: Modular architecture with separate cogs for admin, queue, and submission functionality

### Backend Architecture
- **Async/Await Pattern**: Full asynchronous implementation for handling concurrent Discord operations
- **SQLite Database**: Persistent storage using `aiosqlite` for async database operations
- **Lock-Based Concurrency**: Uses `asyncio.Lock()` to prevent race conditions during queue updates
- **Enum-Based Queue Lines**: Type-safe queue line definitions with priority ordering (BackToBack → DoubleSkip → Skip → Free)

### Data Storage Solutions
- **SQLite Database**: Two main tables for submissions and channel settings
- **Submissions Table**: Stores user submissions with metadata (user_id, artist_name, song_name, link_or_file, queue_line, etc.)
- **Discord CDN Integration**: File uploads stored as Discord CDN URLs for persistent access
- **Channel Settings Table**: Maps queue lines to Discord channels and pinned message IDs
- **Auto-incrementing IDs**: Primary key system for unique submission identification
- **Archive System**: "Calls Played" line automatically tracks processed submissions

### Authentication and Authorization
- **Discord Permission System**: Admin commands protected by `manage_guild` permission check
- **Role-Based Access**: Administrative functions restricted to users with server management permissions
- **User Isolation**: Users can only see their own submissions via `/mysubmissions` command

### Queue Management System
- **Priority-Based Processing**: Four-tier priority system with weighted queue processing
- **Single Free Submission Limit**: Users restricted to one active submission in the Free queue line
- **Cross-Line Mobility**: Admin commands allow moving submissions between different queue lines
- **FIFO Within Priority**: First-in-first-out processing within each priority level

## External Dependencies

### Core Dependencies
- **discord.py (>=2.3.2)**: Modern Discord API wrapper with slash command support
- **aiosqlite (>=0.19.0)**: Async SQLite database interface
- **python-dotenv (>=1.0.0)**: Environment variable management for secure token storage

### Discord API Integration
- **Bot Token Authentication**: Requires Discord bot token stored in environment variables
- **Guild Integration**: Full guild member and message management capabilities
- **Channel Management**: Automatic pinned message creation and updates in designated channels

### Database Integration
- **SQLite File Storage**: Local file-based database (`music_queue.db`)
- **Async Database Operations**: Non-blocking database queries using aiosqlite
- **Automatic Schema Creation**: Database tables created on first run

### Environment Configuration
- **Replit Integration**: Designed for deployment on Replit platform
- **Environment Variables**: Bot token and configuration managed through environment variables
- **Logging System**: File and console logging for monitoring and debugging

### Slash Command Synchronization
If your slash commands (like `/setline`) are not updating correctly, you can force an immediate update by providing your server's ID in the environment variables.

1.  **Find your Server ID (Guild ID):**
    *   In Discord, open your User Settings.
    *   Go to the "Advanced" section.
    *   Enable "Developer Mode".
    *   Right-click on your server's icon in the server list and click "Copy Server ID".

2.  **Set the Environment Variable:**
    *   In your Replit project, go to the "Secrets" tab.
    *   Add a new secret with the key `GUILD_ID` and paste your copied server ID as the value.
    *   Restart the bot.

This will sync the commands directly to your server, which is much faster than the default global sync.