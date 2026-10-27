"""SQLite FTS5 keyword index (stage C, task T10-006).

§9 #1 provisional default: FTS5-only MVP; vector search explicitly deferred
(plan.md scope-cut order removes vector search before automatic PDF
parsing, so vectors must not sit on the critical path). Every index row
carries source_version_id, segment_id, heading path and page range so each
retrieval result can show the exact German passage beside its metadata
(architecture.md §5). The index is a rebuildable cache — deleting
``data/index/`` and rebuilding must yield equivalent results (hook §8.6).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS segments USING fts5(
    text,
    title,
    heading_path,
    source_version_id UNINDEXED,
    segment_id UNINDEXED,
    heading_level UNINDEXED,
    page_start UNINDEXED,
    page_end UNINDEXED
);
"""


def open_db(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (or create) the index; pass None for an in-memory database (tests)."""
    conn = sqlite3.connect(str(path) if path else ":memory:")
    conn.executescript(FTS_DDL)
    return conn


def insert_segment(conn: sqlite3.Connection, segment) -> None:
    """Insert one segment row (usable by the builder and by tests)."""
    conn.execute(
        "INSERT INTO segments (text, title, heading_path, source_version_id, "
        "segment_id, heading_level, page_start, page_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            segment.text,
            segment.title,
            " > ".join(segment.heading_path),
            segment.source_version_id,
            segment.segment_id,
            segment.heading_level,
            segment.page_start,
            segment.page_end,
        ),
    )


def build_index(sources_root: Path, db_path: Path, task_id: str = "T10-006") -> dict:
    """Build the index from SEGMENTED, G0-accepted source versions only.

    Contract (ingestion-pipeline.md §7): a version with G0 status other than
    ``accepted`` contributes zero rows (gate filtering, hook §8.4); the run
    writes an AuditRecord (tool version, input checksums, counts, warnings).
    Segments are read from ``segments.jsonl`` inside each accepted version
    folder (written by the segmenter stage).
    """
    from ..audit import AuditRecord, append_jsonl
    from ..segmenter.models import load_segments_jsonl
    from ..registry.manifest import Manifest, manifest_path

    sources_root = Path(sources_root)
    conn = open_db(db_path)
    counts = {"versions_seen": 0, "versions_accepted": 0, "rows": 0}
    warnings: list[str] = []
    input_ids: list[str] = []
    input_checksums: dict[str, str] = {}

    for manifest_file in sorted(sources_root.glob("SRC-*/SRCV-*/manifest.json")):
        manifest = Manifest.from_json(manifest_file)
        counts["versions_seen"] += 1
        input_ids.append(manifest.source_id)
        input_checksums[manifest.source_id] = manifest.checksum
        if manifest.status != "accepted":
            warnings.append(
                f"{manifest.source_id}: status {manifest.status!r} — zero index rows "
                "(gate filtering §8.4: only G0-accepted versions enter retrieval)")
            continue
        segments_file = manifest_file.parent / "segments.jsonl"
        if not segments_file.exists():
            warnings.append(f"{manifest.source_id}: accepted but no segments.jsonl — nothing indexed")
            continue
        counts["versions_accepted"] += 1
        for segment in load_segments_jsonl(segments_file):
            insert_segment(conn, segment)
            counts["rows"] += 1
    conn.commit()
    conn.close()

    record = AuditRecord(
        run_id=f"INDEX-{task_id}-{counts['rows']}-{len(input_ids)}",
        task_id=task_id,
        role="index_builder",
        tool="pipeline.index.fts/0.2.0",
        input_ids=input_ids,
        input_checksums=input_checksums,
        counts=counts,
        warnings=warnings,
        status="candidate",
        notes="rebuildable cache: deleting the db file and rebuilding yields equivalent rows",
    )
    append_jsonl(sources_root / "audit.jsonl", record.to_dict())
    return record.to_dict()
