# Discord Music Queue Bot

## Overview
This Discord bot establishes a TikTok-style music review queue, allowing users to submit music via links or file uploads. It features interactive slash commands, modal forms, and real-time queue management across four priority-based queues (BackToBack, DoubleSkip, Skip, Free) and an archive. Administrators can manage submissions, and the system includes TikTok handle linking, persistent submission storage with resubmission capabilities, and points tracking with hourly JSON backups. The bot also integrates a robust TikTok Live connection system with persistent retries, real-time status monitoring, comprehensive post-live session analytics covering ALL TikTok handles (linked and unlinked), and automatic disconnect notifications. The project aims to provide a dynamic and engaging platform for music discovery and review within Discord, leveraging TikTok's live interaction model.

## User Preferences
Preferred communication style: Simple, everyday language.

## Recent Changes (October 09, 2025)

### Bug Fixes Round 1
- **Issue #1 Fixed**: Enhanced /next command with diagnostic messaging when only pending skips exist in queue
- **Issue #2 Verified**: Queue pagination and auto-updating functionality confirmed working (Previous/Next buttons, auto-refresh)
- **Issue #3 Verified**: Submission channel cleanup confirmed working (admin/bot messages only, auto-deletes user messages)
- **Issue #4 Verified**: TikTok handle linking with autocomplete and duplicate prevention confirmed working
- **Issue #5 Verified**: Submission storage and resubmission via /my-submissions confirmed working
- **Issue #6 Implemented**: Hourly points backup system creates timestamped JSON files (points_backup_YYYYMMDD_HH.json)
- **Issue #7 Implemented**: Post-live metrics now include ALL TikTok handles (linked and unlinked), sorted by engagement
  - Added database.get_session_all_handles_stats() function
  - Updated _post_live_summary() to display comprehensive participant data
  - Metrics show linked Discord users, unlinked participants, and engagement sorting (coins > interactions)
- Generated comprehensive bug_fix_report.json with all findings, changes, and testing instructions

### Bug Fixes Round 2 - Persistent Views Fix
- **Queue Order Verification**: Confirmed /next command uses correct priority (25+, 20, 15, 10, 5, then engagement-sorted Free) - no changes needed
- **Persistent Views Fixed**: Resolved issue where persistent views stopped working after bot restart or /selfheal
  - Added `reregister_persistent_views()` method to SelfHealingCog
  - Persistent views now automatically re-register during bot startup (auto-heal)
  - Persistent views now automatically re-register when admin runs /selfheal command
  - All interactive buttons (Previous/Next/Refresh) remain functional indefinitely
- Created change_report_persistent_views_fix.md with detailed analysis and implementation notes

### Major Feature - Persistent Auto-Updating Embeds System
- **Implemented 5-Second Auto-Refresh**: All queue and reviewer embeds now automatically update every 5 seconds
- **Database Infrastructure**:
  - New `persistent_embeds` table tracks all auto-updating embeds
  - Stores message IDs, channel IDs, current page, last update time, and active status
  - Added 6 new database methods for embed management
- **New Cog: EmbedRefreshCog**:
  - Background task runs continuously with 5-second refresh interval
  - Rate limit protection: 500ms delay between individual embed updates
  - Automatic error recovery and cleanup for deleted messages
  - Status logging every minute showing active embed count and statistics
  - Admin command `/refresh-stats` for real-time monitoring
- **Enhanced LiveQueueCog & ReviewerCog**:
  - Embeds automatically register for auto-refresh during setup
  - Page state persists across bot restarts via database
  - Pagination buttons work indefinitely with auto-refresh
  - Setup commands now confirm "Auto-refresh enabled"
- **Safety Features**:
  - Staggered updates prevent Discord rate limits (max 50 edits/10s)
  - Graceful failure handling with retry on next cycle
  - Automatic deactivation of deleted embeds
  - Delta checking infrastructure ready for content-based optimization
- **Production Ready**: All embeds survive bot restarts and update continuously without manual intervention
- Created comprehensive PERSISTENT_EMBEDS_IMPLEMENTATION.md documentation

### Bug Fix - TikTok Gift AttributeError Resolution
- **Fixed:** AttributeError crash when processing TikTok gifts with missing 'streakable' attribute
- **Root Cause:** TikTokLive library Gift objects have varying attributes across versions and gift types
- **Solution Implemented**:
  - Added safe attribute checking using `hasattr()` and `getattr()` for all gift properties
  - Wrapped streakable/streaking logic in try/except to prevent asyncio callback crashes
  - Protected gift.diamond_count and gift.name access with defensive defaults (0, 'Unknown Gift')
  - Extended error handling to entire tiered skip reward logic
- **Safety Features**:
  - Graceful degradation with sensible defaults when attributes missing
  - Comprehensive error logging for debugging without verbose spam
  - No impact on gift processing, points calculation, or tiered rewards
  - Works reliably across all TikTokLive library versions
- **Testing:** Bot restart verified - no AttributeError or asyncio callback crashes detected
- Created comprehensive TIKTOK_GIFT_FIX.md documentation

### Gift Tier System Update
- **Completed All 5 Tier Thresholds**:
  - 1000-1999 coins → 5 Skip
  - 2000-3999 coins → 10 Skip
  - 4000-4999 coins → 15 Skip (newly added)
  - 5000-5999 coins → 20 Skip (newly added)
  - 6000+ coins → 25+ Skip (updated from 5000+)
- **Fixed Rewardable Submission Logic**:
  - Now correctly selects from Free line AND Pending Skips
  - Properly excludes submissions already in skip lines (5, 10, 15, 20, 25+)
  - Also excludes Songs Played and Removed submissions
- **Points Calculation**: Under 1000 coins awards 2 points per coin (unchanged)
- **Architect Review**: Passed - all tier thresholds and boundary values handled correctly
- Created comprehensive GIFT_TIER_UPDATE.md documentation

## System Architecture

### UI/UX Decisions
- **Discord.py v2.x Framework**: Utilizes modern Discord bot features, including slash commands and interactive UI elements.
- **Dual Submission Methods**: Supports both modal forms for link submissions and attachment uploads for music files (MP3, WAV, M4A, FLAC up to 25MB).
- **Real-time Embed Updates**: Pinned messages and queue displays auto-update dynamically based on queue changes.
- **Enhanced Reviewer Display**: Provides detailed points breakdown with emoji decorations for clarity.
- **Persistent Interactive Views**: All reviewer views and interactive elements maintain activity indefinitely (`timeout=None`).
- **Post-Live Metrics Channel**: A dedicated channel for structured session analytics after each TikTok LIVE session, displaying ALL participants (linked and unlinked).
- **Disconnect Notifications**: Automatic alerts in a debug channel for unexpected TikTok stream disconnections.
- **Hourly Points Backup**: Automated JSON backups of all user points and TikTok account points for recovery purposes.

### Technical Implementations
- **Async/Await Pattern**: Implemented throughout for non-blocking, concurrent operations.
- **Cog-Based Organization**: Modular architecture separates concerns into distinct cogs for maintainability.
- **Lock-Based Concurrency**: `asyncio.Lock()` is used to prevent race conditions during critical operations.
- **Enum-Based Queue Lines**: Type-safe definitions for various queue priorities.
- **TikTok Handle Autocomplete**: Suggestions for TikTok handles are driven by existing database entries.
- **Ephemeral Submission Confirmations**: Private messages for submission confirmations to reduce channel clutter.
- **Per-Handle Points Tracking**: Points are tracked individually for each linked TikTok handle.
- **Automatic Free Line Points Reset**: Points are reset for submitters and linked handles when a song from the FREE queue plays.
- **Persistent TikTok Connection**: Features intelligent retry logic for connecting to offline users.
- **Connection Status Command**: Provides real-time connection state, uptime, and session ID.
- **Enhanced Disconnect Functionality**: Manages both active connections and in-progress connection attempts, including proper cleanup.
- **State Flag Management**: Uses `_user_initiated_disconnect` flag for accurate tracking of disconnect types.
- **Defer-First Pattern**: All Discord interactions, especially those with async operations, defer immediately to prevent "Unknown interaction" errors.
- **Self-Healing Persistent View System**: Automates cleanup, reconnection, and verification of persistent view channels on startup and via admin commands.

### Feature Specifications
- **Queue Management System**: Four-tier priority (BackToBack, DoubleSkip, Skip, Free) with FIFO processing within tiers.
- **Single Free Submission Limit**: Enforces one active submission per user in the Free queue.
- **User Isolation**: Users can only view their own submissions via `/mysubmissions`.
- **Comprehensive Post-Live Metrics**: Tracks watch time, gift counts, coin values, likes, comments, and shares for ALL TikTok handles (linked and unlinked) in an ASCII table format, sorted by engagement points.
- **Enhanced Reset Points System**: Supports multiple modes for resetting points, including targeting specific users and all linked handles, or a global reset.
- **Hourly Points Backup System**: Automatically creates timestamped JSON backups of user_points and tiktok_accounts data every hour for disaster recovery.

### System Design Choices
- **Database Performance Optimizations**: Implemented strategic indices and optimized queries for frequently accessed data, particularly for the Free queue.
- **Channel ID Type Safety**: Ensures all channel IDs are correctly cast to integers before lookup.
- **Flag-Based State Management**: Provides clear distinction between user-initiated and unexpected disconnect events.
- **Notification Deduplication**: Ensures only unexpected disconnections trigger alerts in the debug channel.

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
- **Automatic Schema Creation**: Database tables are initialized on the bot's first run.

### Environment Configuration
- **Replit Integration**: Designed for deployment within the Replit platform.
- **Environment Variables**: Utilizes environment variables for sensitive data like bot tokens and configuration.

### Slash Command Synchronization
- **GUILD_ID Environment Variable**: Optional setting for immediate server-specific slash command synchronization.