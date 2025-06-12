import sqlite3
import logging

logger = logging.getLogger(__name__)

class ManhwaDB:
    def __init__(self, db_path: str = "data/manhwa.db"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def init_tables(self):
        """Initialize database tables"""
        with self:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS manhwa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    site_name TEXT NOT NULL,
                    telegram_user_id INTEGER NOT NULL,
                    last_chapter_url TEXT,
                    last_chapter_name TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    output_channel_id TEXT NOT NULL
                )
            """)
            logger.info("Database tables initialized.")

    def add_manhwa(self, name: str, url: str, site_name: str, telegram_user_id: int, last_chapter_url: str = "", last_chapter_name: str = ""):
        """Add a new manhwa to track"""
        with self:
            try:
                self.cursor.execute("""
                    INSERT INTO manhwa (name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name))
                logger.info(f"Added manhwa: {name}")
                return True
            except sqlite3.IntegrityError:
                logger.warning(f"Manhwa already exists: {name}")
                return False

    def get_all_manhwa(self):
        """Get all tracked manhwa"""
        with self:
            self.cursor.execute("SELECT name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name FROM manhwa")
            rows = self.cursor.fetchall()
            # Convert rows to objects or dicts for easier access
            class Manhwa:
                def __init__(self, name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name):
                    self.name = name
                    self.url = url
                    self.site_name = site_name
                    self.telegram_user_id = telegram_user_id
                    self.last_chapter_url = last_chapter_url
                    self.last_chapter_name = last_chapter_name
            return [Manhwa(*row) for row in rows]

    def get_manhwa_by_name(self, name: str):
        """Get a specific manhwa by name"""
        with self:
            self.cursor.execute("SELECT name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name FROM manhwa WHERE name = ?", (name,))
            row = self.cursor.fetchone()
            if row:
                class Manhwa:
                    def __init__(self, name, url, site_name, telegram_user_id, last_chapter_url, last_chapter_name):
                        self.name = name
                        self.url = url
                        self.site_name = site_name
                        self.telegram_user_id = telegram_user_id
                        self.last_chapter_url = last_chapter_url
                        self.last_chapter_name = last_chapter_name
                return Manhwa(*row)
            return None

    def update_manhwa_progress(self, name: str, last_chapter_url: str, last_chapter_name: str):
        """Update the last read chapter for a manhwa"""
        with self:
            self.cursor.execute("UPDATE manhwa SET last_chapter_url = ?, last_chapter_name = ? WHERE name = ?",
                                (last_chapter_url, last_chapter_name, name))
            logger.info(f"Updated progress for {name} to {last_chapter_name}")

    def remove_manhwa(self, name: str):
        """Remove a manhwa from tracking"""
        with self:
            self.cursor.execute("DELETE FROM manhwa WHERE name = ?", (name,))
            if self.cursor.rowcount > 0:
                logger.info(f"Removed manhwa: {name}")
                return True
            return False

    def set_user_output_channel(self, telegram_user_id: int, channel_id: str):
        """Set or update the output channel for a user"""
        with self:
            try:
                self.cursor.execute("""
                    INSERT INTO users (telegram_user_id, output_channel_id)
                    VALUES (?, ?)
                    ON CONFLICT(telegram_user_id) DO UPDATE SET
                    output_channel_id = excluded.output_channel_id
                """, (telegram_user_id, channel_id))
                logger.info(f"Set output channel for user {telegram_user_id} to {channel_id}")
                return True
            except Exception as e:
                logger.error(f"Error setting output channel for user {telegram_user_id}: {e}")
                return False

    def get_user_output_channel(self, telegram_user_id: int) -> str | None:
        """Get the output channel for a user"""
        with self:
            self.cursor.execute("SELECT output_channel_id FROM users WHERE telegram_user_id = ?", (telegram_user_id,))
            row = self.cursor.fetchone()
            return row[0] if row else None
