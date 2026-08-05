# database.py
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
    """Initialize the SQLite schema with salary and status tracking."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            source TEXT NOT NULL,
            location TEXT,
            salary TEXT,
            posted_at TEXT,
            status TEXT DEFAULT 'New',
            discovered_at TIMESTAMP NOT NULL
        )
        """)
        conn.commit()

        columns = [row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()]
        if "posted_at" not in columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")
            conn.commit()
    finally:
        conn.close()

def is_job_recorded(url: str) -> bool:
    """Check whether a job URL already exists in the database."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM jobs WHERE url = ?", (url,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def record_job(
    url: str,
    title: str,
    company: str,
    source: str,
    location: Optional[str] = None,
    salary: Optional[str] = None,
    posted_at: Optional[str] = None,
) -> bool:
    """Insert a newly discovered job record."""
    if is_job_recorded(url):
        return False

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO jobs (url, title, company, source, location, salary, posted_at, status, discovered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'New', ?)
        """, (
            url,
            title,
            company,
            source,
            location or "Unspecified",
            salary or "Unspecified",
            posted_at or "Unspecified",
            datetime.now().isoformat(),
        ))
        conn.commit()
    finally:
        conn.close()
    return True

def update_job_status(url: str, status: str) -> None:
    """Update the processing status of a specific job."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = ? WHERE url = ?", (status, url))
        conn.commit()
    finally:
        conn.close()

def get_recent_jobs(limit: int = 200) -> List[Tuple]:
    """Retrieve recent records including their current status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT title, company, source, location, salary, posted_at, discovered_at, url, status 
        FROM jobs 
        ORDER BY discovered_at DESC 
        LIMIT ?
        """, (limit,))
        return cursor.fetchall()