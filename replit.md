# Discord Music Queue Bot

## Overview
This Discord bot implements a TikTok-style music review queue system, enabling users to submit music via links or file uploads. It features interactive slash commands, modal forms, and real-time queue management across four priority-based queue lines (BackToBack, DoubleSkip, Skip, Free) plus an archive. Administrators can manage submissions, and the system includes TikTok handle linking, persistent submission storage with resubmission capabilities, and points tracking. The bot also boasts a robust TikTok Live connection system with persistent retries, real-time status monitoring, comprehensive post-live session analytics, and automatic disconnect notifications.

## User Preferences
Preferred communication style: Simple, everyday language.

## Recent Updates

### Discord Interaction Timeout Fixes (2025-10-09) ✅
**Problem Solved**: Users reported "Unknown interaction" errors (404 error code 10062) when using `/tiktok connect`, `/tiktok status`, `/tiktok disconnect`, and other commands. Analysis revealed that Discord interactions expire after 3 seconds if not acknowledged.

**Root Cause**:
- Commands with database queries or async operations took longer than 3 seconds to respond
- Discord expects acknowledgment within 3 seconds or interaction becomes invalid
- Without immediate defer, long-running commands fail with "Unknown interaction" error

**Solution Implemented - Defer-First Pattern**:

1. **All TikTok Commands Fixed**
   - `/tiktok connect`: Added `await interaction.response.defer()` before database queries
   - `/tiktok status`: Added immediate defer before checking connection state
   - `/tiktok disconnect`: Added immediate defer before cleanup operations
   - All commands now use: defer → process → followup (or edit_original_response)

2. **Admin Commands Fixed**
   - `/move`: Defers before database operations
   - `/remove`: Defers before queue manipulation
   - `/next`: Defers before playing next song
   - `/clearfree`: Defers before clearing Free queue
   - `/setbookmarkchannel`, `/setnowplayingchannel`: Defer before settings update
   - `/setup-post-live-metrics`: Defers before channel configuration

3. **Persistent View Button Interactions Fixed**
   - **SkipQuestionView** (submission_cog.py): Both `yes_button` and `no_button` callbacks now defer before processing
   - **Reviewer Queue Views** (reviewer_cog.py): `update_main_queue_display` and `update_pending_skips_display` defer when interaction is provided
   - **Live Queue View** (live_queue_cog.py): `update_display` defers when interaction is provided before database queries
   - Critical for persistent views (timeout=None) which can have stale interactions
   - All buttons that trigger database queries now defer immediately before processing

**Design Pattern**:
```python
# ✅ CORRECT - Defer first, process later
await interaction.response.defer(ephemeral=True)
# ... database queries, async operations ...
await interaction.followup.send("Done!")

# ❌ INCORRECT - Will timeout if processing takes >3s
# ... database queries, async operations ...
await interaction.response.send_message("Done!")
```

**Testing Results**:
- Bot restarted with zero interaction timeout errors
- All commands now respond within Discord's 3-second window
- Clean logs confirm no "Unknown interaction" errors after fixes

### TikTok Disconnect Notifications (2025-10-09) ✅
**Problem Solved**: Users reported that TikTok connections claimed success but then `/tiktok status` showed "not connected". Analysis revealed that streams were disconnecting silently without any user notification.

**Solution Implemented**:
1. **User-Initiated vs Unexpected Disconnect Tracking**
   - Added `_user_initiated_disconnect` flag to distinguish manual disconnects from stream endings
   - User-initiated disconnects (via `/tiktok disconnect`) don't trigger notifications
   - Unexpected disconnects (stream ends, connection lost) trigger debug channel alerts

2. **Debug Channel Notifications**
   - **Connection Success** (Green Embed):
     - Posted when connection is established
     - Shows: Username, Room ID, Session ID
     - Footer: "Monitoring interactions and engagement"
   
   - **Unexpected Disconnect** (Orange Embed):
     - Posted when stream ends unexpectedly
     - Shows: Username, Connection Duration, Session ID
     - Footer: "Post-live metrics will be posted to the configured metrics channel"

3. **Critical Bug Fix**
   - Fixed channel ID type casting issue: `get_channel(int(debug_channel_id))`
   - Channel IDs are stored as strings in settings_cache but must be cast to int for lookup
   - Without this fix, all notifications would silently fail

**Testing Guide**:

*Prerequisites*:
- Set up debug channel: `/setdebugchannel #debug-channel`
- Ensure bot has message send permissions in debug channel

*Test Scenario 1 - Successful Connection*:
1. Run `/tiktok connect @username` (username must be LIVE)
2. ✅ Connection success message appears
3. ✅ Green embed posted to debug channel
4. Run `/tiktok status` → Shows active connection

*Test Scenario 2 - User-Initiated Disconnect*:
1. While connected, run `/tiktok disconnect`
2. ✅ Confirmation message appears
3. ✅ NO debug channel notification (expected)
4. ✅ Post-live metrics posted to metrics channel

*Test Scenario 3 - Unexpected Stream End*:
1. Connect to a live stream
2. Wait for streamer to end their stream
3. ✅ Orange disconnect embed posted to debug channel
4. ✅ Shows username, duration, session ID
5. Run `/tiktok status` → Shows "Not Connected"

*Test Scenario 4 - Connection Retry (Offline User)*:
1. Run `/tiktok connect @username persistent:True` (user offline)
2. ✅ Shows "Retrying Connection..." status
3. Run `/tiktok status` → Shows "Connection In Progress"

*Test Scenario 5 - Connection Attempt Cancellation*:
1. Start connection to offline user
2. Run `/tiktok disconnect` while retrying
3. ✅ "Connection attempt cancelled" message
4. ✅ NO debug channel notification (user-initiated)

### Post-Live Metrics Channel (2025-10-09) ✅
Implemented comprehensive post-live session analytics with dedicated metrics channel:

1. **Dedicated Metrics Channel Setup**
   - `/setup-post-live-metrics` command to configure metrics channel
   - Separate from debug channel for clean analytics
   - Automatic posting after each TikTok LIVE session ends

2. **Enhanced User Metrics Tracking**
   - **Watch Time**: Approximated from interaction timespan (first to last)
   - **Gift Tracking**: Both gift count AND total coin value
   - **Comprehensive Stats**: Likes, comments, shares, gifts, coins per user
   - Shows Discord username + TikTok handle for identification

3. **Professional Table Format**
   - ASCII table with aligned columns
   - Columns: Discord User, TikTok Handle, Watch Time, Likes, Comments, Shares, Gifts, Coins
   - Displays up to 15 top contributors with overflow indication
   - Session @handle in embed title
   - Overall session stats as embed fields

4. **Database Enhancements**
   - Enhanced `get_session_user_stats()` with watch time calculation
   - Added gift count aggregation
   - Timestamp-based watch time using MIN/MAX interaction timestamps

### TikTok Connection System (2025-10-09) ✅
1. **Persistent Connection with Retry Logic**
   - `/tiktok connect` supports persistent mode (default: enabled)
   - Automatic retry when user is offline
   - Smart retry intervals: 10s for first 3 attempts, 30s thereafter
   - Handles all error scenarios

2. **Connection Status Command**
   - `/tiktok status` displays real-time connection state
   - Shows uptime, retry count, session ID
   - Three states: Active, In Progress, Disconnected
   - Color-coded embeds with helpful footers

3. **Enhanced Disconnect Functionality**
   - Handles both active connections and connection attempts
   - Can cancel in-progress connection attempts
   - Proper cleanup of session data and state
   - Posts session summary when disconnecting

4. **Database Performance Optimizations**
   - Added 7 strategic indices for frequently queried columns
   - Composite index for Free queue ordering
   - Optimized Free queue query to use total_score
   - Partial index on Free queue for efficiency

### Enhanced Features (2025-10-09) ✅

1. **TikTok Handle Autocomplete**
   - Autocomplete in `/submit` and `/submitfile` commands
   - Database-driven suggestions from existing handles
   - Validation ensures only valid handles selected

2. **Ephemeral Submission Confirmations**
   - All submission confirmations are private
   - Reduces channel clutter
   - Better user privacy

3. **Enhanced Reset Points System**
   - `/resetpoints` supports multiple modes
   - Target specific user + all linked handles
   - `reset_all=True` to reset ALL TikTok handles

4. **Per-Handle Points Tracking**
   - Points tracked at TikTok handle level
   - Handles accumulate points independently
   - Earn points even without Discord link

5. **Automatic Free Line Points Reset**
   - Points reset when FREE queue songs play
   - Resets both submitter and linked handles
   - Encourages continued engagement

6. **Enhanced Reviewer Display**
   - Detailed points breakdown with emojis
   - 👍 Likes, 💬 Comments, 🔁 Shares, 🎁 Gifts
   - Better visibility of engagement metrics

7. **Persistent Interactive Views**
   - All reviewer views use `timeout=None`
   - Views remain active indefinitely
   - No expiration on interactive buttons

8. **Auto-Refreshing Queue Displays**
   - Automatic updates on queue state changes
   - Event-driven refresh via `queue_update` events
   - Real-time synchronization

## System Architecture

### UI/UX Decisions
- **Discord.py v2.x Framework**: Modern Discord bot features with slash commands and interactive UI
- **Dual Submission Methods**: Modal for links, Attachment for file uploads
- **File Upload Support**: MP3, WAV, M4A, FLAC up to 25MB with validation
- **Real-time Embed Updates**: Pinned messages auto-update on queue changes
- **Enhanced Reviewer Display**: Detailed points breakdown with emoji decorations
- **Persistent Interactive Views**: All reviewer views use `timeout=None`
- **Auto-Refreshing Queue Displays**: Event-driven automatic updates
- **Post-Live Metrics Channel**: Dedicated channel for session analytics
- **Disconnect Notifications**: Automatic debug channel alerts for stream endings

### Technical Implementations
- **Async/Await Pattern**: Fully asynchronous for concurrent operations
- **Cog-Based Organization**: Modular architecture with separate cogs
- **Lock-Based Concurrency**: `asyncio.Lock()` prevents race conditions
- **Enum-Based Queue Lines**: Type-safe queue line definitions
- **TikTok Handle Autocomplete**: Database-driven suggestions and validation
- **Ephemeral Submission Confirmations**: Private messages reduce clutter
- **Per-Handle Points Tracking**: Points tracked at TikTok handle level
- **Automatic Free Line Points Reset**: Points reset on FREE queue plays
- **Persistent TikTok Connection**: Retry logic for offline users
- **Connection Status Command**: Real-time state with uptime and session info
- **Enhanced Disconnect Functionality**: Handles connections and attempts
- **Disconnect Notifications**: Automatic debug channel alerts
- **State Flag Management**: `_user_initiated_disconnect` flag for proper tracking

### Feature Specifications
- **Enhanced Reset Points System**: Multiple reset modes for flexibility
- **Queue Management System**: Four-tier priority with FIFO processing
- **Single Free Submission Limit**: One active submission per user in Free queue
- **User Isolation**: Users only see their own submissions via `/mysubmissions`
- **Comprehensive Post-Live Metrics**: Watch time, gifts, coins, interactions per user
- **Smart Disconnect Tracking**: Distinguishes manual vs unexpected disconnects

### System Design Choices
- **Database Performance Optimizations**: Strategic indices and optimized queries
- **Channel ID Type Safety**: All channel IDs cast to int before lookup
- **Flag-Based State Management**: Clean disconnect type tracking
- **Notification Deduplication**: Only unexpected disconnects trigger alerts

## External Dependencies

### Core Dependencies
- **discord.py (>=2.3.2)**: Discord API wrapper
- **aiosqlite (>=0.19.0)**: Asynchronous SQLite database interface
- **python-dotenv (>=1.0.0)**: Environment variable management
- **TikTokLive (>=2.2.1)**: TikTok Live stream integration

### Discord API Integration
- **Bot Token Authentication**: Token stored in environment variables
- **Guild Integration**: Full guild member and message management
- **Channel Management**: Automatic pinned message creation and updates

### Database Integration
- **SQLite File Storage**: Local file-based database (`music_queue.db`)
- **Async Database Operations**: Non-blocking queries using `aiosqlite`
- **Automatic Schema Creation**: Database tables created on first run

### Environment Configuration
- **Replit Integration**: Designed for Replit platform deployment
- **Environment Variables**: Bot token and config via environment variables
- **Logging System**: File and console logging for monitoring

### Slash Command Synchronization
- **GUILD_ID Environment Variable**: Optional for immediate server-specific sync
