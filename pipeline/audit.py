"""Append-only audit records, adapted from agent-governance.md §3.

Every import, segmentation run, and index build writes one JSONL record per
run: tool version, input IDs/checksums, counts, warnings, status. Records
are never rewritten; corrections are new records (governance: append-only).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AuditRecord:
    run_id: str
    task_id: str
    role: str  # "source_intake" | "segmenter" | "index_builder" | ...
    tool: str  # e.g. "pipeline.registry/0.1.0"
    started_at: str = field(default_factory=utc_now)
    input_ids: list[str] = field(default_factory=list)
    input_checksums: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    status: str = "candidate"  # candidate | needs_review | blocked | error
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def append_jsonl(path: str | Path, record: dict) -> None:
    """Append one JSON object as a line, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file back into a list of dicts."""
    records: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
