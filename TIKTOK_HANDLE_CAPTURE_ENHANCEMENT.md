# TikTok Handle Capture Enhancement

## Overview
Enhanced the TikTok Live integration to capture **ALL** TikTok handles that enter live sessions, not just those who actively interact. This ensures a complete database of all participants for linking and analytics purposes.

## Changes Implemented

### 1. Added JoinEvent Handler
**Location**: `cogs/tiktok_cog.py`

#### Import Addition (Line 12)
```python
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, LikeEvent, ShareEvent, FollowEvent, JoinEvent
```

#### Event Listener Registration (Line 145)
```python
client.add_listener(JoinEvent, self.on_join)
```

#### Event Handler Implementation (Lines 476-486)
```python
async def on_join(self, event: JoinEvent):
    """Captures TikTok handles when users join the stream (no points awarded for joining)."""
    if not self.current_session_id or not hasattr(event, 'user') or not hasattr(event.user, 'unique_id'):
        return
    
    try:
        # Just capture the handle in the database, no points awarded
        await self.bot.db.upsert_tiktok_account(event.user.unique_id)
        logging.debug(f"TIKTOK: User {event.user.unique_id} joined the stream (captured in database)")
    except Exception as e:
        logging.error(f"Failed to capture TikTok join event: {e}", exc_info=True)
```

## Complete Event Coverage

The system now captures TikTok handles from **all** of these events:

| Event | Purpose | Points Awarded | Database Captured |
|-------|---------|----------------|-------------------|
| **JoinEvent** | User enters stream | ❌ No | ✅ Yes |
| **LikeEvent** | Stream likes | ✅ 1 point | ✅ Yes |
| **CommentEvent** | Chat messages | ✅ 2 points | ✅ Yes |
| **ShareEvent** | Stream shares | ✅ 5 points | ✅ Yes |
| **FollowEvent** | New follows | ✅ 10 points | ✅ Yes |
| **GiftEvent** | Gift sends | ✅ Variable (coins × multiplier) | ✅ Yes |

## Key Features

### 1. Silent Capture
- Join events are captured silently in the background
- Uses `logging.debug()` to avoid log spam
- No notifications sent to users for joining

### 2. No Points for Joining
- Simply entering the stream does NOT award engagement points
- Points are only awarded for actual interactions (likes, comments, shares, follows, gifts)
- Maintains fair engagement metrics

### 3. Complete Participant List
- Every user who enters the stream is added to `tiktok_accounts` table
- Enables comprehensive post-live session analytics
- Allows users to link any handle they used during the stream

### 4. Database Integration
- Uses existing `upsert_tiktok_account()` function
- Automatically updates `last_seen` timestamp
- Handles duplicates gracefully (upsert pattern)

## Benefits

### 1. For Users
- Can immediately link their TikTok handle after joining stream
- Don't need to wait until they interact
- Better user experience during live sessions

### 2. For Analytics
- Complete participant metrics (not just active users)
- Accurate viewer counts and engagement ratios
- Better understanding of lurkers vs. active participants

### 3. For Admins
- Full visibility into stream participants
- More accurate session summaries
- Better data for post-live metrics

## Technical Details

### Error Handling
- Graceful failure if event data is malformed
- Comprehensive error logging for debugging
- No impact on other event handlers

### Performance
- Lightweight operation (single database upsert)
- Asynchronous execution (non-blocking)
- No additional API calls required

### Data Flow
```
User Joins TikTok Stream
    ↓
JoinEvent Triggered
    ↓
on_join() Handler
    ↓
upsert_tiktok_account(unique_id)
    ↓
Database Updated (handle_name, last_seen)
    ↓
Handle Available for Linking
```

## Testing Recommendations

### During Live Sessions
1. Connect to a TikTok LIVE stream
2. Monitor logs for "joined the stream" debug messages
3. Verify handles appear in database immediately
4. Test /link-tiktok with recently joined (but non-interactive) handles

### Database Verification
```sql
-- Check recently captured handles
SELECT handle_name, last_seen, linked_discord_id 
FROM tiktok_accounts 
ORDER BY last_seen DESC 
LIMIT 20;
```

## Related Changes

This enhancement works in conjunction with:
- **Temporary TikTok Handle Linking**: Users can link any handle without stream validation
- **Post-Live Metrics**: Shows ALL participants (linked and unlinked)
- **Engagement Tracking**: Distinguishes between joins and interactions

## Date
October 09, 2025
