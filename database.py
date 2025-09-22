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

class Database:
    """Async SQLite database handler for the music queue bot"""
    
    def __init__(self, db_path: str = "music_queue.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()
    
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
            
            await db.commit()
    
    async def add_submission(self, user_id: int, username: str, artist_name: str, 
                           song_name: str, link_or_file: str, queue_line: str) -> int:
        """Add a new submission to the database"""
        async with self._lock:
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
            async with db.execute("""
                SELECT * FROM submissions WHERE user_id = ? ORDER BY submission_time ASC
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_queue_submissions(self, queue_line: str) -> List[Dict[str, Any]]:
        """Get all submissions for a specific queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM submissions WHERE queue_line = ? ORDER BY submission_time ASC
            """, (queue_line,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def remove_submission(self, submission_id: int) -> bool:
        """Remove a submission by ID"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    DELETE FROM submissions WHERE id = ?
                """, (submission_id,))
                await db.commit()
                return cursor.rowcount > 0
    
    async def move_submission(self, submission_id: int, target_line: str) -> bool:
        """Move a submission to a different queue line"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    UPDATE submissions SET queue_line = ? WHERE id = ?
                """, (target_line, submission_id))
                await db.commit()
                return cursor.rowcount > 0
    
    async def get_next_submission(self) -> Optional[Dict[str, Any]]:
        """Get the next submission following priority order"""
        priority_order = [QueueLine.BACKTOBACK.value, QueueLine.DOUBLESKIP.value, 
                         QueueLine.SKIP.value, QueueLine.FREE.value]
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for queue_line in priority_order:
                async with db.execute("""
                    SELECT * FROM submissions WHERE queue_line = ? 
                    ORDER BY submission_time ASC LIMIT 1
                """, (queue_line,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
        return None
    
    async def set_channel_for_line(self, queue_line: str, channel_id: int, pinned_message_id: Optional[int] = None):
        """Set the channel for a queue line"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO channel_settings (queue_line, channel_id, pinned_message_id)
                    VALUES (?, ?, ?)
                """, (queue_line, channel_id, pinned_message_id))
                await db.commit()
    
    async def get_channel_for_line(self, queue_line: str) -> Optional[Dict[str, Any]]:
        """Get channel settings for a queue line"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM channel_settings WHERE queue_line = ?
            """, (queue_line,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def update_pinned_message(self, queue_line: str, pinned_message_id: int):
        """Update the pinned message ID for a queue line"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE channel_settings SET pinned_message_id = ? WHERE queue_line = ?
                """, (pinned_message_id, queue_line))
                await db.commit()
    
    async def get_user_submission_count_in_line(self, user_id: int, queue_line: str) -> int:
        """Get count of user's submissions in a specific line"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT COUNT(*) FROM submissions WHERE user_id = ? AND queue_line = ?
            """, (user_id, queue_line)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0