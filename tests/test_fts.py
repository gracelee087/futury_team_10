"""Tests for the FTS5 index skeleton (pipeline.index.fts + query) — runs on stdlib sqlite3."""
from __future__ import annotations

import unittest

from pipeline.index.fts import FTS_DDL, insert_segment, open_db
from pipeline.index.query import search
from pipeline.segmenter.models import Segment


def segment(seg_id: str, srcv: str, text: str, title: str = "Mitteilungsverfahren") -> Segment:
    return Segment(
        segment_id=seg_id,
        source_version_id=srcv,
        heading_level=2,
        heading_path=["2", "2.1"],
        title=title,
        page_start=7,
        page_end=7,
        text=text,
    )


class TestFtsIndex(unittest.TestCase):
    def setUp(self):
        self.conn = open_db(None)  # in-memory; also proves FTS5 is available
        insert_segment(self.conn, segment("SEG-1", "SRCV-1-A", "Das Mitteilungsverfahren beginnt mit der Anmeldung."))
        insert_segment(self.conn, segment("SEG-2", "SRCV-1-A", "Anrechenbare Vorerkrankungen sind nach §2.1.3 zu prüfen."))
        insert_segment(self.conn, segment("SEG-3", "SRCV-2-A", "Fremdtext, der nie geliefert werden darf."))
        self.conn.commit()

    def test_search_finds_german_terms(self):
        # "Anmeldung" occurs only in SEG-1's text (the shared section title is
        # deliberately not used as the probe term).
        results = search(self.conn, "Anmeldung", accepted_versions={"SRCV-1-A"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].segment_id, "SEG-1")
        self.assertEqual(results[0].source_version_id, "SRCV-1-A")
        self.assertEqual(results[0].heading_path, "2 > 2.1")

    def test_gate_filtering_accepted_only(self):
        # SRCV-2-A is not accepted: its rows are never served (hook §8.4 semantics)
        results = search(self.conn, "Fremdtext", accepted_versions={"SRCV-1-A"})
        self.assertEqual(results, [])

    def test_empty_accepted_set_fails_closed(self):
        self.assertEqual(search(self.conn, "Mitteilungsverfahren", accepted_versions=set()), [])

    def test_empty_query_returns_nothing(self):
        self.assertEqual(search(self.conn, "   ", accepted_versions={"SRCV-1-A"}), [])

    def test_malformed_query_raises_not_silently(self):
        with self.assertRaises(ValueError):
            search(self.conn, "(", accepted_versions={"SRCV-1-A"})

    def test_schema_declares_all_citation_columns(self):
        for column in ("source_version_id", "segment_id", "heading_path", "page_start", "page_end"):
            self.assertIn(column, FTS_DDL)


if __name__ == "__main__":
    unittest.main()
