"""
Data Migration Script

This script migrates data from an SQLite database to a PostgreSQL database
and moves associated files from a local directory to a Backblaze B2 bucket.

**Prerequisites:**
1.  A backup of the SQLite database file (e.g., 'music_queue.db').
2.  A backup of the associated assets folder (e.g., 'attached_assets/').
3.  The following environment variables must be set in a .env file or in your environment:
    - `DATABASE_URL`: The connection URL for your PostgreSQL database.
    - `B2_ENDPOINT_URL`: The endpoint URL for your Backblaze B2 bucket.
    - `B2_ACCESS_KEY_ID`: Your Backblaze B2 Application Key ID.
    - `B2_SECRET_ACCESS_KEY`: Your Backblaze B2 Application Key.
    - `B2_BUCKET_NAME`: The name of your Backblaze B2 bucket.
"""

import aiosqlite
import asyncpg
import asyncio
import os
import logging
from dotenv import load_dotenv
from s3_utils import S3Client  # Assuming s3_utils.py is in the same directory
import uuid

# --- Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Paths to your backed-up data ---
SQLITE_DB_PATH = "music_queue.db"
ATTACHED_ASSETS_PATH = "attached_assets/"

# --- Helper Functions ---
def is_discord_cdn_url(url: str) -> bool:
    """Check if a URL is a Discord CDN URL, which indicates a file upload."""
    return "cdn.discordapp.com/attachments" in url

async def get_sqlite_data(conn: aiosqlite.Connection, table_name: str) -> list:
    """Fetch all data from a specific table in the SQLite database."""
    conn.row_factory = aiosqlite.Row
    async with conn.execute(f"SELECT * FROM {table_name}") as cursor:
        return [dict(row) for row in await cursor.fetchall()]

async def migrate_submissions(sqlite_conn: aiosqlite.Connection, pg_pool: asyncpg.Pool, s3_client: S3Client):
    """Migrate submissions, handling file uploads to S3."""
    logging.info("Starting submissions migration...")
    submissions = await get_sqlite_data(sqlite_conn, "submissions")

    async with pg_pool.acquire() as pg_conn:
        # Disable triggers to speed up bulk inserts if necessary, though for this size it's likely fine.
        # await pg_conn.execute("SET session_replication_role = 'replica';")

        for sub in submissions:
            link_or_file = sub.get('link_or_file')
            new_link_or_file = link_or_file

            if link_or_file and is_discord_cdn_url(link_or_file):
                # This is a file that needs to be moved to S3
                try:
                    # Extract the original filename from the Discord URL
                    # e.g., https://cdn.discordapp.com/attachments/channel_id/attachment_id/filename.mp3
                    original_filename = os.path.basename(link_or_file.split('?')[0])
                    local_file_path = os.path.join(ATTACHED_ASSETS_PATH, original_filename)

                    if os.path.exists(local_file_path):
                        # Create a unique object name for S3
                        file_extension = os.path.splitext(original_filename)[1]
                        object_name = f"submissions/{sub['user_id']}/{uuid.uuid4()}{file_extension}"

                        logging.info(f"Uploading {local_file_path} to S3 as {object_name}...")
                        success = await s3_client.upload_file_from_path(local_file_path, object_name)

                        if success:
                            new_link_or_file = s3_client.get_public_file_url(object_name)
                            logging.info(f"Successfully uploaded. New URL: {new_link_or_file}")
                        else:
                            logging.warning(f"Failed to upload {local_file_path} to S3. Skipping S3 migration for this entry.")
                    else:
                        logging.warning(f"Local file not found: {local_file_path}. Cannot upload to S3.")
                except Exception as e:
                    logging.error(f"Error processing file for submission {sub.get('id')}: {e}")

            # Insert into PostgreSQL
            await pg_conn.execute("""
                INSERT INTO submissions (
                    id, public_id, user_id, username, artist_name, song_name,
                    link_or_file, queue_line, submission_time, position, played_time,
                    note, tiktok_username, live_watch_score, live_interaction_score, total_score
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
                ) ON CONFLICT (id) DO NOTHING
            """,
            sub.get('id'), sub.get('public_id'), sub.get('user_id'), sub.get('username'),
            sub.get('artist_name'), sub.get('song_name'), new_link_or_file, sub.get('queue_line'),
            sub.get('submission_time'), sub.get('position', 0), sub.get('played_time'), sub.get('note'),
            sub.get('tiktok_username'), sub.get('live_watch_score', 0), sub.get('live_interaction_score', 0),
            sub.get('total_score', 0)
            )

        # Re-enable triggers
        # await pg_conn.execute("SET session_replication_role = 'origin';")
        logging.info(f"Finished migrating {len(submissions)} submissions.")

async def migrate_simple_table(sqlite_conn: aiosqlite.Connection, pg_pool: asyncpg.Pool, table_name: str, columns: list, pk_column: str):
    """Migrate a simple table with direct column mapping."""
    logging.info(f"Starting migration for table: {table_name}...")
    data = await get_sqlite_data(sqlite_conn, table_name)

    if not data:
        logging.info(f"Table {table_name} is empty. Nothing to migrate.")
        return

    async with pg_pool.acquire() as pg_conn:
        for row in data:
            cols = ', '.join(columns)
            placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
            values = [row.get(col) for col in columns]

            query = f"""
                INSERT INTO {table_name} ({cols})
                VALUES ({placeholders})
                ON CONFLICT ({pk_column}) DO NOTHING
            """
            await pg_conn.execute(query, *values)
    logging.info(f"Finished migrating {len(data)} rows for table {table_name}.")


async def main():
    """Main function to run the migration."""
    logging.info("--- Starting Data Migration ---")

    # --- Verify prerequisites ---
    if not os.path.exists(SQLITE_DB_PATH):
        logging.error(f"FATAL: SQLite database not found at '{SQLITE_DB_PATH}'. Aborting.")
        return
    if not os.path.isdir(ATTACHED_ASSETS_PATH):
        logging.error(f"FATAL: Attached assets folder not found at '{ATTACHED_ASSETS_PATH}'. Aborting.")
        return

    pg_url = os.getenv("DATABASE_URL")
    if not pg_url:
        logging.error("FATAL: DATABASE_URL environment variable not set. Aborting.")
        return

    try:
        s3_client = S3Client()
    except ValueError as e:
        logging.error(f"FATAL: {e}. Aborting.")
        return

    pg_pool = None
    sqlite_conn = None
    try:
        # --- Establish connections ---
        pg_pool = await asyncpg.create_pool(pg_url)
        if not pg_pool: raise ConnectionError("Failed to create PostgreSQL pool.")
        sqlite_conn = await aiosqlite.connect(SQLITE_DB_PATH)
        logging.info("Successfully connected to both PostgreSQL and SQLite databases.")

        # --- Run migrations for each table ---
        await migrate_simple_table(sqlite_conn, pg_pool, 'channel_settings', ['queue_line', 'channel_id', 'pinned_message_id'], 'queue_line')
        await migrate_simple_table(sqlite_conn, pg_pool, 'bot_settings', ['key', 'value'], 'key')
        await migrate_simple_table(sqlite_conn, pg_pool, 'submission_channel', ['id', 'channel_id'], 'id')
        await migrate_simple_table(sqlite_conn, pg_pool, 'tiktok_handles', ['user_id', 'tiktok_username'], 'user_id')

        # Run submission migration which includes S3 logic
        await migrate_submissions(sqlite_conn, pg_pool, s3_client)

        # After migrating submissions, it's good practice to reset the sequence for the primary key
        # so new inserts don't conflict.
        async with pg_pool.acquire() as conn:
            await conn.execute("SELECT setval('submissions_id_seq', (SELECT MAX(id) FROM submissions));")
            logging.info("Reset PostgreSQL submissions_id_seq.")

        logging.info("--- Data Migration Completed Successfully! ---")

    except Exception as e:
        logging.error(f"An error occurred during migration: {e}", exc_info=True)
    finally:
        # --- Clean up connections ---
        if pg_pool:
            await pg_pool.close()
            logging.info("PostgreSQL connection pool closed.")
        if sqlite_conn:
            await sqlite_conn.close()
            logging.info("SQLite connection closed.")

if __name__ == "__main__":
    asyncio.run(main())