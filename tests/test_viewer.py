import unittest
from unittest.mock import patch
import tkinter as tk
import viewer


class FakeTextWidget:
    def config(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass

    def insert(self, *args, **kwargs):
        pass


class FakeTree:
    def __init__(self):
        self._rows = []
        self._children = []
        self.columns = ["Title", "Company", "Source", "Location", "Salary", "Posted", "Discovered", "URL", "Applied", "Ignored", "Rejected"]

    def get_children(self, _=""):
        return list(self._children)

    def delete(self, child):
        self._children.remove(child)
        self._rows = [row for row in self._rows if row[0] != child]

    def insert(self, parent, index, values):
        child_id = f"id{len(self._children) + 1}"
        self._children.append(child_id)
        self._rows.append((child_id, values))

    def set(self, child, col):
        for row_id, values in self._rows:
            if row_id == child:
                return values[self.columns.index(col)]
        return ""

    def move(self, child, parent, index):
        current = next(row for row in self._rows if row[0] == child)
        self._rows.remove(current)
        self._rows.insert(index, current)
        self._children = [row[0] for row in self._rows]

    def heading(self, *args, **kwargs):
        pass


class ViewerRefreshTests(unittest.TestCase):
    def test_refresh_applies_existing_sort_state(self):
        fake_tree = FakeTree()
        fake_text = FakeTextWidget()
        jobs = [
            ("Beta Role", "BetaCo", "Ashby", "Remote", "$100k", "2024-01-02", "2024-01-02 10:00", "https://example.com/beta", "New"),
            ("Alpha Role", "AlphaCo", "Ashby", "Remote", "$90k", "2024-01-01", "2024-01-01 09:00", "https://example.com/alpha", "New"),
        ]

        with patch("viewer.database.get_recent_jobs", return_value=jobs), patch("viewer.read_log_file", return_value=""):
            viewer.refresh_data(fake_tree, fake_text, filter_text=None, sort_state={"column": "Title", "reverse": False})

        self.assertEqual([row[1][0] for row in fake_tree._rows], ["Alpha Role", "Beta Role"])


if __name__ == "__main__":
    unittest.main()
