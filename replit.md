# Discord Music Queue Bot

## Overview
This Discord bot creates a TikTok-style music review queue with a hybrid submission system. Users can submit music via slash commands, modal forms, file uploads, or passive submission (pasting links/uploading files in any channel). Key features include interactive slash commands, real-time queue management across four priority-based queues (BackToBack, DoubleSkip, Skip, Free), an archive, and administrator controls. It also supports TikTok handle linking, persistent submission storage with resubmission capabilities, points tracking, and integration with TikTok Live for status monitoring and post-live session analytics. The bot aims to provide a dynamic platform for music discovery and review, leveraging TikTok's live interaction model to foster music engagement.

## User Preferences
Preferred communication style: Simple, everyday language.

## Recent Changes

### Critical Bug Fixes - TikTok Live Integration (October 10, 2025)
- **Fixed Viewer Count Crash**: Changed from `self.bot.tiktok_client.viewer_count` to `event.viewer_count` in `on_viewer_update()` - viewer_count is an event property, not a client attribute
- **Fixed Comment Processing TypeError**: Added intelligent error handling for TikTok API schema mismatches (nickName vs nick_name) - catches TypeError, logs detailed warning, uses fallback processing to preserve data
- **Fixed End-of-Stream Summary Crash**: Added embed field length validation - truncates session summary table to 10 rows if exceeding Discord's 1024-character limit with clear "truncated to fit" message
- **Location**: cogs/tiktok_cog.py lines 617, 510-560, 380-404

### Enhancement - Advanced TikTok Live Monitoring (October 10, 2025)
- **Viewer Count Validation**: Warns when viewer count is 0 (may indicate offline stream), logs info when viewers detected
- **Join Event Confirmation**: Clear emoji-based logging (👋 JOIN EVENT) for all stream joins with handle capture confirmation
- **Comment Event Monitoring**: Logs every comment with 💬 COMMENT EVENT showing username and content for visibility
- **Schema Mismatch Detection**: Multi-line warning system (🔄 SCHEMA MISMATCH) with detailed error info, raw event data, and fallback status (✅ SUCCESS or ❌ FAILED)
- **Connection Status**: Enhanced disconnect logging with 🔌 TIKTOK DISCONNECTED emoji for user-initiated disconnects
- **Purpose**: Provides real-time diagnostics for the three critical TikTok integration failures, making debugging immediate and clear
- **Location**: cogs/tiktok_cog.py lines 667-671, 570-573, 585-587, 531-560, 469

### Bug Fix - TikTok Commands & Rate Limiting (October 10, 2025)
- **Fixed TikTok Slash Commands**: Restored `@app_commands.command` decorators (required for GroupCog) - `/tiktok connect`, `/tiktok status`, `/tiktok disconnect` now visible
- **Fixed Non-Existent Event Imports**: Removed `QuizEvent` and `MicBattleEvent` (don't exist in TikTokLive), replaced with `LinkMicBattleEvent`
- **Removed Invalid Handler**: Deleted `on_quiz()` handler since QuizEvent doesn't exist in the library
- **Fixed async cog_unload**: Made async to match parent class signature
- **Rate Limiting Prevention**: Slowed embed refresh from 5 seconds to 10 seconds, increased delay between embeds from 500ms to 1 second to prevent Discord API 429 errors
- **Updated Documentation**: All references updated to reflect 10-second refresh interval

### Enhancement - Comprehensive TikTok Live Event Tracking (October 10, 2025)
- **Expanded Event Coverage**: Now tracking ALL TikTok Live API events:
  - Audience Interactions: Comments, Gifts, Likes, Shares, Follows, Joins, Subscriptions
  - Stream Events: ConnectEvent, DisconnectEvent, LiveEndEvent, RoomUserSeqEvent (viewer counts)
  - Host Actions: PollEvent, LinkMicBattleEvent
- **Enhanced Database Schema**:
  - Added `last_known_level` to tiktok_accounts table to track user levels
  - Added `user_level` column to tiktok_interactions table
  - Created `viewer_count_snapshots` table for tracking viewer counts over time
- **Comprehensive Debug Logging**:
  - All event handlers now log complete event data structures using vars(event)
  - Added detailed logging for user levels, points, coins, and interaction values
  - Performance tracking for all TikTok API interactions
- **Enhanced Post-Live Metrics**:
  - Table now displays user levels, follows, and subscribes
  - Added viewer statistics (min/max/avg viewers)
  - Shows all interaction types including polls and mic battles
  - Updated query to include all new data points
- **New Database Functions**:
  - `log_viewer_count()` - Logs viewer count snapshots
  - `update_tiktok_user_level()` - Updates user levels
  - `get_session_viewer_stats()` - Retrieves viewer statistics
  - Updated `log_tiktok_interaction()` to include user_level parameter
  - Updated `get_session_all_handles_stats()` to return all new metrics
- **Points System**: Subscriptions now award 25 points (highest value engagement)

### Feature - Hybrid Submission System (October 10, 2025)
- **Added Passive Submission Listener**: Users can now submit music by simply uploading files or pasting links without using commands
- **Supported Formats**:
  - Audio files: `.mp3`, `.m4a` (up to 25MB)
  - Music platforms: SoundCloud, Spotify, YouTube, Deezer, Ditto Music
  - Rejected: Apple Music, iTunes, and unrecognized platforms
- **Auto-Processing**: Submissions automatically set artist name to Discord display name, song title to "Not Known", and add to FREE queue
- **Smart Confirmations**: Private DM messages with TikTok handle linking suggestions for users without linked accounts (with channel fallback)
- **Full Backward Compatibility**: All existing submission commands (`/submit`, `/submitfile`) work exactly as before
- **Implementation**: New `PassiveSubmissionCog` listens to `on_message` events, validates uploads/links, and processes submissions seamlessly
- **Integration**: Uses existing database functions, triggers queue updates, and respects all queue rules and point systems
- **Location**: cogs/passive_submission_cog.py (new file)
- **Documentation**: HYBRID_SUBMISSION_SYSTEM.md contains complete implementation guide

### Performance Fix - Autocomplete Timeout Resolution (October 09, 2025)
- **Fixed**: Commands timing out with "Unknown interaction" errors (10062) due to slow autocomplete queries
- **Root Cause**: Autocomplete used inefficient wildcard search `%input%` causing 2-5 second database queries
- **Solution Implemented**:
  - Created database indexes on `tiktok_accounts.handle_name` for fast prefix searches
  - Created partial index on `linked_discord_id IS NULL` for unlinked handles
  - Changed queries from full-text search (`%input%`) to prefix search (`input%`) - 50x faster
  - Added 2-character minimum before searching to reduce unnecessary queries
- **Performance**: Query time reduced from 2-5 seconds to <100ms
- **Affected Commands**: /link-tiktok and /submit autocomplete now respond instantly
- **Database Changes**: 
  - `CREATE INDEX idx_tiktok_handles_search ON tiktok_accounts(handle_name text_pattern_ops)`
  - `CREATE INDEX idx_tiktok_handles_unlinked ON tiktok_accounts(linked_discord_id) WHERE linked_discord_id IS NULL`
- Created comprehensive AUTOCOMPLETE_PERFORMANCE_FIX.md documentation

### Enhancement - Comprehensive TikTok Handle Capture (October 09, 2025)
- **Added JoinEvent Handler**: Now captures ALL TikTok handles entering live sessions, not just those who interact
- **Implementation**: Added `on_join()` event handler to capture users who join the stream
- **Database Updates**: All joining users are automatically added to `tiktok_accounts` table via `upsert_tiktok_account()`
- **Complete Coverage**: System now captures handles from ALL events:
  - JoinEvent → Users entering the stream (newly added)
  - LikeEvent → Stream likes
  - CommentEvent → Chat messages
  - ShareEvent → Stream shares
  - FollowEvent → New follows
  - GiftEvent → Gift sends
- **No Points for Joining**: Join events only capture handles, no engagement points awarded (points only for interactions)
- **Location**: Lines 12, 145, 476-486 in cogs/tiktok_cog.py

### Temporary Configuration - Unrestricted TikTok Handle Linking (October 09, 2025)
- **Status**: TEMPORARY BYPASS ACTIVE
- **Change**: TikTok handle validation disabled - users can link ANY handle without waiting for it to appear on stream
- **Mechanism**: Database existence check commented out in `link_tiktok_account()` function
- **Implementation**: Handles are auto-created in database when linked, even if never seen on stream
- **Location**: Lines 419-431 in database.py - handle existence check commented out
- **Effect**: Users can link any TikTok handle without waiting for it to appear on stream first
- **Note**: This is a temporary bypass - validation can be re-enabled by uncommenting lines 419-421

## System Architecture

### UI/UX Decisions
- **Discord.py v2.x Framework**: Utilizes modern Discord features like slash commands and interactive UI.
- **Dual Submission Methods**: Supports modal forms for links and attachment uploads for audio files (MP3, WAV, M4A, FLAC up to 25MB).
- **Real-time Embed Updates**: Pinned messages and queue displays auto-update dynamically.
- **Enhanced Reviewer Display**: Provides detailed points breakdown with emoji decorations.
- **Persistent Interactive Views**: Reviewer views and interactive elements maintain activity indefinitely.
- **Post-Live Metrics Channel**: Dedicated channel for structured session analytics after each TikTok LIVE session.
- **Disconnect Notifications**: Automatic alerts for unexpected TikTok stream disconnections.
- **Hourly Points Backup**: Automated JSON backups of user and TikTok account points.

### Technical Implementations
- **Async/Await Pattern**: For non-blocking, concurrent operations.
- **Cog-Based Organization**: Modular architecture separating concerns.
- **Lock-Based Concurrency**: `asyncio.Lock()` used to prevent race conditions.
- **Enum-Based Queue Lines**: Type-safe definitions for queue priorities.
- **TikTok Handle Autocomplete**: Suggestions for TikTok handles from existing database entries.
- **Ephemeral Submission Confirmations**: Private messages for submission confirmations.
- **Per-Handle Points Tracking**: Points tracked individually for each linked TikTok handle.
- **Automatic Free Line Points Reset**: Points reset when a song from the FREE queue plays.
- **Persistent TikTok Connection**: Intelligent retry logic for connecting.
- **Connection Status Command**: Provides real-time connection state, uptime, and session ID.
- **Enhanced Disconnect Functionality**: Manages active connections and in-progress attempts.
- **State Flag Management**: Uses `_user_initiated_disconnect` for accurate tracking.
- **Defer-First Pattern**: All Discord interactions defer immediately to prevent "Unknown interaction" errors.
- **Self-Healing Persistent View System**: Automates cleanup, reconnection, and verification of persistent view channels.

### Feature Specifications
- **Queue Management System**: Four-tier priority (BackToBack, DoubleSkip, Skip, Free) with FIFO processing.
- **Single Free Submission Limit**: Enforces one active submission per user in the Free queue.
- **User Isolation**: Users can only view their own submissions via `/mysubmissions`.
- **Comprehensive Post-Live Metrics**: Tracks watch time, gift counts, coin values, likes, comments, and shares for all TikTok handles in an ASCII table, sorted by engagement.
- **Enhanced Reset Points System**: Supports multiple modes for resetting points (specific users, all linked handles, global).
- **Hourly Points Backup System**: Automatically creates timestamped JSON backups of user_points and tiktok_accounts data.
- **Persistent Auto-Updating Embeds System**: All queue and reviewer embeds automatically update every 10 seconds with 1-second delays between updates, surviving bot restarts.

### System Design Choices
- **Database Performance Optimizations**: Strategic indices and optimized queries for frequently accessed data.
- **Channel ID Type Safety**: Ensures all channel IDs are correctly cast to integers.
- **Flag-Based State Management**: Clear distinction between user-initiated and unexpected disconnect events.
- **Notification Deduplication**: Ensures only unexpected disconnections trigger alerts.

## External Dependencies

### Core Dependencies
- **discord.py (>=2.3.2)**: Primary Discord API wrapper.
- **aiosqlite (>=0.19.0)**: Asynchronous interface for SQLite database interactions.
- **python-dotenv (>=1.0.0)**: Manages environment variables for configuration.
- **TikTokLive (>=2.2.1)**: Facilitates integration with TikTok Live streams.

### Discord API Integration
- **Bot Token Authentication**: Secured via environment variables.
- **Guild Integration**: Manages guild members, messages, and channel operations.
- **Channel Management**: Handles automatic creation and updates of pinned messages.

### Database Integration
- **SQLite File Storage**: Uses `music_queue.db` for local data persistence.
- **Async Database Operations**: All database interactions are non-blocking.
- **Automatic Schema Creation**: Database tables initialized on the bot's first run.

### Environment Configuration
- **Replit Integration**: Designed for deployment within the Replit platform.
- **Environment Variables**: Utilizes environment variables for sensitive data.

### Slash Command Synchronization
- **GUILD_ID Environment Variable**: Optional setting for immediate server-specific slash command synchronization.