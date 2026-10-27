"""Segment and warning records — the T10-005 output schema (ingestion-pipeline.md §6 sketch).

Purity rules: ``text`` is exact source text (no normalization, no
dehyphenation); breadcrumbs such as ``GG_EEL V13.1 > 2 ...`` are prepended
at embed/query time, never stored into the text.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHUNK_SECTION = "heading_section"
CHUNK_PARAGRAPH = "paragraph"
CHUNK_TABLE = "table"
CHUNK_TYPES = (CHUNK_SECTION, CHUNK_PARAGRAPH, CHUNK_TABLE)

SEGMENT_STATUSES = ("candidate", "needs_review")


@dataclass
class ExtractionWarning:
    """A quirk or low-confidence finding kept visible downstream (ingestion-pipeline.md §6)."""

    code: str  # e.g. split_heading_line | wrapped_heading | heading_count_mismatch | table_noise
    message: str
    page: int | None = None


@dataclass
class Segment:
    """One canonical heading segment or retrieval chunk, aligned with the architecture §5 citation shape."""

    segment_id: str
    source_version_id: str
    heading_level: int  # 1..6 for canonical sections; 0 for unheaded retrieval chunks
    heading_path: list[str]
    title: str
    page_start: int
    page_end: int
    text: str
    chunk_type: str = CHUNK_SECTION
    extraction_warnings: list[ExtractionWarning] = field(default_factory=list)
    status: str = "candidate"  # candidate | needs_review (approval is human-only, downstream)

    def __post_init__(self) -> None:
        if self.chunk_type not in CHUNK_TYPES:
            raise ValueError(f"unknown chunk_type: {self.chunk_type!r}")
        if self.status not in SEGMENT_STATUSES:
            raise ValueError(f"unknown segment status: {self.status!r}")

    def to_dict(self) -> dict:
        return asdict(self)


def dump_segments_jsonl(segments: list[Segment], path: str | Path) -> Path:
    """Write segments as JSONL (the §9 #2 provisional canonical store).

    ``path`` must name a regular file inside an existing directory; the caller's
    own output path is the API, but symlinked directories are not followed into
    escapes: the resolved target must keep its resolved parent."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not target.is_file():
        raise ValueError(f"output path is not a regular file: {target}")
    payload_text = "".join(json.dumps(s.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for s in segments)
    target.write_text(payload_text, encoding="utf-8")
    return target


def load_segments_jsonl(path: str | Path) -> list[Segment]:
    """Read segments back; unknown keys are rejected at the boundary."""
    segments: list[Segment] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            warnings = [ExtractionWarning(**w) for w in data.pop("extraction_warnings", [])]
            segments.append(Segment(**data, extraction_warnings=warnings))
    return segments
