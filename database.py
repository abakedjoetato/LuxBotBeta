"""
Database module for Discord Music Queue Bot
Handles PostgreSQL operations for submissions and queue management
"""

import asyncpg
import asyncio
import os
import random
from typing import List, Dict, Optional, Any, AsyncGenerator
from enum import Enum
import logging

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
    """Async PostgreSQL database handler for the music queue bot"""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._pool: Optional[asyncpg.Pool] = None

    async def get_pool(self) -> asyncpg.Pool:
        """Get the connection pool, creating it if it doesn't exist."""
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(self.db_url)
                if self._pool is None:
                    raise ConnectionError("Database pool could not be created.")
                logging.info("DATABASE: Connection pool created successfully.")
            except Exception as e:
                logging.error(f"DATABASE: Could not connect to PostgreSQL: {e}", exc_info=True)
                raise
        return self._pool

    async def close(self):
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            logging.info("DATABASE: Connection pool closed.")

    async def _execute(self, query: str, *args) -> List[asyncpg.Record]:
        """Execute a query and return the results."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute_val(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def _execute_row(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Execute a query and return a single row."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _execute_run(self, query: str, *args) -> None:
        """Execute a command query (e.g., INSERT, UPDATE, DELETE)."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, *args)

    async def initialize(self):
        """Initialize database tables"""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS submissions (
                        id SERIAL PRIMARY KEY,
                        public_id TEXT UNIQUE NOT NULL,
                        user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        artist_name TEXT NOT NULL,
                        song_name TEXT NOT NULL,
                        link_or_file TEXT,
                        queue_line TEXT NOT NULL,
                        submission_time TIMESTAMPTZ DEFAULT NOW(),
                        position INTEGER DEFAULT 0,
                        played_time TIMESTAMPTZ,
                        note TEXT,
                        tiktok_username TEXT,
                        live_watch_score REAL DEFAULT 0,
                        live_interaction_score REAL DEFAULT 0,
                        total_score REAL DEFAULT 0
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS channel_settings (
                        queue_line TEXT PRIMARY KEY,
                        channel_id BIGINT,
                        pinned_message_id BIGINT
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                await conn.execute("INSERT INTO bot_settings (key, value) VALUES ('free_line_closed', '0') ON CONFLICT (key) DO NOTHING")

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS submission_channel (
                        id INTEGER PRIMARY KEY,
                        channel_id BIGINT UNIQUE
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tiktok_handles (
                        user_id BIGINT PRIMARY KEY,
                        tiktok_username TEXT NOT NULL
                    )
                """)
        logging.info("DATABASE: All tables initialized successfully.")

    async def _generate_unique_submission_id(self) -> str:
        """Generate a unique 6-digit random string for a submission ID."""
        while True:
            new_id = f"{random.randint(0, 999999):06d}"
            exists = await self._execute_val("SELECT 1 FROM submissions WHERE public_id = $1", new_id)
            if not exists:
                return new_id

    async def add_submission(self, user_id: int, username: str, artist_name: str,
                           song_name: str, link_or_file: str, queue_line: str,
                           note: Optional[str] = None) -> str:
        """Add a new submission to the database, automatically attaching the user's saved TikTok handle."""
        tiktok_username = await self.get_tiktok_handle(user_id)
        public_id = await self._generate_unique_submission_id()
        query = """
            INSERT INTO submissions (public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        await self._execute_run(query, public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username)
        return public_id

    async def get_user_submissions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all submissions for a specific user"""
        rows = await self._execute("SELECT * FROM submissions WHERE user_id = $1 ORDER BY submission_time ASC", user_id)
        return [dict(row) for row in rows]

    async def get_queue_submissions(self, queue_line: str) -> List[Dict[str, Any]]:
        if queue_line == QueueLine.CALLS_PLAYED.value:
            query = "SELECT * FROM submissions WHERE queue_line = $1 AND played_time IS NOT NULL ORDER BY played_time DESC"
        elif queue_line == QueueLine.FREE.value:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC"
        else:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC"
        rows = await self._execute(query, queue_line)
        return [dict(row) for row in rows]

    async def get_queue_submissions_paginated(self, queue_line: str, page: int, per_page: int) -> List[Dict[str, Any]]:
        offset = (page - 1) * per_page
        if queue_line == QueueLine.CALLS_PLAYED.value:
            query = "SELECT * FROM submissions WHERE queue_line = $1 AND played_time IS NOT NULL ORDER BY played_time DESC LIMIT $2 OFFSET $3"
        elif queue_line == QueueLine.FREE.value:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC LIMIT $2 OFFSET $3"
        else:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC LIMIT $2 OFFSET $3"
        rows = await self._execute(query, queue_line, per_page, offset)
        return [dict(row) for row in rows]

    async def get_queue_submission_count(self, queue_line: str) -> int:
        count = await self._execute_val("SELECT COUNT(*) FROM submissions WHERE queue_line = $1", queue_line)
        return count or 0

    async def remove_submission(self, public_id: str) -> Optional[str]:
        """Remove a submission by public ID and return its original queue line."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                original_line = await conn.fetchval("SELECT queue_line FROM submissions WHERE public_id = $1", public_id)
                if not original_line:
                    return None
                result = await conn.execute("DELETE FROM submissions WHERE public_id = $1", public_id)
                if result == "DELETE 0":
                    return None
                return original_line

    async def move_submission(self, public_id: str, target_line: str) -> Optional[str]:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                original_line = await conn.fetchval("SELECT queue_line FROM submissions WHERE public_id = $1", public_id)
                if not original_line: return None
                if original_line == target_line: return original_line

                await conn.execute("UPDATE submissions SET queue_line = $1, submission_time = NOW() WHERE public_id = $2", target_line, public_id)
                return original_line

    async def get_next_submission(self) -> Optional[Dict[str, Any]]:
        priority_order = [
            QueueLine.TWENTYFIVEPLUSSKIP.value, QueueLine.TWENTYSKIP.value,
            QueueLine.FIFTEENSKIP.value, QueueLine.TENSKIP.value,
            QueueLine.FIVESKIP.value, QueueLine.FREE.value
        ]
        for queue_line in priority_order:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC LIMIT 1" if queue_line == QueueLine.FREE.value else "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC LIMIT 1"
            row = await self._execute_row(query, queue_line)
            if row: return dict(row)
        return None

    async def take_next_to_calls_played(self) -> Optional[Dict[str, Any]]:
        priority_order = [
            QueueLine.TWENTYFIVEPLUSSKIP.value, QueueLine.TWENTYSKIP.value,
            QueueLine.FIFTEENSKIP.value, QueueLine.TENSKIP.value,
            QueueLine.FIVESKIP.value, QueueLine.FREE.value
        ]
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            for queue_line in priority_order:
                query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC LIMIT 1" if queue_line == QueueLine.FREE.value else "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC LIMIT 1"
                row = await conn.fetchrow(query, queue_line)
                if row:
                    async with conn.transaction():
                        submission_dict = dict(row)
                        original_line = submission_dict['queue_line']
                        await conn.execute("UPDATE submissions SET queue_line = $1, played_time = NOW() WHERE id = $2", QueueLine.CALLS_PLAYED.value, submission_dict['id'])
                        submission_dict['original_line'] = original_line
                        return submission_dict
        return None

    async def set_channel_for_line(self, queue_line: str, channel_id: int, pinned_message_id: Optional[int] = None):
        query = "INSERT INTO channel_settings (queue_line, channel_id, pinned_message_id) VALUES ($1, $2, $3) ON CONFLICT (queue_line) DO UPDATE SET channel_id = $2, pinned_message_id = $3"
        await self._execute_run(query, queue_line, channel_id, pinned_message_id)

    async def get_channel_for_line(self, queue_line: str) -> Optional[Dict[str, Any]]:
        row = await self._execute_row("SELECT * FROM channel_settings WHERE queue_line = $1", queue_line)
        return dict(row) if row else None

    async def update_pinned_message(self, queue_line: str, pinned_message_id: int):
        await self._execute_run("UPDATE channel_settings SET pinned_message_id = $1 WHERE queue_line = $2", pinned_message_id, queue_line)

    async def get_user_submission_count_in_line(self, user_id: int, queue_line: str) -> int:
        count = await self._execute_val("SELECT COUNT(*) FROM submissions WHERE user_id = $1 AND queue_line = $2", user_id, queue_line)
        return count or 0

    async def set_submission_channel(self, channel_id: int):
        await self._execute_run("INSERT INTO submission_channel (id, channel_id) VALUES (1, $1) ON CONFLICT (id) DO UPDATE SET channel_id = $1", channel_id)

    async def get_submission_channel(self) -> Optional[int]:
        return await self._execute_val("SELECT channel_id FROM submission_channel WHERE id = 1")

    async def set_free_line_status(self, is_open: bool):
        await self._execute_run("INSERT INTO bot_settings (key, value) VALUES ('free_line_closed', $1) ON CONFLICT (key) DO UPDATE SET value = $1", '0' if is_open else '1')

    async def is_free_line_open(self) -> bool:
        val = await self._execute_val("SELECT value FROM bot_settings WHERE key = 'free_line_closed'")
        return val == '0' if val else True

    async def clear_free_line(self) -> int:
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute("DELETE FROM submissions WHERE queue_line = $1", QueueLine.FREE.value)
                # "DELETE N" -> N
                return int(result.split(" ")[1])

    async def set_now_playing_channel(self, channel_id: int):
        await self._execute_run("INSERT INTO bot_settings (key, value) VALUES ('now_playing_channel_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1", str(channel_id))

    async def get_now_playing_channel(self) -> Optional[int]:
        val = await self._execute_val("SELECT value FROM bot_settings WHERE key = 'now_playing_channel_id'")
        return int(val) if val and val.isdigit() else None

    async def clear_stale_queue_lines(self) -> int:
        valid_lines = [ql.value for ql in QueueLine]
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM channel_settings WHERE queue_line <> ALL($1)", valid_lines)
            return int(result.split(" ")[1])

    async def get_submission_by_id(self, public_id: str) -> Optional[Dict[str, Any]]:
        row = await self._execute_row("SELECT * FROM submissions WHERE public_id = $1", public_id)
        return dict(row) if row else None

    async def set_bookmark_channel(self, channel_id: int):
        await self._execute_run("INSERT INTO bot_settings (key, value) VALUES ('bookmark_channel_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1", str(channel_id))

    async def get_bookmark_channel(self) -> Optional[int]:
        val = await self._execute_val("SELECT value FROM bot_settings WHERE key = 'bookmark_channel_id'")
        return int(val) if val and val.isdigit() else None

    async def get_all_channel_settings(self) -> List[Dict[str, Any]]:
        rows = await self._execute("SELECT * FROM channel_settings ORDER BY queue_line")
        return [dict(row) for row in rows]

    async def get_all_bot_settings(self) -> Dict[str, Any]:
        settings = {}
        rows = await self._execute("SELECT key, value FROM bot_settings")
        for row in rows:
            key, value = row['key'], row['value']
            if value and value.isdigit():
                settings[key] = int(value)
            else:
                settings[key] = value
        return settings

    async def update_free_line_scores(self, viewer_scores: Dict[str, float]):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                free_line_subs = await conn.fetch("SELECT id, tiktok_username, live_interaction_score FROM submissions WHERE queue_line = $1", QueueLine.FREE.value)
                for sub in free_line_subs:
                    watch_time = viewer_scores.get(sub['tiktok_username'], 0)
                    live_watch_score = watch_time * 1.0
                    total_score = live_watch_score + sub['live_interaction_score']
                    await conn.execute("UPDATE submissions SET live_watch_score = $1, total_score = $2 WHERE id = $3", live_watch_score, total_score, sub['id'])

    async def add_interaction_score(self, public_id: str, points: float):
        query = "UPDATE submissions SET live_interaction_score = live_interaction_score + $1, total_score = total_score + $1 WHERE public_id = $2"
        await self._execute_run(query, points, public_id)

    async def find_active_submission_by_tiktok_user(self, tiktok_username: str) -> Optional[Dict[str, Any]]:
        eligible_lines = (QueueLine.FREE.value, QueueLine.PENDING_SKIPS.value)
        query = "SELECT * FROM submissions WHERE tiktok_username = $1 AND queue_line = ANY($2) ORDER BY submission_time DESC LIMIT 1"
        row = await self._execute_row(query, tiktok_username, eligible_lines)
        return dict(row) if row else None

    async def set_tiktok_handle(self, user_id: int, tiktok_username: str):
        query = "INSERT INTO tiktok_handles (user_id, tiktok_username) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET tiktok_username = $2"
        await self._execute_run(query, user_id, tiktok_username)

    async def get_tiktok_handle(self, user_id: int) -> Optional[str]:
        return await self._execute_val("SELECT tiktok_username FROM tiktok_handles WHERE user_id = $1", user_id)

    async def update_user_submissions_tiktok_handle(self, user_id: int, tiktok_username: str):
        query = "UPDATE submissions SET tiktok_username = $1 WHERE user_id = $2 AND queue_line != $3"
        await self._execute_run(query, tiktok_username, user_id, QueueLine.CALLS_PLAYED.value)