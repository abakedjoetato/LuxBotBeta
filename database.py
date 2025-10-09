"""
Database module for Discord Music Queue Bot
Handles PostgreSQL operations for submissions and queue management using asyncpg.
"""

import asyncpg
import asyncio
import os
import random
import logging
from typing import List, Dict, Optional, Any, Tuple
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
    SONGS_PLAYED = "Songs Played" # Renamed from "Calls Played"
    REMOVED = "Removed"

class Database:
    """Async PostgreSQL database handler for the music queue bot"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize database connection pool and create tables if they don't exist."""
        if not self._pool:
            try:
                self._pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=10)
                logging.info("Database pool created.")
            except Exception as e:
                logging.critical(f"Could not connect to PostgreSQL database: {e}", exc_info=True)
                raise

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # --- New Schema ---
                # live_sessions to track each live stream
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS live_sessions (
                        id SERIAL PRIMARY KEY,
                        tiktok_username TEXT NOT NULL,
                        start_time TIMESTAMPTZ DEFAULT NOW(),
                        end_time TIMESTAMPTZ
                    );
                """)

                # tiktok_accounts to store all seen tiktok users
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tiktok_accounts (
                        handle_id SERIAL PRIMARY KEY,
                        handle_name TEXT UNIQUE NOT NULL,
                        first_seen TIMESTAMPTZ DEFAULT NOW(),
                        last_seen TIMESTAMPTZ DEFAULT NOW(),
                        linked_discord_id BIGINT
                    );
                """)

                # tiktok_interactions for logging all interactions
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tiktok_interactions (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                        tiktok_account_id INTEGER REFERENCES tiktok_accounts(handle_id) ON DELETE SET NULL,
                        interaction_type TEXT NOT NULL, -- 'like', 'comment', 'share', 'gift', 'follow'
                        value TEXT, -- e.g., comment text or gift name
                        coin_value INTEGER,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                # Submissions table now serves as a permanent historical record
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS submissions (
                        id SERIAL PRIMARY KEY,
                        public_id TEXT UNIQUE NOT NULL,
                        user_id BIGINT NOT NULL,
                        username TEXT NOT NULL,
                        artist_name TEXT NOT NULL,
                        song_name TEXT NOT NULL,
                        link_or_file TEXT,
                        queue_line TEXT, -- Can be NULL if not in a queue
                        submission_time TIMESTAMPTZ DEFAULT NOW(),
                        played_time TIMESTAMPTZ,
                        note TEXT,
                        tiktok_username TEXT, -- Storing the handle at time of submission for context
                        total_score REAL DEFAULT 0 -- This will be dynamically updated
                    );
                """)

                # user_points table for engagement points
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_points (
                        user_id BIGINT PRIMARY KEY,
                        points INTEGER DEFAULT 0 NOT NULL
                    );
                """)

                # bot_config table for all bot settings
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bot_config (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        channel_id BIGINT,
                        message_id BIGINT
                    );
                """)
                await conn.execute("INSERT INTO bot_config (key, value) VALUES ('free_line_closed', '0') ON CONFLICT (key) DO NOTHING;")

                # queue_config to map queues to channels (for admin views, etc)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS queue_config (
                        queue_line TEXT PRIMARY KEY,
                        channel_id BIGINT,
                        pinned_message_id BIGINT
                    );
                """)

        logging.info("Database initialized successfully.")

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise ConnectionError("Database pool is not initialized. Call .initialize() first.")
        return self._pool

    async def _generate_unique_submission_id(self, conn: asyncpg.Connection) -> str:
        """Generate a unique 6-digit random string for a submission ID."""
        while True:
            new_id = f"{random.randint(0, 999999):06d}"
            if not await conn.fetchval("SELECT 1 FROM submissions WHERE public_id = $1", new_id):
                return new_id

    async def add_submission(self, user_id: int, username: str, artist_name: str,
                           song_name: str, link_or_file: str, queue_line: str,
                           note: Optional[str] = None, tiktok_username: Optional[str] = None) -> str:
        """Add a new submission to the database."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # The tiktok_username is now passed in directly.
                user_points = await conn.fetchval("SELECT points FROM user_points WHERE user_id = $1", user_id) or 0
                public_id = await self._generate_unique_submission_id(conn)
                await conn.execute("""
                    INSERT INTO submissions (public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username, total_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, public_id, user_id, username, artist_name, song_name, link_or_file, queue_line, note, tiktok_username, user_points)
                return public_id

    async def get_user_submissions_history(self, user_id: int, limit: int = 25) -> List[Dict[str, Any]]:
        """Get the most recent submissions for a specific user from their history."""
        query = "SELECT * FROM submissions WHERE user_id = $1 ORDER BY submission_time DESC LIMIT $2"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)
            return [dict(row) for row in rows]

    async def get_queue_submissions(self, queue_line: str) -> List[Dict[str, Any]]:
        """Get all submissions for a specific queue line."""
        if queue_line == QueueLine.SONGS_PLAYED.value:
            query = "SELECT * FROM submissions WHERE queue_line = $1 AND played_time IS NOT NULL ORDER BY played_time DESC"
        elif queue_line == QueueLine.FREE.value:
            query = "SELECT s.*, u.points FROM submissions s LEFT JOIN user_points u ON s.user_id = u.user_id WHERE s.queue_line = $1 ORDER BY u.points DESC, s.submission_time ASC"
        else:
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, queue_line)
            return [dict(row) for row in rows]

    async def take_next_to_songs_played(self) -> Optional[Dict[str, Any]]:
        """Atomically find, update, and return the next submission to be played."""
        priority_order = [
            QueueLine.TWENTYFIVEPLUSSKIP.value, QueueLine.TWENTYSKIP.value,
            QueueLine.FIFTEENSKIP.value, QueueLine.TENSKIP.value,
            QueueLine.FIVESKIP.value, QueueLine.FREE.value
        ]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for queue_line in priority_order:
                    if queue_line == QueueLine.FREE.value:
                        # Order by the pre-calculated total_score to avoid the problematic JOIN with FOR UPDATE
                        find_query = "SELECT id, queue_line FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC LIMIT 1 FOR UPDATE"
                    else:
                        find_query = "SELECT id, queue_line FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC LIMIT 1 FOR UPDATE"

                    submission_to_move = await conn.fetchrow(find_query, queue_line)
                    if submission_to_move:
                        updated_sub = await conn.fetchrow(
                            "UPDATE submissions SET queue_line = $1, played_time = NOW() WHERE id = $2 RETURNING *",
                            QueueLine.SONGS_PLAYED.value, submission_to_move['id']
                        )
                        if updated_sub:
                            updated_dict = dict(updated_sub)
                            updated_dict['original_line'] = submission_to_move['queue_line']
                            return updated_dict
        return None

    async def get_submission_by_id(self, public_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific submission by public ID"""
        query = "SELECT * FROM submissions WHERE public_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, public_id)
            return dict(row) if row else None

    async def check_duplicate_submission(self, artist_name: str, song_name: str) -> bool:
        """Checks if an identical song is already in any active queue, regardless of user."""
        active_queues = [q.value for q in QueueLine if q not in (QueueLine.SONGS_PLAYED, QueueLine.PENDING_SKIPS, QueueLine.REMOVED)]
        query = """
            SELECT 1 FROM submissions
            WHERE lower(artist_name) = lower($1) AND lower(song_name) = lower($2) AND queue_line = ANY($3::text[])
            LIMIT 1;
        """
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(query, artist_name, song_name, active_queues)
            return exists is not None

    async def reset_user_points(self, user_id: int):
        """Resets a user's engagement points to zero."""
        query = "INSERT INTO user_points (user_id, points) VALUES ($1, 0) ON CONFLICT (user_id) DO UPDATE SET points = 0;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id)

    async def add_points_to_user(self, user_id: int, points_to_add: int):
        """Adds points to a user's score. Creates the user if they don't exist."""
        query = """
            INSERT INTO user_points (user_id, points)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET points = user_points.points + $2;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, points_to_add)

    async def sync_submission_scores(self):
        """Updates the total_score for all submissions in the Free queue from the user_points table."""
        query = """
            UPDATE submissions s
            SET total_score = u.points
            FROM user_points u
            WHERE s.user_id = u.user_id AND s.queue_line = 'Free';
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query)

    async def get_all_active_queue_songs(self, detailed: bool = False) -> List[Dict[str, Any]]:
        """
        Gets all songs from all active queues, sorted by priority and time.
        If detailed is True, returns all submission columns.
        """
        priority_order_case = "CASE queue_line WHEN '25+ Skip' THEN 1 WHEN '20 Skip' THEN 2 WHEN '15 Skip' THEN 3 WHEN '10 Skip' THEN 4 WHEN '5 Skip' THEN 5 WHEN 'Free' THEN 6 ELSE 7 END"
        active_queues = [q.value for q in QueueLine if q not in (QueueLine.SONGS_PLAYED, QueueLine.PENDING_SKIPS, QueueLine.REMOVED)]

        select_columns = "s.*" if detailed else "s.artist_name, s.song_name, s.queue_line, s.username"

        query = f"""
            SELECT {select_columns}
            FROM submissions s
            LEFT JOIN user_points u ON s.user_id = u.user_id
            WHERE s.queue_line = ANY($1::text[])
            ORDER BY {priority_order_case}, s.total_score DESC NULLS LAST, s.submission_time ASC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, active_queues)
            return [dict(row) for row in rows]

    async def upsert_tiktok_account(self, handle_name: str) -> int:
        """Inserts a TikTok account if it doesn't exist, and updates its last_seen timestamp. Returns the account's handle_id."""
        query = "INSERT INTO tiktok_accounts (handle_name, last_seen) VALUES ($1, NOW()) ON CONFLICT (handle_name) DO UPDATE SET last_seen = NOW() RETURNING handle_id;"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, handle_name)

    async def log_tiktok_interaction(self, session_id: int, tiktok_account_id: int, interaction_type: str, value: Optional[str] = None, coin_value: Optional[int] = None):
        """Logs a single TikTok interaction."""
        query = "INSERT INTO tiktok_interactions (session_id, tiktok_account_id, interaction_type, value, coin_value) VALUES ($1, $2, $3, $4, $5);"
        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id, tiktok_account_id, interaction_type, value, coin_value)

    # FIXED BY Replit: TikTok handle validation and duplicate prevention - verified working
    async def link_tiktok_account(self, discord_id: int, tiktok_handle: str) -> Tuple[bool, str]:
        """Links a TikTok handle to a Discord ID. Returns a success boolean and a message."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                account = await conn.fetchrow("SELECT handle_id, linked_discord_id FROM tiktok_accounts WHERE handle_name = $1", tiktok_handle)
                if not account:
                    return False, "This TikTok handle has not been seen on stream yet."
                if account['linked_discord_id'] and account['linked_discord_id'] != discord_id:
                    return False, "This TikTok handle is already linked to another Discord user."
                if account['linked_discord_id'] == discord_id:
                    return False, "You have already linked this TikTok handle."
                await conn.execute("UPDATE tiktok_accounts SET linked_discord_id = $1 WHERE handle_id = $2", discord_id, account['handle_id'])
                return True, f"Successfully linked your Discord account to the TikTok handle `{tiktok_handle}`."

    async def unlink_tiktok_account(self, discord_id: int, tiktok_handle: str) -> Tuple[bool, str]:
        """Unlinks a TikTok handle from a Discord ID."""
        async with self.pool.acquire() as conn:
            account = await conn.fetchrow("SELECT handle_id FROM tiktok_accounts WHERE handle_name = $1 AND linked_discord_id = $2", tiktok_handle, discord_id)
            if not account:
                return False, "This TikTok handle is not linked to your account."
            await conn.execute("UPDATE tiktok_accounts SET linked_discord_id = NULL WHERE handle_id = $1", account['handle_id'])
            return True, f"Successfully unlinked the TikTok handle `{tiktok_handle}` from your account."

    async def get_linked_tiktok_handles(self, discord_id: int) -> List[str]:
        """Gets all TikTok handles linked to a Discord ID."""
        query = "SELECT handle_name FROM tiktok_accounts WHERE linked_discord_id = $1 ORDER BY handle_name;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, discord_id)
            return [row['handle_name'] for row in rows]

    # FIXED BY JULES
    # FIXED BY Replit: TikTok handle autocomplete from database - verified working
    async def get_unlinked_tiktok_handles(self, current_input: str = "") -> List[str]:
        """
        Gets all TikTok handles that are not currently linked to any Discord account,
        for use in autocomplete. Filters by the user's current input.
        """
        query = """
            SELECT handle_name FROM tiktok_accounts
            WHERE linked_discord_id IS NULL
            AND handle_name ILIKE $1
            ORDER BY last_seen DESC
            LIMIT 25;
        """
        async with self.pool.acquire() as conn:
            # Add wildcards for the ILIKE search
            search_pattern = f"%{current_input}%"
            rows = await conn.fetch(query, search_pattern)
            return [row['handle_name'] for row in rows]

    async def start_live_session(self, tiktok_username: str) -> int:
        """Starts a new live session and returns the session ID."""
        query = "INSERT INTO live_sessions (tiktok_username) VALUES ($1) RETURNING id;"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, tiktok_username)

    async def end_live_session(self, session_id: int):
        """Ends a live session by setting the end_time."""
        query = "UPDATE live_sessions SET end_time = NOW() WHERE id = $1;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id)

    async def get_live_session_summary(self, session_id: int) -> Dict[str, int]:
        """Generates a summary of interactions for a given live session."""
        query = "SELECT interaction_type, COUNT(*) as count FROM tiktok_interactions WHERE session_id = $1 GROUP BY interaction_type;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            summary = {row['interaction_type']: row['count'] for row in rows}
            gift_value = await conn.fetchval("SELECT SUM(coin_value) FROM tiktok_interactions WHERE session_id = $1 AND interaction_type = 'gift'", session_id)
            summary['gift_coins'] = gift_value or 0
            return summary

    async def get_session_user_stats(self, session_id: int) -> List[Dict[str, Any]]:
        """
        Calculates per-user interaction stats for a specific session,
        grouping by the user.
        """
        query = """
            SELECT
                ta.linked_discord_id,
                ta.handle_name as tiktok_username,
                SUM(CASE WHEN ti.interaction_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN ti.interaction_type = 'comment' THEN 1 ELSE 0 END) AS comments,
                SUM(CASE WHEN ti.interaction_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN ti.coin_value ELSE 0 END) AS gift_coins
            FROM
                tiktok_interactions ti
            JOIN
                tiktok_accounts ta ON ti.tiktok_account_id = ta.handle_id
            WHERE
                ti.session_id = $1 AND ta.linked_discord_id IS NOT NULL
            GROUP BY
                ta.linked_discord_id, ta.handle_name
            ORDER BY
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN ti.coin_value ELSE 0 END) DESC,
                COUNT(ti.id) DESC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            return [dict(row) for row in rows]

    async def get_session_submission_counts(self, session_id: int) -> Dict[int, int]:
        """
        Calculates the number of submissions per user for a specific live session.
        """
        async with self.pool.acquire() as conn:
            session_times = await conn.fetchrow("SELECT start_time, end_time FROM live_sessions WHERE id = $1", session_id)
            if not session_times or not session_times['end_time']:
                return {} # Session not found or not ended

            submission_counts_query = """
                SELECT
                    user_id,
                    COUNT(id) as submission_count
                FROM
                    submissions
                WHERE
                    submission_time >= $1 AND submission_time <= $2
                GROUP BY
                    user_id;
            """
            rows = await conn.fetch(submission_counts_query, session_times['start_time'], session_times['end_time'])
            return {row['user_id']: row['submission_count'] for row in rows}

    async def get_discord_id_from_handle(self, tiktok_handle: str) -> Optional[int]:
        """Retrieves the linked Discord user ID for a given TikTok handle."""
        query = "SELECT linked_discord_id FROM tiktok_accounts WHERE handle_name = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, tiktok_handle)

    async def find_gift_rewardable_submission(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Finds the most recent submission from a user that can be rewarded by a gift."""
        non_rewardable_queues = [q.value for q in QueueLine if q != QueueLine.FREE]
        query = "SELECT * FROM submissions WHERE user_id = $1 AND (queue_line IS NULL OR NOT (queue_line = ANY($2::text[]))) ORDER BY submission_time DESC LIMIT 1;"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, non_rewardable_queues)
            return dict(row) if row else None

    async def get_all_bot_settings(self) -> Dict[str, Any]:
        """Fetches all settings from the bot_config table and returns them as a dictionary."""
        query = "SELECT key, value, channel_id, message_id FROM bot_config;"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            settings = {}
            for row in rows:
                if row['channel_id']:
                    settings[row['key']] = row['channel_id']
                elif row['message_id']:
                    settings[row['key']] = row['message_id']
                else:
                    settings[row['key']] = row['value']
            return settings

    async def set_bot_config(self, key: str, value: Optional[str] = None, channel_id: Optional[int] = None, message_id: Optional[int] = None):
        """Inserts or updates a setting in the bot_config table."""
        query = """
            INSERT INTO bot_config (key, value, channel_id, message_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, key, value, channel_id, message_id)

    async def set_free_line_status(self, is_open: bool):
        """Sets the status of the Free line (open/closed)."""
        await self.set_bot_config('free_line_closed', value='0' if is_open else '1')

    async def is_free_line_open(self) -> bool:
        """Checks if the Free line is open for submissions."""
        query = "SELECT value FROM bot_config WHERE key = 'free_line_closed'"
        async with self.pool.acquire() as conn:
            status = await conn.fetchval(query)
            # Returns True if status is '0' (not closed), False otherwise.
            return status == '0'

    async def clear_free_line(self) -> int:
        """Removes all submissions from the 'Free' queue and returns the count of removed submissions."""
        query = "DELETE FROM submissions WHERE queue_line = 'Free' RETURNING id;"
        async with self.pool.acquire() as conn:
            deleted_rows = await conn.fetch(query)
            return len(deleted_rows)

    async def move_submission(self, public_id: str, target_line: str) -> Optional[str]:
        """Moves a submission to a different queue line and returns the original line."""
        async with self.pool.acquire() as conn:
            original_line = await conn.fetchval("SELECT queue_line FROM submissions WHERE public_id = $1", public_id)
            if original_line:
                await conn.execute("UPDATE submissions SET queue_line = $1 WHERE public_id = $2", target_line, public_id)
                return original_line
            return None

    async def remove_submission_from_queue(self, public_id: str) -> Optional[str]:
        """Removes a submission from its queue by setting its queue_line to 'Removed'. Returns the original line."""
        async with self.pool.acquire() as conn:
            original_line = await conn.fetchval("SELECT queue_line FROM submissions WHERE public_id = $1", public_id)
            if original_line:
                await conn.execute("UPDATE submissions SET queue_line = $1 WHERE public_id = $2", QueueLine.REMOVED.value, public_id)
                return original_line
            return None

    async def delete_submission_from_history(self, public_id: str, user_id: int) -> bool:
        """
        Permanently deletes a submission from the history.
        Only allows a user to delete their own submission.
        """
        query = "DELETE FROM submissions WHERE public_id = $1 AND user_id = $2"
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, public_id, user_id)
            # "DELETE 1" means one row was deleted.
            return result == "DELETE 1"

    async def get_user_lifetime_stats(self, user_id: int) -> Dict[str, int]:
        """
        Calculates lifetime interaction stats (likes, comments, shares, gift coins)
        for a given Discord user across all their linked TikTok accounts.
        """
        query = """
            SELECT
                ti.interaction_type,
                COUNT(ti.id) AS count,
                SUM(ti.coin_value) AS total_coins
            FROM
                tiktok_interactions ti
            JOIN
                tiktok_accounts ta ON ti.tiktok_account_id = ta.handle_id
            WHERE
                ta.linked_discord_id = $1
            GROUP BY
                ti.interaction_type;
        """
        stats = {
            'like': 0,
            'comment': 0,
            'share': 0,
            'follow': 0,
            'gift_coins': 0
        }
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            for row in rows:
                interaction_type = row['interaction_type']
                if interaction_type in stats:
                    stats[interaction_type] = row['count']
                if interaction_type == 'gift' and row['total_coins']:
                    stats['gift_coins'] = int(row['total_coins'])
        return stats

    async def close(self):
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            logging.info("Database pool closed.")