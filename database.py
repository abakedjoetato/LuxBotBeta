"""
Database module for Discord Music Queue Bot
Handles SQLite operations for submissions and queue management
"""

import aiosqlite
import asyncio
import os
import random
from typing import List, Dict, Optional, Any
from enum import Enum

class QueueLine(Enum):
    """Enum for queue line types with priority order"""
    FIVESKIP = "5 Skip"
    TENSKIP = "10 Skip"
    FIFTEENSKIP = "15 Skip"
    TWENTYSKIP = "20 Skip"
    TWENTYFIVEPLUSSKIP = "25+ Skip"
    FREE = "Free"
    PENDING_SKIPS = "Pending Skips"
    CALLS_PLAYED = "Calls Played"

class Database:
    """Async SQLite database handler for the music queue bot"""

    def __init__(self, db_path: str = "music_queue.db"):
        self.db_path = db_path

    async def initialize(self):
        """Initialize database tables"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    artist_name TEXT NOT NULL,
                    song_name TEXT NOT NULL,
                    link_or_file TEXT,
                    queue_line TEXT NOT NULL,
                    submission_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    position INTEGER DEFAULT 0,
                    played_time DATETIME,
                    note TEXT,
                    tiktok_username TEXT
                )
            """)

            # For existing databases, add columns if they don't exist
            async with db.execute("PRAGMA table_info(submissions)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
            if 'played_time' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN played_time DATETIME")
            if 'public_id' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN public_id TEXT")
                await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_public_id ON submissions (public_id)")
            if 'note' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN note TEXT")
            if 'tiktok_username' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN tiktok_username TEXT")
            if 'live_watch_score' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN live_watch_score REAL DEFAULT 0")
            if 'live_interaction_score' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN live_interaction_score REAL DEFAULT 0")
            if 'total_score' not in columns:
                await db.execute("ALTER TABLE submissions ADD COLUMN total_score REAL DEFAULT 0")

            # Populate public_id for existing rows
            async with db.execute("SELECT id FROM submissions WHERE public_id IS NULL") as cursor:
                rows_to_update = await cursor.fetchall()
                for row in rows_to_update:
                    submission_id = row[0]
                    public_id = await self._generate_unique_submission_id(db)
                    await db.execute("UPDATE submissions SET public_id = ? WHERE id = ?", (public_id, submission_id))

            await db.execute("""
                CREATE TABLE IF NOT EXISTS channel_settings (
                    queue_line TEXT PRIMARY KEY,
                    channel_id INTEGER,
                    pinned_message_id INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Add default settings
            await db.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES ('free_line_closed', '0')")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS submission_channel (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER UNIQUE
                )
            """)

            await db.execute("DROP TABLE IF EXISTS submission_status")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tiktok_handles (
                    user_id INTEGER PRIMARY KEY,
                    tiktok_username TEXT NOT NULL
                )
            """)

            await db.commit()

    async def _generate_unique_submission_id(self, db: aiosqlite.Connection) -> str:
        """Generate a unique 6-digit random string for a submission ID."""
        while True:
            new_id = f"{random.randint(0, 999999):06d}"
            async with db.execute("SELECT 1 FROM submissions WHERE public_id = ?", (new_id,)) as cursor:
                if await cursor.fetchone() is None:
                    return new_id

    async def add_submission(self, user_id: int, username: str, artist_name: str,
                           song_name: str, link_or_file: str, queue_line: str,
                           note: Optional[str] = None) -> str:
        """Add a new submission to the database, automatically attaching the user's saved TikTok handle."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get the user's saved TikTok handle
            async with db.execute("SELECT tiktok_username FROM tiktok_handles WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                tiktok_username = row[0] if row else None

            public_id = await self._generate_unique_submission_id(db)
            await db.execute("""
                INSERT INTO submissions (public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username))

            await db.commit()
            return public_id

    async def get_user_submissions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all submissions for a specific user"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM submissions WHERE user_id = ? ORDER BY submission_time ASC", (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_queue_submissions(self, queue_line: str) -> List[Dict[str, Any]]:
        """
        Get all submissions for a specific queue line.
        Sorts "Calls Played" by played time (most recent first).
        Sorts "Free" line by total_score (desc) and then submission_time (asc).
        Sorts other lines by submission_time (oldest first).
        """
        if queue_line == QueueLine.CALLS_PLAYED.value:
            query = "SELECT * FROM submissions WHERE queue_line = ? AND played_time IS NOT NULL ORDER BY played_time DESC"
        elif queue_line == QueueLine.FREE.value:
            query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY total_score DESC, submission_time ASC"
        else:
            query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (queue_line,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_queue_submissions_paginated(self, queue_line: str, page: int, per_page: int) -> List[Dict[str, Any]]:
        """
        Get submissions for a specific queue line with pagination.
        Sorts "Calls Played" by played time (most recent first).
        Sorts "Free" line by total_score (desc) and then submission_time (asc).
        Sorts other lines by submission_time (oldest first).
        """
        offset = (page - 1) * per_page
        if queue_line == QueueLine.CALLS_PLAYED.value:
            query = "SELECT * FROM submissions WHERE queue_line = ? AND played_time IS NOT NULL ORDER BY played_time DESC LIMIT ? OFFSET ?"
        elif queue_line == QueueLine.FREE.value:
            query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY total_score DESC, submission_time ASC LIMIT ? OFFSET ?"
        else:
            query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC LIMIT ? OFFSET ?"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (queue_line, per_page, offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_queue_submission_count(self, queue_line: str) -> int:
        """Get total count of submissions in a specific queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM submissions WHERE queue_line = ?", (queue_line,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def remove_submission(self, public_id: str) -> Optional[str]:
        """Remove a submission by public ID and return its original queue line."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("BEGIN"):
                async with db.execute("SELECT queue_line FROM submissions WHERE public_id = ?", (public_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None

                original_line = row['queue_line']

                cursor = await db.execute("DELETE FROM submissions WHERE public_id = ?", (public_id,))
                if cursor.rowcount == 0:
                    await db.rollback()
                    return None

            await db.commit()
            return original_line

    async def move_submission(self, public_id: str, target_line: str) -> Optional[str]:
        """Move a submission to a different queue line, update its timestamp, and return its original queue line."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("BEGIN"):
                async with db.execute("SELECT queue_line FROM submissions WHERE public_id = ?", (public_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                original_line = row['queue_line']

                if original_line == target_line:
                    return original_line

                cursor = await db.execute("UPDATE submissions SET queue_line = ?, submission_time = CURRENT_TIMESTAMP WHERE public_id = ?", (target_line, public_id))
                if cursor.rowcount == 0:
                    await db.rollback()
                    return None

            await db.commit()
            return original_line

    async def get_next_submission(self) -> Optional[Dict[str, Any]]:
        """Get the next submission following priority order, excluding Pending Skips."""
        priority_order = [
            QueueLine.TWENTYFIVEPLUSSKIP.value,
            QueueLine.TWENTYSKIP.value,
            QueueLine.FIFTEENSKIP.value,
            QueueLine.TENSKIP.value,
            QueueLine.FIVESKIP.value,
            QueueLine.FREE.value
        ]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for queue_line in priority_order:
                # Special handling for the Free line to use the new scoring system
                if queue_line == QueueLine.FREE.value:
                    query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY total_score DESC, submission_time ASC LIMIT 1"
                else:
                    query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC LIMIT 1"

                async with db.execute(query, (queue_line,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
        return None

    async def take_next_to_calls_played(self) -> Optional[Dict[str, Any]]:
        """Atomically move the next submission to Calls Played line and ensure commit."""
        priority_order = [
            QueueLine.TWENTYFIVEPLUSSKIP.value,
            QueueLine.TWENTYSKIP.value,
            QueueLine.FIFTEENSKIP.value,
            QueueLine.TENSKIP.value,
            QueueLine.FIVESKIP.value,
            QueueLine.FREE.value
        ]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for queue_line in priority_order:
                # Special handling for the Free line to use the new scoring system
                if queue_line == QueueLine.FREE.value:
                    query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY total_score DESC, submission_time ASC LIMIT 1"
                else:
                    query = "SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC LIMIT 1"

                async with db.execute(query, (queue_line,)) as cursor:
                    row = await cursor.fetchone()

                if row:
                    submission_dict = dict(row)
                    original_line = submission_dict['queue_line']

                    await db.execute(
                        "UPDATE submissions SET queue_line = ?, played_time = CURRENT_TIMESTAMP WHERE id = ?",
                        (QueueLine.CALLS_PLAYED.value, submission_dict['id'])
                    )
                    await db.commit()

                    submission_dict['original_line'] = original_line
                    return submission_dict
        return None

    async def set_channel_for_line(self, queue_line: str, channel_id: int, pinned_message_id: Optional[int] = None):
        """Set the channel for a queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO channel_settings (queue_line, channel_id, pinned_message_id) VALUES (?, ?, ?)", (queue_line, channel_id, pinned_message_id))
            await db.commit()

    async def get_channel_for_line(self, queue_line: str) -> Optional[Dict[str, Any]]:
        """Get channel settings for a queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM channel_settings WHERE queue_line = ?", (queue_line,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_pinned_message(self, queue_line: str, pinned_message_id: int):
        """Update the pinned message ID for a queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE channel_settings SET pinned_message_id = ? WHERE queue_line = ?", (pinned_message_id, queue_line))
            await db.commit()

    async def get_user_submission_count_in_line(self, user_id: int, queue_line: str) -> int:
        """Get count of user's submissions in a specific line"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND queue_line = ?", (user_id, queue_line)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def set_submission_channel(self, channel_id: int):
        """Set the submission channel"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO submission_channel (id, channel_id) VALUES (1, ?)", (channel_id,))
            await db.commit()

    async def get_submission_channel(self) -> Optional[int]:
        """Get the submission channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT channel_id FROM submission_channel WHERE id = 1") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_free_line_status(self, is_open: bool):
        """Set whether the Free line is open or closed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('free_line_closed', ?)", ('0' if is_open else '1',))
            await db.commit()

    async def is_free_line_open(self) -> bool:
        """Check if the Free line is currently open."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'free_line_closed'") as cursor:
                row = await cursor.fetchone()
                # Default to open if not set
                return row[0] == '0' if row else True

    async def clear_free_line(self) -> int:
        """Clear all submissions from the Free line and return count of cleared submissions"""
        async with aiosqlite.connect(self.db_path) as db:
            count = 0
            async with db.execute("BEGIN"):
                async with db.execute("SELECT COUNT(*) FROM submissions WHERE queue_line = ?", (QueueLine.FREE.value,)) as cursor:
                    count_result = await cursor.fetchone()
                    count = count_result[0] if count_result else 0
                
                if count > 0:
                    await db.execute("DELETE FROM submissions WHERE queue_line = ?", (QueueLine.FREE.value,))

            await db.commit()
            return count

    async def set_now_playing_channel(self, channel_id: int):
        """Set the now playing channel."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('now_playing_channel_id', ?)", (str(channel_id),))
            await db.commit()

    async def get_now_playing_channel(self) -> Optional[int]:
        """Get the now playing channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'now_playing_channel_id'") as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        return int(row[0])
                    except (ValueError, TypeError):
                        return None
        return None

    async def clear_stale_queue_lines(self) -> int:
        """Removes queue lines from channel_settings that are no longer in the QueueLine enum. Returns the number of lines removed."""
        async with aiosqlite.connect(self.db_path) as db:
            valid_queue_lines = [ql.value for ql in QueueLine]

            placeholders = ', '.join('?' for _ in valid_queue_lines)

            # Use a transaction to ensure atomicity
            async with db.execute("BEGIN"):
                delete_query = f"DELETE FROM channel_settings WHERE queue_line NOT IN ({placeholders})"
                cursor = await db.execute(delete_query, valid_queue_lines)
                rows_deleted = cursor.rowcount

            await db.commit()
            print(f"DATABASE: Removed {rows_deleted} stale queue lines.")
            return rows_deleted

    async def get_submission_by_id(self, public_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific submission by public ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM submissions WHERE public_id = ?", (public_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def set_bookmark_channel(self, channel_id: int):
        """Set the bookmark channel. Raises an exception on failure."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('bookmark_channel_id', ?)", (str(channel_id),))
            await db.commit()

    async def get_bookmark_channel(self) -> Optional[int]:
        """Get the bookmark channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'bookmark_channel_id'") as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        return int(row[0])
                    except (ValueError, TypeError):
                        return None
        return None

    async def get_all_channel_settings(self) -> List[Dict[str, Any]]:
        """Get all configured queue line channels."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM channel_settings ORDER BY queue_line") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_bot_settings(self) -> Dict[str, Any]:
        """Get all settings from the bot_settings table."""
        settings = {}
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT key, value FROM bot_settings") as cursor:
                async for row in cursor:
                    key, value = row
                    # Try to convert to int if possible, otherwise keep as string
                    if value is not None:
                        try:
                            settings[key] = int(value)
                        except (ValueError, TypeError):
                            settings[key] = value
                    else:
                        settings[key] = None
        return settings

    async def update_free_line_scores(self, viewer_scores: Dict[str, float]):
        """
        Recalculates and updates the watch time and total scores for all submissions in the Free line.
        viewer_scores: A dictionary mapping tiktok_username to total watch time in minutes.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Use a transaction for bulk updates
            async with db.execute("BEGIN"):
                # Get all free line submissions
                async with db.execute("SELECT id, tiktok_username, live_interaction_score FROM submissions WHERE queue_line = ?", (QueueLine.FREE.value,)) as cursor:
                    free_line_subs = await cursor.fetchall()

                # Calculate and update scores for each submission
                for sub in free_line_subs:
                    watch_time = viewer_scores.get(sub['tiktok_username'], 0)
                    live_watch_score = watch_time * 1.0  # 1 point per minute watched
                    total_score = live_watch_score + sub['live_interaction_score']

                    await db.execute(
                        "UPDATE submissions SET live_watch_score = ?, total_score = ? WHERE id = ?",
                        (live_watch_score, total_score, sub['id'])
                    )
            await db.commit()

    async def add_interaction_score(self, public_id: str, points: float):
        """Adds points to a submission's interaction score and updates the total score."""
        async with aiosqlite.connect(self.db_path) as db:
            # Atomically update the scores
            await db.execute(
                """
                UPDATE submissions
                SET
                    live_interaction_score = live_interaction_score + ?,
                    total_score = total_score + ?
                WHERE public_id = ?
                """,
                (points, points, public_id)
            )
            await db.commit()

    async def find_active_submission_by_tiktok_user(self, tiktok_username: str) -> Optional[Dict[str, Any]]:
        """
        Finds the most recent submission from a TikTok user that is eligible for a reward.
        An eligible submission is one that is not already in a priority queue or played.
        """
        eligible_lines = [QueueLine.FREE.value, QueueLine.PENDING_SKIPS.value]
        placeholders = ', '.join('?' for _ in eligible_lines)
        query = f"""
            SELECT * FROM submissions
            WHERE tiktok_username = ? AND queue_line IN ({placeholders})
            ORDER BY submission_time DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (tiktok_username, *eligible_lines)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def set_tiktok_handle(self, user_id: int, tiktok_username: str):
        """Sets or updates a user's TikTok handle in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tiktok_handles (user_id, tiktok_username) VALUES (?, ?)",
                (user_id, tiktok_username)
            )
            await db.commit()

    async def get_tiktok_handle(self, user_id: int) -> Optional[str]:
        """Retrieves a user's saved TikTok handle."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT tiktok_username FROM tiktok_handles WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def update_user_submissions_tiktok_handle(self, user_id: int, tiktok_username: str):
        """Updates the TikTok handle for all of a user's existing, unplayed submissions."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE submissions SET tiktok_username = ? WHERE user_id = ? AND queue_line != ?",
                (tiktok_username, user_id, QueueLine.CALLS_PLAYED.value)
            )
            await db.commit()

    async def close(self):
        """Close database connection"""
        pass