"""Source-version manifest: architecture.md §4 fields, G0 status vocabulary.

Rules (ingestion-pipeline.md §5):

  - every version enters with status ``candidate``; only a human moves it to
    ``accepted`` (gate G0, see pipeline.registry.g0) — fetch is not accept;
  - filename-derived values (V13.1, gueltig_ab_...) are candidate metadata,
    never verified facts;
  - unknown fields stay empty rather than guessed;
  - publication date and effective date are kept separate.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

STATUS_CANDIDATE = "candidate"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"
STATUSES = (STATUS_CANDIDATE, STATUS_ACCEPTED, STATUS_REJECTED, STATUS_SUPERSEDED)

# architecture.md §4 source fields (registry-internal additions appended).
FIELD_ORDER = (
    "source_id",
    "title",
    "issuing_body",
    "source_type",
    "official_uri_or_origin",
    "retrieved_at",
    "published_or_issued_at",
    "edition_or_version",
    "valid_from",
    "valid_to",
    "language",
    "checksum",
    "supersedes",
    "status",
    "reviewer",
    "notes",
    # registry-internal:
    "intake_paths",
)

SOURCE_TYPES = ("law", "itsg_spec", "form_template", "vendor_doc", "execution_output", "other")


@dataclass
class Manifest:
    """One immutable source version (data/sources/SRC-<n>/SRCV-<n>-<L>/manifest.json)."""

    source_id: str
    title: str = ""
    issuing_body: str = ""
    source_type: str = ""
    official_uri_or_origin: str = ""
    retrieved_at: str = ""
    published_or_issued_at: str = ""
    edition_or_version: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    language: str = "de"
    checksum: str = ""
    supersedes: str | None = None
    status: str = STATUS_CANDIDATE
    reviewer: str | None = None
    notes: str = ""
    intake_paths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown manifest status: {self.status!r}")
        if self.source_type and self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {self.source_type!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        """Build from a dict; unknown keys are rejected at the boundary (agent-governance.md §3)."""
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown manifest fields: {unknown}")
        return cls(**data)

    @classmethod
    def from_json(cls, path: str | Path) -> "Manifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def parse_srcv_id(srcv_id: str) -> tuple[int, str]:
    """``SRCV-12-A`` -> (12, "A"). Raises ValueError on malformed IDs."""
    parts = srcv_id.split("-")
    if len(parts) != 3 or parts[0] != "SRCV" or not parts[1].isdigit() or not parts[2].isalpha():
        raise ValueError(f"malformed SRCV id: {srcv_id!r}")
    return int(parts[1]), parts[2]


def srcv_dir(sources_root: str | Path, srcv_id: str) -> Path:
    """Version folder for a SRCV id: data/sources/SRC-12/SRCV-12-A/."""
    seq, _suffix = parse_srcv_id(srcv_id)
    return Path(sources_root) / f"SRC-{seq}" / srcv_id


def manifest_path(sources_root: str | Path, srcv_id: str) -> Path:
    return srcv_dir(sources_root, srcv_id) / "manifest.json"
