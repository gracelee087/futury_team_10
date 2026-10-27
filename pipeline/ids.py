"""Stable identifiers and content checksums shared by all pipeline stages.

ID scheme [PROVISIONAL — ingestion-pipeline.md §4/§6; confirm at review]:

  SRC-<n>              one logical source (a law, specification, or form)
  SRCV-<n>-<L>         one immutable version folder under data/sources/SRC-<n>/,
                       letters assigned in intake order (A, B, C, ...)
  SEG-<srcv_id>-<seq>  segment within a version, ordered by (page_start,
                       heading_path) so IDs stay stable for a given version

Identifiers are assigned once at registration and never reused or renumbered;
supersession is recorded on the manifest, never by mutating IDs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def new_id(prefix: str, seq: int, suffix: str | None = None) -> str:
    """Build an ID like ``SRC-12`` or ``SRCV-12-A`` from a 1-based sequence number."""
    if seq < 1:
        raise ValueError("sequence numbers are 1-based")
    base = f"{prefix}-{seq}"
    return f"{base}-{suffix}" if suffix else base


def next_seq(existing: list[str], prefix: str) -> int:
    """Next free 1-based sequence number for ``prefix``.

    >>> next_seq(["SRC-1", "SRC-3"], "SRC")
    4
    >>> next_seq([], "SRC")
    1
    """
    marker = f"{prefix}-"
    numbers = []
    for item in existing:
        if not item.startswith(marker):
            continue  # "SRCV-1-A" does not collide with prefix "SRC-"
        rest = item[len(marker):]
        head = rest.split("-", 1)[0]
        if head.isdigit():
            numbers.append(int(head))
    return max(numbers, default=0) + 1


def checksum_bytes(data: bytes) -> str:
    """SHA-256 hex digest of a byte string (dedupe key for intake, ingestion-pipeline.md §5)."""
    return hashlib.sha256(data).hexdigest()


def checksum_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file, streamed in 1 MiB blocks (originals are never loaded whole)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
