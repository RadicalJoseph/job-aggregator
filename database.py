import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "jobs.db")

def ensure_data_directory() -> None:
    """Ensure the local runtime data directory exists."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

def get_connection() -> sqlite3.Connection:
    """Establish and return a database connection."""
    ensure_data_directory()
    return sqlite3.connect(DB_PATH)

def init_db() -> None:
    """Initialize the SQLite schema if it does not already exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT,
                discovered_at TIMESTAMP NOT NULL
            )
        """)
        conn.commit()

def is_job_recorded(url: str) -> bool:
    """Check whether a job URL already exists in the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
        return cursor.fetchone() is not None

def record_job(url: str, title: str, company: str, source: str, location: Optional[str] = None) -> bool:
    """Insert a newly discovered job record."""
    if is_job_recorded(url):
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (url, title, company, source, location, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (url, title, company, source, location or "Unspecified", datetime.now().isoformat()))
        conn.commit()
    return True

def get_recent_jobs(limit: int = 50) -> List[Tuple[str, str, str, str, str, str]]:
    """Retrieve recent records for inspection."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, company, source, location, discovered_at FROM jobs ORDER BY discovered_at DESC LIMIT ?", (limit,))
        return cursor.fetchall()