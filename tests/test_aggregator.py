import os
import shutil
import sqlite3
import tempfile
import unittest

import aggregator
import database


class MatchesTargetRoleTests(unittest.TestCase):
    def test_matches_broader_role_titles(self):
        self.assertTrue(aggregator.matches_target_role("Director of Technology Services and Projects"))
        self.assertTrue(aggregator.matches_target_role("AI Enablement Lead"))
        self.assertTrue(aggregator.matches_target_role("Senior Manager Science Data & Knowledge Mgmt"))
        self.assertTrue(aggregator.matches_target_role("Sr. Tech Specialist"))


class PostedDateExtractionTests(unittest.TestCase):
    def test_extract_posted_at_recurses_through_nested_payloads(self):
        payload = {
            "job": {
                "meta": {
                    "publishedAt": "2026-07-03T12:25:05.315+00:00"
                }
            }
        }
        self.assertEqual(aggregator.extract_posted_at(payload), "2026-07-03T12:25:05.315+00:00")


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_db_dir = database.DB_DIR
        self.original_db_path = database.DB_PATH
        database.DB_DIR = self.temp_dir
        database.DB_PATH = os.path.join(self.temp_dir, "jobs.db")

    def tearDown(self):
        database.DB_DIR = self.original_db_dir
        database.DB_PATH = self.original_db_path
        try:
            if os.path.exists(os.path.join(self.temp_dir, "jobs.db")):
                os.remove(os.path.join(self.temp_dir, "jobs.db"))
            os.rmdir(self.temp_dir)
        except OSError:
            pass

    def test_init_db_adds_posted_at_column_to_existing_jobs_table(self):
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute("""
            CREATE TABLE jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT,
                salary TEXT,
                status TEXT DEFAULT 'New',
                discovered_at TIMESTAMP NOT NULL
            )
            """)
            conn.commit()

        database.init_db()

        with sqlite3.connect(database.DB_PATH) as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
            self.assertIn("posted_at", columns)

    def test_init_db_deduplicates_existing_rows_by_url(self):
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute("""
            CREATE TABLE jobs (
                url TEXT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT,
                salary TEXT,
                status TEXT DEFAULT 'New',
                discovered_at TIMESTAMP NOT NULL
            )
            """)
            conn.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                "https://example.com/job",
                "Duplicate A",
                "Acme",
                "Source",
                "Remote",
                "Unspecified",
                "New",
                "2026-01-01T00:00:00",
            ))
            conn.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                "https://example.com/job",
                "Duplicate B",
                "Acme",
                "Source",
                "Remote",
                "Unspecified",
                "New",
                "2026-01-02T00:00:00",
            ))
            conn.commit()

        database.init_db()

        with sqlite3.connect(database.DB_PATH) as conn:
            rows = conn.execute("SELECT title FROM jobs WHERE url = ?", ("https://example.com/job",)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertTrue(any("Duplicate" in row[0] for row in rows))
            indexes = conn.execute("PRAGMA index_list(jobs)").fetchall()
            self.assertTrue(any(index[1] == "idx_jobs_url" for index in indexes))

    def test_record_job_updates_existing_row_posted_at(self):
        database.init_db()
        inserted = database.record_job(
            url="https://example.com/job",
            title="Existing job",
            company="Acme",
            source="Source",
            location="Remote",
            salary="Unspecified",
            posted_at=None,
        )
        self.assertTrue(inserted)

        updated = database.record_job(
            url="https://example.com/job",
            title="Existing job",
            company="Acme",
            source="Source",
            location="Remote",
            salary="Unspecified",
            posted_at="2026-08-05T12:00:00Z",
        )
        self.assertFalse(updated)

        with sqlite3.connect(database.DB_PATH) as conn:
            posted_at = conn.execute("SELECT posted_at FROM jobs WHERE url = ?", ("https://example.com/job",)).fetchone()[0]
            self.assertEqual(posted_at, "2026-08-05T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
