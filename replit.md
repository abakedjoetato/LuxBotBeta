# Discord Music Queue Bot

## Overview
This Discord bot creates a TikTok-style music review queue, enabling users to submit music via links or file uploads. It features interactive slash commands, modal forms, and real-time queue management across four priority-based queues (BackToBack, DoubleSkip, Skip, Free) and an archive. Administrators can manage submissions, and the system includes TikTok handle linking, persistent submission storage with resubmission capabilities, and points tracking. The bot integrates with TikTok Live for real-time status monitoring, comprehensive post-live session analytics for all TikTok handles, and automatic disconnect notifications. The project aims to provide a dynamic platform for music discovery and review within Discord, leveraging TikTok's live interaction model and business vision to potentially create a new market for music engagement.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### UI/UX Decisions
- **Discord.py v2.x Framework**: Utilizes modern Discord bot features, including slash commands and interactive UI elements.
- **Dual Submission Methods**: Supports modal forms for link submissions and attachment uploads for music files (MP3, WAV, M4A, FLAC up to 25MB).
- **Real-time Embed Updates**: Pinned messages and queue displays auto-update dynamically.
- **Enhanced Reviewer Display**: Provides detailed points breakdown with emoji decorations.
- **Persistent Interactive Views**: All reviewer views and interactive elements maintain activity indefinitely.
- **Post-Live Metrics Channel**: A dedicated channel for structured session analytics after each TikTok LIVE session, displaying all participants.
- **Disconnect Notifications**: Automatic alerts for unexpected TikTok stream disconnections.
- **Hourly Points Backup**: Automated JSON backups of all user points and TikTok account points.

### Technical Implementations
- **Async/Await Pattern**: Implemented for non-blocking, concurrent operations.
- **Cog-Based Organization**: Modular architecture separates concerns into distinct cogs.
- **Lock-Based Concurrency**: `asyncio.Lock()` used to prevent race conditions.
- **Enum-Based Queue Lines**: Type-safe definitions for queue priorities.
- **TikTok Handle Autocomplete**: Suggestions for TikTok handles from existing database entries.
- **Ephemeral Submission Confirmations**: Private messages for submission confirmations.
- **Per-Handle Points Tracking**: Points tracked individually for each linked TikTok handle.
- **Automatic Free Line Points Reset**: Points reset when a song from the FREE queue plays.
- **Persistent TikTok Connection**: Intelligent retry logic for connecting to offline users.
- **Connection Status Command**: Provides real-time connection state, uptime, and session ID.
- **Enhanced Disconnect Functionality**: Manages active connections and in-progress attempts.
- **State Flag Management**: Uses `_user_initiated_disconnect` flag for accurate disconnect tracking.
- **Defer-First Pattern**: All Discord interactions defer immediately to prevent "Unknown interaction" errors.
- **Self-Healing Persistent View System**: Automates cleanup, reconnection, and verification of persistent view channels.

### Feature Specifications
- **Queue Management System**: Four-tier priority (BackToBack, DoubleSkip, Skip, Free) with FIFO processing.
- **Single Free Submission Limit**: Enforces one active submission per user in the Free queue.
- **User Isolation**: Users can only view their own submissions via `/mysubmissions`.
- **Comprehensive Post-Live Metrics**: Tracks watch time, gift counts, coin values, likes, comments, and shares for all TikTok handles in an ASCII table, sorted by engagement.
- **Enhanced Reset Points System**: Supports multiple modes for resetting points (specific users, all linked handles, global).
- **Hourly Points Backup System**: Automatically creates timestamped JSON backups of user_points and tiktok_accounts data.
- **Persistent Auto-Updating Embeds System**: All queue and reviewer embeds automatically update every 5 seconds, surviving bot restarts.

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