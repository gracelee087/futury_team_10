"""Tests for the SÜSIE assistant corpus retrieval wrapper (itsg.retrieval).

Contract under test: only G0-approved source versions are served, and every
failure mode (missing index file, unreadable db, invalid FTS query, empty
accepted set) degrades to ``[]`` instead of raising — the assistant layer
must never fabricate retrieval results.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from itsg import retrieval
from itsg.store import Store
from pipeline.index.fts import insert_segment, open_db
from pipeline.segmenter.models import Segment


def segment(seg_id: str, srcv: str, text: str) -> Segment:
    return Segment(
        segment_id=seg_id,
        source_version_id=srcv,
        heading_level=2,
        heading_path=["2", "2.1"],
        title="Fehlzeiten des Arbeitnehmers",
        page_start=7,
        page_end=8,
        text=text,
    )


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)

        # store root: one approved source SRC-BP, one needs_review SRC-X
        self.store = tmp / "store"
        store = Store(self.store)
        store.put("source", {"id": "SRC-BP", "status": "approved"})
        store.put("source", {"id": "SRC-X", "status": "needs_review"})

        # an empty store (no source records at all)
        self.empty_store = tmp / "store-empty"

        # index db on disk with one segment per version
        self.index = tmp / "index.sqlite"
        conn = open_db(self.index)
        insert_segment(conn, segment("SEG-BP", "SRC-BP", "Der Arbeitnehmer meldet eine Fehlzeit rechtzeitig."))
        insert_segment(conn, segment("SEG-X", "SRC-X", "Fehlzeit-Fremdtext, der nie geliefert werden darf."))
        conn.commit()
        conn.close()

    def test_only_accepted_versions_are_served(self):
        hits = retrieval.corpus_search(self.store, self.index, "Fehlzeit")
        self.assertEqual([h["source_version_id"] for h in hits], ["SRC-BP"])

    def test_hit_carries_citation_fields(self):
        hits = retrieval.corpus_search(self.store, self.index, "Fehlzeit")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(
            sorted(hit),
            sorted(
                [
                    "source_version_id",
                    "segment_id",
                    "heading_path",
                    "title",
                    "text",
                    "page_start",
                    "page_end",
                ]
            ),
        )
        self.assertEqual(hit["segment_id"], "SEG-BP")
        self.assertEqual(hit["page_start"], 7)
        self.assertEqual(hit["page_end"], 8)
        self.assertIn("Fehlzeit", hit["text"])

    def test_missing_index_degrades_to_empty(self):
        self.assertEqual(retrieval.corpus_search(self.store, Path(self._tmp.name) / "nope.sqlite", "Fehlzeit"), [])

    def test_no_accepted_versions_returns_empty(self):
        self.assertEqual(retrieval.corpus_search(self.empty_store, self.index, "Fehlzeit"), [])

    def test_invalid_query_returns_empty_not_error(self):
        self.assertEqual(retrieval.corpus_search(self.store, self.index, '"unbalanced'), [])

    def test_accepted_version_ids_reads_store(self):
        self.assertEqual(retrieval.accepted_version_ids(self.store), {"SRC-BP"})
        self.assertEqual(retrieval.accepted_version_ids(self.empty_store), set())


if __name__ == "__main__":
    unittest.main()
