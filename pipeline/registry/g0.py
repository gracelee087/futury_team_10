"""Gate G0 — source intake acceptance. Human-only (architecture.md §7).

An agent may not accept, reject, or supersede a source version. These
functions require a non-empty human reviewer identity and a recorded
rationale and fail closed otherwise; both are written onto the manifest,
which is the G0 evidence record (reviewer, decision, rationale, version).
"""
from __future__ import annotations

from .manifest import (
    STATUS_ACCEPTED,
    STATUS_CANDIDATE,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    Manifest,
)


def _require_human(reviewer: str | None, rationale: str) -> None:
    if not reviewer or not reviewer.strip():
        raise ValueError("gate G0 requires a named human reviewer")
    if not rationale or not rationale.strip():
        raise ValueError("gate G0 requires a recorded rationale")


def _append_note(notes: str, line: str) -> str:
    return f"{notes}\n{line}".strip() if notes else line


def accept(manifest: Manifest, reviewer: str, rationale: str) -> Manifest:
    """Human acceptance: candidate -> accepted. The version may then enter retrieval."""
    _require_human(reviewer, rationale)
    if manifest.status != STATUS_CANDIDATE:
        raise ValueError(f"only candidate versions can be accepted, got {manifest.status!r}")
    manifest.status = STATUS_ACCEPTED
    manifest.reviewer = reviewer
    manifest.notes = _append_note(manifest.notes, f"G0 accepted by {reviewer}: {rationale}")
    return manifest


def reject(manifest: Manifest, reviewer: str, rationale: str) -> Manifest:
    """Human rejection: candidate -> rejected. The version never enters retrieval."""
    _require_human(reviewer, rationale)
    if manifest.status != STATUS_CANDIDATE:
        raise ValueError(f"only candidate versions can be rejected, got {manifest.status!r}")
    manifest.status = STATUS_REJECTED
    manifest.reviewer = reviewer
    manifest.notes = _append_note(manifest.notes, f"G0 rejected by {reviewer}: {rationale}")
    return manifest


def supersede(manifest: Manifest, successor_srcv: str, reviewer: str, rationale: str) -> Manifest:
    """Human decision that a newer version replaces this one: accepted -> superseded."""
    _require_human(reviewer, rationale)
    if manifest.status != STATUS_ACCEPTED:
        raise ValueError(f"only accepted versions can be superseded, got {manifest.status!r}")
    if not successor_srcv.startswith("SRCV-"):
        raise ValueError(f"successor must be a SRCV id, got {successor_srcv!r}")
    manifest.status = STATUS_SUPERSEDED
    manifest.reviewer = reviewer
    manifest.notes = _append_note(
        manifest.notes, f"G0 superseded by {successor_srcv} (decided by {reviewer}): {rationale}"
    )
    return manifest
