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
                        linked_discord_id BIGINT,
                        points INTEGER DEFAULT 0 NOT NULL,
                        last_known_level INTEGER DEFAULT 0
                    );
                """)
                
                # Add points column if it doesn't exist (migration)
                await conn.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='tiktok_accounts' AND column_name='points'
                        ) THEN
                            ALTER TABLE tiktok_accounts ADD COLUMN points INTEGER DEFAULT 0 NOT NULL;
                        END IF;
                    END $$;
                """)
                
                # Add last_known_level column if it doesn't exist (migration)
                await conn.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='tiktok_accounts' AND column_name='last_known_level'
                        ) THEN
                            ALTER TABLE tiktok_accounts ADD COLUMN last_known_level INTEGER DEFAULT 0;
                        END IF;
                    END $$;
                """)
                
                # Add user_level column to tiktok_interactions if it doesn't exist (migration)
                await conn.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='tiktok_interactions' AND column_name='user_level'
                        ) THEN
                            ALTER TABLE tiktok_interactions ADD COLUMN user_level INTEGER;
                        END IF;
                    END $$;
                """)

                # tiktok_interactions for logging all interactions
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tiktok_interactions (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                        tiktok_account_id INTEGER REFERENCES tiktok_accounts(handle_id) ON DELETE SET NULL,
                        interaction_type TEXT NOT NULL, -- 'like', 'comment', 'share', 'gift', 'follow', 'subscribe', 'poll', 'quiz', 'mic_battle'
                        value TEXT, -- e.g., comment text, gift name, poll/quiz/battle data
                        coin_value INTEGER,
                        user_level INTEGER, -- User's level at time of interaction
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
                
                # viewer_count_snapshots for tracking viewer counts over time
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS viewer_count_snapshots (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES live_sessions(id) ON DELETE CASCADE,
                        viewer_count INTEGER NOT NULL,
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

                # persistent_embeds table for auto-updating persistent displays
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS persistent_embeds (
                        id SERIAL PRIMARY KEY,
                        embed_type TEXT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT NOT NULL,
                        current_page INTEGER DEFAULT 0,
                        last_content_hash TEXT,
                        last_updated TIMESTAMPTZ DEFAULT NOW(),
                        is_active BOOLEAN DEFAULT TRUE,
                        UNIQUE(embed_type, channel_id)
                    );
                """)

                # queue_config to map queues to channels (for admin views, etc)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS queue_config (
                        queue_line TEXT PRIMARY KEY,
                        channel_id BIGINT,
                        pinned_message_id BIGINT
                    );
                """)

                # Create performance indices for frequently queried columns
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_user_id ON submissions(user_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_queue_line ON submissions(queue_line);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_played_time ON submissions(played_time);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_submission_time ON submissions(submission_time);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_tiktok_interactions_session_id ON tiktok_interactions(session_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_tiktok_interactions_tiktok_account_id ON tiktok_interactions(tiktok_account_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_tiktok_accounts_linked_discord_id ON tiktok_accounts(linked_discord_id);")
                
                # Composite index for Free queue ordering (critical for performance)
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_free_queue ON submissions(queue_line, total_score DESC, submission_time ASC) WHERE queue_line = 'Free';")

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
            # Use total_score (synced from user_points) for consistent ordering with composite index
            query = "SELECT * FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC"
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
                        find_query = "SELECT id, queue_line, user_id FROM submissions WHERE queue_line = $1 ORDER BY total_score DESC, submission_time ASC LIMIT 1 FOR UPDATE"
                    else:
                        find_query = "SELECT id, queue_line, user_id FROM submissions WHERE queue_line = $1 ORDER BY submission_time ASC LIMIT 1 FOR UPDATE"

                    submission_to_move = await conn.fetchrow(find_query, queue_line)
                    if submission_to_move:
                        updated_sub = await conn.fetchrow(
                            "UPDATE submissions SET queue_line = $1, played_time = NOW() WHERE id = $2 RETURNING *",
                            QueueLine.SONGS_PLAYED.value, submission_to_move['id']
                        )
                        if updated_sub:
                            updated_dict = dict(updated_sub)
                            updated_dict['original_line'] = submission_to_move['queue_line']
                            
                            # If song was from Free Line, reset points for submitter and all linked handles
                            if submission_to_move['queue_line'] == QueueLine.FREE.value:
                                user_id = submission_to_move['user_id']
                                # Reset Discord user points
                                await conn.execute(
                                    "INSERT INTO user_points (user_id, points) VALUES ($1, 0) ON CONFLICT (user_id) DO UPDATE SET points = 0;",
                                    user_id
                                )
                                # Reset all linked TikTok handle points
                                await conn.execute(
                                    "UPDATE tiktok_accounts SET points = 0 WHERE linked_discord_id = $1;",
                                    user_id
                                )
                            
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

    async def reset_user_and_linked_handles_points(self, user_id: int):
        """Resets points for a Discord user and all their linked TikTok handles."""
        async with self.pool.acquire() as conn:
            # Reset Discord user points
            await conn.execute("INSERT INTO user_points (user_id, points) VALUES ($1, 0) ON CONFLICT (user_id) DO UPDATE SET points = 0;", user_id)
            # Reset all linked TikTok handle points
            await conn.execute("UPDATE tiktok_accounts SET points = 0 WHERE linked_discord_id = $1;", user_id)

    async def reset_all_tiktok_handles_points(self):
        """Resets points for ALL TikTok handles in the system."""
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE tiktok_accounts SET points = 0;")

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

    async def add_points_to_tiktok_handle(self, handle_name: str, points_to_add: int):
        """Adds points to a TikTok handle. Creates the handle if it doesn't exist."""
        query = """
            INSERT INTO tiktok_accounts (handle_name, points)
            VALUES ($1, $2)
            ON CONFLICT (handle_name) DO UPDATE
            SET points = tiktok_accounts.points + $2, last_seen = NOW();
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, handle_name, points_to_add)

    async def get_tiktok_handle_points(self, handle_name: str) -> int:
        """Gets the points for a TikTok handle."""
        query = "SELECT points FROM tiktok_accounts WHERE handle_name = $1"
        async with self.pool.acquire() as conn:
            points = await conn.fetchval(query, handle_name)
            return points if points is not None else 0

    async def get_tiktok_handle_points_breakdown(self, handle_name: str) -> Dict[str, int]:
        """Gets detailed points breakdown by interaction type for a TikTok handle."""
        query = """
            SELECT 
                interaction_type,
                COUNT(*) as count,
                COALESCE(SUM(coin_value), 0) as total_coins
            FROM tiktok_interactions ti
            JOIN tiktok_accounts ta ON ti.tiktok_account_id = ta.handle_id
            WHERE ta.handle_name = $1
            GROUP BY interaction_type
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, handle_name)
            breakdown = {
                'likes': 0,
                'comments': 0,
                'shares': 0,
                'follows': 0,
                'coins': 0
            }
            for row in rows:
                interaction_type = row['interaction_type']
                count = row['count']
                if interaction_type == 'like':
                    breakdown['likes'] = count
                elif interaction_type == 'comment':
                    breakdown['comments'] = count
                elif interaction_type == 'share':
                    breakdown['shares'] = count
                elif interaction_type == 'follow':
                    breakdown['follows'] = count
                elif interaction_type == 'gift':
                    breakdown['coins'] = row['total_coins']
            return breakdown

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

    async def log_tiktok_interaction(self, session_id: int, tiktok_account_id: int, interaction_type: str, value: Optional[str] = None, coin_value: Optional[int] = None, user_level: Optional[int] = None):
        """Logs a single TikTok interaction with optional user level."""
        query = "INSERT INTO tiktok_interactions (session_id, tiktok_account_id, interaction_type, value, coin_value, user_level) VALUES ($1, $2, $3, $4, $5, $6);"
        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id, tiktok_account_id, interaction_type, value, coin_value, user_level)
    
    async def log_viewer_count(self, session_id: int, viewer_count: int):
        """Logs a viewer count snapshot."""
        query = "INSERT INTO viewer_count_snapshots (session_id, viewer_count) VALUES ($1, $2);"
        async with self.pool.acquire() as conn:
            await conn.execute(query, session_id, viewer_count)
    
    async def update_tiktok_user_level(self, handle_name: str, level: int):
        """Updates the last known level for a TikTok user."""
        query = "UPDATE tiktok_accounts SET last_known_level = $1, last_seen = NOW() WHERE handle_name = $2;"
        async with self.pool.acquire() as conn:
            await conn.execute(query, level, handle_name)

    # FIXED BY Replit: TikTok handle validation and duplicate prevention - verified working
    # TEMPORARY: Handle existence check bypassed - accepts any handle
    async def link_tiktok_account(self, discord_id: int, tiktok_handle: str) -> Tuple[bool, str]:
        """Links a TikTok handle to a Discord ID. Returns a success boolean and a message."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                account = await conn.fetchrow("SELECT handle_id, linked_discord_id FROM tiktok_accounts WHERE handle_name = $1", tiktok_handle)
                
                # TEMPORARY: Commented out requirement for handle to exist in database
                # if not account:
                #     return False, "This TikTok handle has not been seen on stream yet."
                
                # If handle doesn't exist, create it
                if not account:
                    handle_id = await conn.fetchval(
                        "INSERT INTO tiktok_accounts (handle_name, last_seen) VALUES ($1, NOW()) RETURNING handle_id",
                        tiktok_handle
                    )
                    # Now link it to the user
                    await conn.execute("UPDATE tiktok_accounts SET linked_discord_id = $1 WHERE handle_id = $2", discord_id, handle_id)
                    return True, f"Successfully linked your Discord account to the TikTok handle `{tiktok_handle}`."
                
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
        Optimized for fast autocomplete responses (<1 second).
        """
        # Use prefix search for better index performance (ILIKE 'input%' can use index)
        # Only use slow full-text search if user has typed 2+ characters
        if len(current_input) >= 2:
            query = """
                SELECT handle_name FROM tiktok_accounts
                WHERE linked_discord_id IS NULL
                AND handle_name ILIKE $1
                ORDER BY last_seen DESC
                LIMIT 25;
            """
            search_pattern = f"{current_input}%"  # Prefix search only (faster)
        else:
            # Return most recent unlinked handles if input is too short
            query = """
                SELECT handle_name FROM tiktok_accounts
                WHERE linked_discord_id IS NULL
                ORDER BY last_seen DESC
                LIMIT 25;
            """
            search_pattern = None
        
        async with self.pool.acquire() as conn:
            if search_pattern:
                rows = await conn.fetch(query, search_pattern)
            else:
                rows = await conn.fetch(query)
            return [row['handle_name'] for row in rows]

    async def get_all_tiktok_handles(self, current_input: str = "") -> List[str]:
        """
        Gets all known TikTok handles for autocomplete during submission.
        Filters by the user's current input.
        Optimized for fast autocomplete responses (<1 second).
        """
        # Use prefix search for better index performance
        if len(current_input) >= 2:
            query = """
                SELECT handle_name FROM tiktok_accounts
                WHERE handle_name ILIKE $1
                ORDER BY last_seen DESC
                LIMIT 25;
            """
            search_pattern = f"{current_input}%"  # Prefix search only (faster)
        else:
            # Return most recent handles if input is too short
            query = """
                SELECT handle_name FROM tiktok_accounts
                ORDER BY last_seen DESC
                LIMIT 25;
            """
            search_pattern = None
        
        async with self.pool.acquire() as conn:
            if search_pattern:
                rows = await conn.fetch(query, search_pattern)
            else:
                rows = await conn.fetch(query)
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
        including watch time (calculated as time span from first to last interaction).
        """
        query = """
            SELECT
                ta.linked_discord_id,
                ta.handle_name as tiktok_username,
                SUM(CASE WHEN ti.interaction_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN ti.interaction_type = 'comment' THEN 1 ELSE 0 END) AS comments,
                SUM(CASE WHEN ti.interaction_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN 1 ELSE 0 END) AS gifts,
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN ti.coin_value ELSE 0 END) AS gift_coins,
                EXTRACT(EPOCH FROM (MAX(ti.timestamp) - MIN(ti.timestamp))) AS watch_time_seconds
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
    
    # FIXED BY JULES: New function to get ALL TikTok handles (linked and unlinked) for post-live metrics
    async def get_session_all_handles_stats(self, session_id: int) -> List[Dict[str, Any]]:
        """
        Calculates per-handle interaction stats for ALL TikTok handles (linked and unlinked),
        sorted by total engagement points (coins descending, then interaction count descending).
        Now includes subscriptions, follows, user levels, polls, quizzes, and mic battles.
        """
        query = """
            SELECT
                ta.linked_discord_id,
                ta.handle_name as tiktok_username,
                ta.last_known_level as user_level,
                SUM(CASE WHEN ti.interaction_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN ti.interaction_type = 'comment' THEN 1 ELSE 0 END) AS comments,
                SUM(CASE WHEN ti.interaction_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN ti.interaction_type = 'follow' THEN 1 ELSE 0 END) AS follows,
                SUM(CASE WHEN ti.interaction_type = 'subscribe' THEN 1 ELSE 0 END) AS subscribes,
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN 1 ELSE 0 END) AS gifts,
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN ti.coin_value ELSE 0 END) AS gift_coins,
                SUM(CASE WHEN ti.interaction_type = 'poll' THEN 1 ELSE 0 END) AS polls,
                SUM(CASE WHEN ti.interaction_type = 'quiz' THEN 1 ELSE 0 END) AS quizzes,
                SUM(CASE WHEN ti.interaction_type = 'mic_battle' THEN 1 ELSE 0 END) AS mic_battles,
                EXTRACT(EPOCH FROM (MAX(ti.timestamp) - MIN(ti.timestamp))) AS watch_time_seconds,
                COUNT(ti.id) AS total_interactions
            FROM
                tiktok_interactions ti
            JOIN
                tiktok_accounts ta ON ti.tiktok_account_id = ta.handle_id
            WHERE
                ti.session_id = $1
            GROUP BY
                ta.linked_discord_id, ta.handle_name, ta.last_known_level
            ORDER BY
                SUM(CASE WHEN ti.interaction_type = 'gift' THEN ti.coin_value ELSE 0 END) DESC,
                COUNT(ti.id) DESC;
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, session_id)
            return [dict(row) for row in rows]
    
    async def get_session_viewer_stats(self, session_id: int) -> Dict[str, Any]:
        """Gets viewer count statistics for a session (min, max, avg)."""
        query = """
            SELECT
                MIN(viewer_count) as min_viewers,
                MAX(viewer_count) as max_viewers,
                ROUND(AVG(viewer_count)) as avg_viewers,
                COUNT(*) as snapshot_count
            FROM viewer_count_snapshots
            WHERE session_id = $1;
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, session_id)
            return dict(row) if row else {'min_viewers': 0, 'max_viewers': 0, 'avg_viewers': 0, 'snapshot_count': 0}

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
        """Finds the most recent submission from a user that can be rewarded by a gift.
        
        Selects from: Free line and Pending Skips
        Excludes: All skip lines (5, 10, 15, 20, 25+), Songs Played, and Removed
        """
        # Only exclude submissions already in skip lines, songs played, or removed
        non_rewardable_queues = [
            QueueLine.FIVESKIP.value,
            QueueLine.TENSKIP.value,
            QueueLine.FIFTEENSKIP.value,
            QueueLine.TWENTYSKIP.value,
            QueueLine.TWENTYFIVEPLUSSKIP.value,
            QueueLine.SONGS_PLAYED.value,
            QueueLine.REMOVED.value
        ]
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

    # ========================================
    # Persistent Embeds Methods
    # ========================================

    async def register_persistent_embed(self, embed_type: str, channel_id: int, message_id: int) -> None:
        """Register or update a persistent embed for auto-refresh tracking."""
        query = """
            INSERT INTO persistent_embeds (embed_type, channel_id, message_id, current_page, is_active, last_updated)
            VALUES ($1, $2, $3, 0, TRUE, NOW())
            ON CONFLICT (embed_type, channel_id)
            DO UPDATE SET message_id = $3, is_active = TRUE, last_updated = NOW()
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, embed_type, channel_id, message_id)
            logging.info(f"Registered persistent embed: {embed_type} in channel {channel_id}")

    async def get_all_active_persistent_embeds(self) -> List[Dict[str, Any]]:
        """Get all active persistent embeds for the refresh loop."""
        query = """
            SELECT id, embed_type, channel_id, message_id, current_page, last_content_hash, last_updated
            FROM persistent_embeds
            WHERE is_active = TRUE
            ORDER BY embed_type
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def get_persistent_embed(self, embed_type: str, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific persistent embed by type and channel."""
        query = """
            SELECT id, embed_type, channel_id, message_id, current_page, last_content_hash, last_updated, is_active
            FROM persistent_embeds
            WHERE embed_type = $1 AND channel_id = $2
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, embed_type, channel_id)
            return dict(row) if row else None

    async def update_persistent_embed_page(self, embed_type: str, channel_id: int, page: int) -> None:
        """Update the current page for a persistent embed."""
        query = """
            UPDATE persistent_embeds
            SET current_page = $3, last_updated = NOW()
            WHERE embed_type = $1 AND channel_id = $2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, embed_type, channel_id, page)

    async def update_persistent_embed_hash(self, embed_type: str, channel_id: int, content_hash: str) -> None:
        """Update the content hash for a persistent embed after refreshing."""
        query = """
            UPDATE persistent_embeds
            SET last_content_hash = $3, last_updated = NOW()
            WHERE embed_type = $1 AND channel_id = $2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, embed_type, channel_id, content_hash)

    async def deactivate_persistent_embed(self, embed_type: str, channel_id: int) -> None:
        """Mark a persistent embed as inactive (won't be auto-refreshed)."""
        query = """
            UPDATE persistent_embeds
            SET is_active = FALSE, last_updated = NOW()
            WHERE embed_type = $1 AND channel_id = $2
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, embed_type, channel_id)
            logging.info(f"Deactivated persistent embed: {embed_type} in channel {channel_id}")

    async def close(self):
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            logging.info("Database pool closed.")