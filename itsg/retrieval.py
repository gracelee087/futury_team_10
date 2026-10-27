"""Corpus retrieval wrapper for the SÜSIE assistant (task 2, susie-assistant track).

A thin, read-only layer over the existing T10-006 index:
``pipeline.index.query.search`` supplies the FTS5 lookup; ``itsg.store.Store``
supplies the G0 gate state (source records with ``status == "approved"`` are
served, nothing else).

Honest degradation (fail closed, never fabricate): a missing or unreadable
index file, an invalid FTS query or an empty accepted set all yield ``[]`` —
the assistant layer reports "nothing found" rather than raising or widening
the result set. No index building happens here (T10-006 owns that); this
module only reads.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from pipeline.index.query import search as _fts_search

from .store import Store

HIT_KEYS = (
    "source_version_id",
    "segment_id",
    "heading_path",
    "title",
    "text",
    "page_start",
    "page_end",
)


def accepted_version_ids(store_root: Path) -> set[str]:
    """Ids of source records the G0 gate has approved (``status == "approved"``)."""
    return {
        record["id"]
        for record in Store(store_root).all("source")
        if record.get("status") == "approved" and record.get("id")
    }


def corpus_search(
    store_root: Path,
    index_path: Path,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Search the FTS index, restricted to G0-approved source versions.

    Returns one dict per hit with exactly the citation keys in ``HIT_KEYS``,
    best match first. Any failure mode degrades to ``[]``: missing index
    file, unreadable/corrupt database, invalid FTS query or empty accepted
    set.
    """
    accepted = accepted_version_ids(store_root)
    if not accepted or not index_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(index_path))
    except sqlite3.Error:
        return []
    try:
        results = _fts_search(conn, query, accepted, limit)
    except (sqlite3.Error, ValueError):
        return []  # invalid FTS query or unreadable db: nothing to serve
    finally:
        conn.close()
    return [{key: getattr(result, key) for key in HIT_KEYS} for result in results]
