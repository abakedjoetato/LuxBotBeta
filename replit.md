# Discord Music Queue Bot

## Overview

A Discord bot that implements a TikTok-style music review queue system using Discord.py v2.x. The bot features interactive slash commands, modal forms and file uploads for submissions, and real-time queue management across four priority-based queue lines plus an archive. Users can submit music via links or upload actual MP3/audio files, while administrators can manage submissions across different priority queues with automatic embed updates and "Calls Played" archiving.

### Import Status (2025-10-09)
✅ **Successfully migrated to Replit environment**
- Python 3.11 installed and configured
- All dependencies installed (discord.py, python-dotenv, aiosqlite, psycopg2-binary, asyncpg)
- Environment secrets configured (DISCORD_BOT_TOKEN, DATABASE_URL)
- Workflow configured and bot running successfully
- Database connected and initialized

### Recent Verification (2025-10-09)
All core functionality has been verified and is working correctly:
- ✅ Queue pagination with auto-updating displays
- ✅ Submission channel cleanup (admin/bot only)
- ✅ TikTok handle linking with database autocomplete and validation
- ✅ Persistent submission storage with resubmission capability
- ✅ Points tracking per Discord account with periodic sync

### Enhanced Features Implementation (2025-10-09)
Successfully implemented 8 major feature enhancements:

1. **TikTok Handle Autocomplete in Submissions** ✅
   - Added autocomplete to `/submit` and `/submitfile` commands
   - Database-driven suggestions from existing TikTok handles
   - Validation ensures only valid handles can be selected
   - Seamless integration with existing submission flow

2. **Ephemeral Submission Confirmations** ✅
   - All submission confirmation messages are now private (ephemeral)
   - Reduces channel clutter
   - Better user privacy for submissions

3. **Enhanced Reset Points System** ✅
   - `/resetpoints` command now supports multiple modes:
     - Target specific user + all their linked handles
     - Set `reset_all=True` to reset ALL TikTok handles in system
   - Flexible admin control over points management

4. **Per-Handle Points Tracking** ✅
   - Points now tracked at TikTok handle level in `tiktok_accounts` table
   - Handles accumulate points independently of Discord account linking
   - TikTok handles earn engagement points even without active Discord link
   - Database schema updated with `points` column in `tiktok_accounts`

5. **Automatic Free Line Points Reset** ✅
   - When songs play from FREE queue line, points automatically reset
   - Resets both submitter and all linked TikTok handles
   - Encourages continued engagement and fair rotation

6. **Enhanced Reviewer Display** ✅
   - Detailed points breakdown with emoji decorations:
     - 👍 Likes
     - 💬 Comments  
     - 🔁 Shares
     - 🎁 Gifts
   - Better visibility of engagement metrics per submission

7. **Persistent Interactive Views** ✅
   - All reviewer views use `timeout=None` for persistence
   - Views remain active indefinitely until manually dismissed
   - No expiration on interactive buttons

8. **Auto-Refreshing Queue Displays** ✅
   - Queue displays automatically update on queue state changes
   - Event-driven refresh via `queue_update` events
   - Real-time synchronization across all displays

### TikTok Connection Improvements (2025-10-09)
Implemented robust TikTok Live connection system with enterprise-grade reliability:

1. **Persistent Connection with Retry Logic** ✅
   - `/tiktok connect` now supports persistent mode (default: enabled)
   - Automatic retry when user is offline - perfect for pre-stream setup
   - Smart retry intervals: 10s for first 3 attempts, 30s thereafter
   - Handles all error scenarios: UserNotFoundError, UserOfflineError, general exceptions
   - Proper cancellation support for clean shutdown

2. **Connection Status Command** ✅
   - `/tiktok status` displays real-time connection state
   - Shows connection uptime, retry count, session ID
   - Three distinct states: Active (connected), In Progress (attempting), Disconnected
   - Clear visual indicators with color-coded embeds
   - Helpful footer text with next action suggestions

3. **Enhanced Disconnect Functionality** ✅
   - `/tiktok disconnect` handles both active connections and connection attempts
   - Can cancel in-progress connection attempts
   - Clear status messages for all scenarios
   - Proper cleanup of session data and state variables
   - Posts session summary when disconnecting from active stream

4. **Database Performance Optimizations** ✅
   - Added 7 strategic indices for frequently queried columns
   - Composite index for Free queue ordering (critical performance boost)
   - Optimized Free queue query to use total_score (eliminates expensive join)
   - Index coverage for: user_id, queue_line, session_id, played_time, submission_time
   - Partial index on Free queue for maximum efficiency

### Code Cleanup & Error Fixes (2025-10-09)
Successfully completed comprehensive codebase cleanup:
- ✅ Fixed all critical attribute errors (bot.database → bot.db) across all cogs
- ✅ Added missing _cleanup_connection method to TikTok cog
- ✅ Removed duplicate/legacy cog files (reviewer_queue_cog.py, queue_cog.py)
- ✅ Added debug_cog to loaded cogs list in main.py
- ✅ Cleaned up requirements.txt (removed duplicates)
- ✅ Deleted unnecessary files (=1.0.0, =2.3.2, changes.json, fix_report.json, Procfile, migrate_data.py)
- ✅ All LSP diagnostics resolved (0 errors)
- ✅ Bot starts successfully and all cogs load without errors

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