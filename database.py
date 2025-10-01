"""
Database module for Discord Music Queue Bot
Handles SQLite operations for submissions and queue management
"""

import aiosqlite
import asyncio
import os
from typing import List, Dict, Optional, Any
from enum import Enum

class QueueLine(Enum):
    """Enum for queue line types with priority order"""
    BACKTOBACK = "BackToBack"
    DOUBLESKIP = "DoubleSkip"
    SKIP = "Skip"
    FREE = "Free"
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
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    artist_name TEXT NOT NULL,
                    song_name TEXT NOT NULL,
                    link_or_file TEXT,
                    queue_line TEXT NOT NULL,
                    submission_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    position INTEGER DEFAULT 0
                )
            """)

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

            await db.execute("""
                CREATE TABLE IF NOT EXISTS submission_channel (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER UNIQUE
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS submission_status (
                    id INTEGER PRIMARY KEY,
                    submissions_open BOOLEAN DEFAULT 1
                )
            """)

            await db.execute("""
                INSERT OR IGNORE INTO submission_status (id, submissions_open) VALUES (1, 1)
            """)

            await db.commit()

    async def add_submission(self, user_id: int, username: str, artist_name: str,
                           song_name: str, link_or_file: str, queue_line: str) -> int:
        """Add a new submission to the database"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO submissions (user_id, username, artist_name, song_name, link_or_file, queue_line)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, artist_name, song_name, link_or_file, queue_line))

            submission_id = cursor.lastrowid
            await db.commit()
            return submission_id or 0

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
        Sorts "Calls Played" by most recent, and others by oldest.
        """
        sort_order = "DESC" if queue_line == QueueLine.CALLS_PLAYED.value else "ASC"
        query = f"SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time {sort_order}"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (queue_line,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_queue_submissions_paginated(self, queue_line: str, page: int, per_page: int) -> List[Dict[str, Any]]:
        """
        Get submissions for a specific queue line with pagination.
        Sorts "Calls Played" by most recent, and others by oldest.
        """
        offset = (page - 1) * per_page
        sort_order = "DESC" if queue_line == QueueLine.CALLS_PLAYED.value else "ASC"
        query = f"SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time {sort_order} LIMIT ? OFFSET ?"

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

    async def remove_submission(self, submission_id: int) -> Optional[str]:
        """Remove a submission by ID and return its original queue line."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("BEGIN"):
                async with db.execute("SELECT queue_line FROM submissions WHERE id = ?", (submission_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None

                original_line = row['queue_line']

                cursor = await db.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
                if cursor.rowcount == 0:
                    await db.rollback()
                    return None

            await db.commit()
            return original_line

    async def move_submission(self, submission_id: int, target_line: str) -> Optional[str]:
        """Move a submission to a different queue line and return its original queue line."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("BEGIN"):
                async with db.execute("SELECT queue_line FROM submissions WHERE id = ?", (submission_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                original_line = row['queue_line']

                if original_line == target_line:
                    return original_line

                cursor = await db.execute("UPDATE submissions SET queue_line = ? WHERE id = ?", (target_line, submission_id))
                if cursor.rowcount == 0:
                    await db.rollback()
                    return None

            await db.commit()
            return original_line

    async def get_next_submission(self) -> Optional[Dict[str, Any]]:
        """Get the next submission following priority order"""
        priority_order = [QueueLine.BACKTOBACK.value, QueueLine.DOUBLESKIP.value,
                         QueueLine.SKIP.value, QueueLine.FREE.value]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for queue_line in priority_order:
                async with db.execute("SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC LIMIT 1", (queue_line,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
        return None

    async def take_next_to_calls_played(self) -> Optional[Dict[str, Any]]:
        """Atomically move the next submission to Calls Played line"""
        priority_order = [QueueLine.BACKTOBACK.value, QueueLine.DOUBLESKIP.value,
                         QueueLine.SKIP.value, QueueLine.FREE.value]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN")
            try:
                for queue_line in priority_order:
                    async with db.execute("SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC LIMIT 1", (queue_line,)) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            submission_dict = dict(row)
                            original_line = submission_dict['queue_line']
                            await db.execute("UPDATE submissions SET queue_line = ? WHERE id = ?", (QueueLine.CALLS_PLAYED.value, submission_dict['id']))
                            await db.commit()
                            submission_dict['original_line'] = original_line
                            return submission_dict
                await db.commit()
                return None
            except Exception:
                await db.rollback()
                raise

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

    async def set_submissions_status(self, open_status: bool):
        """Set whether submissions are open or closed"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE submission_status SET submissions_open = ? WHERE id = 1", (open_status,))
            await db.commit()

    async def are_submissions_open(self) -> bool:
        """Check if submissions are currently open"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT submissions_open FROM submission_status WHERE id = 1") as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else True

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

    async def set_bookmark_channel(self, channel_id: int):
        """Set the bookmark channel"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('bookmark_channel', ?)", (str(channel_id),))
            await db.commit()

    async def get_bookmark_channel(self) -> Optional[int]:
        """Get the bookmark channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'bookmark_channel'") as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else None

    async def get_submission_by_id(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific submission by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def close(self):
        """Close database connection"""
        pass