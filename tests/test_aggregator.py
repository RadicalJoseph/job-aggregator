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


if __name__ == "__main__":
    unittest.main()
