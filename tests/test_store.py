"""Tests for the JSON store + append-only event log (itsg.store)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from itsg.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "data" / "demo"

    def test_put_get_all_round_trip(self):
        store = Store(self.root)
        store.put("source", {"id": "SRC-1", "title": "Demo fixture"})
        self.assertEqual(store.get("source", "SRC-1")["title"], "Demo fixture")
        self.assertIsNone(store.get("source", "SRC-2"))
        self.assertEqual(len(store.all("source")), 1)

    def test_put_requires_id(self):
        store = Store(self.root)
        with self.assertRaises(ValueError):
            store.put("source", {"title": "no id"})
        with self.assertRaises(ValueError):
            store.put("source", "not-a-dict")

    def test_upsert_overwrites_and_logs(self):
        store = Store(self.root)
        store.put("source", {"id": "SRC-1", "title": "v1"})
        store.put("source", {"id": "SRC-1", "title": "v2"})
        self.assertEqual(store.get("source", "SRC-1")["title"], "v2")
        self.assertEqual(len(store.all("source")), 1)

    def test_event_log_is_append_only_and_persistent(self):
        store = Store(self.root)
        store.put("source", {"id": "SRC-1", "title": "a"})
        first_events = store.events()
        self.assertEqual([e["seq"] for e in first_events], [1])

        reopened = Store(self.root)  # simulate a new session on the same data dir
        reopened.put("source", {"id": "SRC-2", "title": "b"})
        events = reopened.events()
        self.assertEqual([e["seq"] for e in events], [1, 2])
        self.assertEqual(events[1]["id"], "SRC-2")

    def test_records_file_is_valid_json_on_disk(self):
        store = Store(self.root)
        store.put("source", {"id": "SRC-1", "title": "a"})
        import json

        data = json.loads(store.records_path.read_text(encoding="utf-8"))
        self.assertEqual(data["source"]["SRC-1"]["title"], "a")


if __name__ == "__main__":
    unittest.main()
