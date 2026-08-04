# database.py
import sqlite3
import os
from datetime import datetime, timedelta

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "jobs.db")

def get_connection() -> sqlite3.Connection:
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    return sqlite3.connect(DB_PATH)

def init_db() -> None:
    """Initialize schema with status tracking for the 2-week lookback."""
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            source TEXT NOT NULL,
            location TEXT,
            salary TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            discovered_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NOT NULL
        )
        """)

def upsert_job(url: str, title: str, company: str, source: str, location: str, salary: str) -> bool:
    """Inserts a new job or updates last_seen_at. Returns True if brand new."""
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM jobs WHERE url = ?", (url,))
        exists = cursor.fetchone() is not None
        
        if exists:
            cursor.execute("UPDATE jobs SET last_seen_at = ?, status = 'ACTIVE' WHERE url = ?", (now, url))
            return False
        else:
            cursor.execute("""
                INSERT INTO jobs (url, title, company, source, location, salary, status, discovered_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
            """, (url, title, company, source, location, salary, now, now))
            return True

def reconcile_missing_jobs(active_urls: set, source_name: str, lookback_days: int = 14) -> list:
    """Marks jobs as REMOVED if they disappeared from the live boards, enabling takedown alerts."""
    now = datetime.now()
    cutoff = (now - timedelta(days=lookback_days)).isoformat()
    newly_removed = []

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT url, title, company FROM jobs 
            WHERE source = ? AND status = 'ACTIVE' AND discovered_at >= ?
        """, (source_name, cutoff))
        
        for url, title, company in cursor.fetchall():
            if url not in active_urls:
                cursor.execute("UPDATE jobs SET status = 'REMOVED' WHERE url = ?", (url,))
                newly_removed.append(f"{title} at {company}")
    return newly_removed