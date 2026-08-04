# database.py
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "jobs.db")

def get_connection() -> sqlite3.Connection:
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    return sqlite3.connect(DB_PATH)

def init_db() -> None:
    """Initialize schema with status tracking and metadata fields."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
        conn.commit()

def upsert_job(url: str, title: str, company: str, source: str, location: str, salary: str) -> bool:
    """
    Inserts a new job or updates the last_seen_at timestamp if it already exists.
    Returns True if this is a brand new discovery.
    """
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM jobs WHERE url = ?", (url,))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Update last_seen_at and reset status to ACTIVE if it was previously marked REMOVED
            cursor.execute("""
                UPDATE jobs 
                SET last_seen_at = ?, status = 'ACTIVE' 
                WHERE url = ?
            """, (now, url))
            conn.commit()
            return False
        else:
            # Insert brand new record
            cursor.execute("""
                INSERT INTO jobs (url, title, company, source, location, salary, status, discovered_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
            """, (url, title, company, source, location, salary, now, now))
            conn.commit()
            return True

def reconcile_missing_jobs(active_urls_in_run: set, source_name: str, lookback_days: int = 14) -> List[Dict[str, Any]]:
    """
    Compares URLs seen in the current run against ACTIVE jobs in the DB for a specific source.
    Marks jobs as REMOVED if they weren't seen in this run, returning the newly removed jobs.
    """
    now = datetime.now()
    cutoff = (now - timedelta(days=lookback_days)).isoformat()
    newly_removed = []

    with get_connection() as conn:
        cursor = conn.cursor()
        # Find active jobs from this source discovered within the lookback window
        cursor.execute("""
            SELECT url, title, company, salary FROM jobs 
            WHERE source = ? AND status = 'ACTIVE' AND discovered_at >= ?
        """, (source_name, cutoff))
        
        for url, title, company, salary in cursor.fetchall():
            if url not in active_urls_in_run:
                # Mark as removed
                cursor.execute("UPDATE jobs SET status = 'REMOVED' WHERE url = ?", (url,))
                newly_removed.append({"url": url, "title": title, "company": company, "salary": salary})
        
        conn.commit()
    return newly_removed