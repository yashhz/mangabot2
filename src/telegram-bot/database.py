
import sqlite3
import os
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class Manhwa:
    id: int
    name: str
    url: str
    site_name: str
    last_chapter_url: str
    last_chapter_name: str
    created_at: str
    updated_at: str

class ManhwaDB:
    def __init__(self, db_path: str = "data/manhwa.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_tables()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_tables(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS manhwa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    site_name TEXT NOT NULL,
                    last_chapter_url TEXT DEFAULT '',
                    last_chapter_name TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE,
                    output_channel_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    base_url TEXT NOT NULL,
                    parser_class_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # Insert default supported sites
            sites = [
                ('manhwaclan', 'https://manhwaclan.com', 'ManhwaClanScraper'),
                ('asurascans', 'https://asurascans.com', 'AsuraScansScraper'),
                ('flamescans', 'https://flamescans.org', 'FlameScansScraper')
            ]
            
            for site_name, base_url, parser_class in sites:
                conn.execute("""
                    INSERT OR IGNORE INTO sites (name, base_url, parser_class_name)
                    VALUES (?, ?, ?)
                """, (site_name, base_url, parser_class))
            
            conn.commit()
    
    def add_manhwa(self, name: str, url: str, site_name: str, 
                   last_chapter_url: str = '', last_chapter_name: str = '') -> bool:
        """Add a new manhwa to tracking"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO manhwa (name, url, site_name, last_chapter_url, last_chapter_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, url, site_name, last_chapter_url, last_chapter_name))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Manhwa already exists
    
    def get_all_manhwa(self) -> List[Manhwa]:
        """Get all tracked manhwa"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, url, site_name, last_chapter_url, 
                       last_chapter_name, created_at, updated_at
                FROM manhwa ORDER BY name
            """)
            rows = cursor.fetchall()
            
            return [Manhwa(*row) for row in rows]
    
    def get_manhwa_by_name(self, name: str) -> Optional[Manhwa]:
        """Get manhwa by name"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, url, site_name, last_chapter_url,
                       last_chapter_name, created_at, updated_at
                FROM manhwa WHERE name = ?
            """, (name,))
            row = cursor.fetchone()
            
            return Manhwa(*row) if row else None
    
    def update_manhwa_progress(self, name: str, last_chapter_url: str, 
                              last_chapter_name: str) -> bool:
        """Update manhwa progress"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE manhwa 
                    SET last_chapter_url = ?, last_chapter_name = ?, 
                        updated_at = CURRENT_TIMESTAMP
                    WHERE name = ?
                """, (last_chapter_url, last_chapter_name, name))
                conn.commit()
            return True
        except Exception:
            return False
    
    def remove_manhwa(self, name: str) -> bool:
        """Remove manhwa from tracking"""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM manhwa WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_supported_sites(self) -> List[tuple]:
        """Get all supported sites"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name, base_url, parser_class_name 
                FROM sites WHERE is_active = TRUE
            """)
            return cursor.fetchall()

def init_db():
    """Initialize the database"""
    db = ManhwaDB()
    return db
