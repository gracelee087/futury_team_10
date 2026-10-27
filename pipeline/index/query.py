"""Retrieval over the FTS index (task T10-006).

Contract: only G0-accepted source versions are served (architecture.md §7
gate G0; ingestion-pipeline.md §7). Fails closed — an empty accepted set or
an empty query returns no rows, and a malformed query raises instead of
silently widening the result set.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class SearchResult:
    source_version_id: str
    segment_id: str
    heading_path: str
    heading_level: int
    page_start: int
    page_end: int
    title: str
    text: str
    score: float


_COLUMNS = (
    "text, title, heading_path, source_version_id, segment_id, "
    "heading_level, page_start, page_end, rank"
)


def search(
    conn: sqlite3.Connection,
    query: str,
    accepted_versions: set[str],
    limit: int = 10,
) -> list[SearchResult]:
    """FTS5 MATCH restricted to G0-accepted source versions."""
    if not query.strip():
        return []
    if not accepted_versions:
        return []  # fail closed: nothing is accepted -> nothing is served
    placeholders = ",".join("?" for _ in accepted_versions)
    sql = (
        f"SELECT {_COLUMNS} FROM segments "
        f"WHERE segments MATCH ? AND source_version_id IN ({placeholders}) "
        f"ORDER BY rank LIMIT ?"
    )
    try:
        rows = conn.execute(sql, (query, *sorted(accepted_versions), limit)).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"invalid FTS query {query!r}") from exc
    return [
        SearchResult(
            text=row[0],
            title=row[1],
            heading_path=row[2],
            source_version_id=row[3],
            segment_id=row[4],
            heading_level=row[5],
            page_start=row[6],
            page_end=row[7],
            score=row[8],
        )
        for row in rows
    ]
