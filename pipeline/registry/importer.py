"""Stage A — inbox import and registry (T10-004, implemented T10-031).

Contract implemented:

  1. For every file in the inbox: SHA-256, then
       - a registered manifest with the same checksum gains the inbox path in
         its ``intake_paths`` — identical bytes are never duplicated;
       - otherwise ``data/sources/SRC-<n>/SRCV-<n>-<L>/`` is created with the
         original bytes copied once (immutable) and a manifest.json with the
         architecture §4 fields.
  2. Every version enters with status ``candidate`` — fetch is not accept
     (G0 moves it, human-only).
  3. Filename version hints (V13.1, gueltig_ab_01.01.2027) are captured as
     candidate metadata; unknown fields stay empty.
  4. One AuditRecord per run (pipeline.audit).

Known dedupe case in the corpus: GG_EEL exists twice (``Laws/`` and
``Rules Input part 1/``) with identical bytes -> exactly one SRCV with two
recorded intake paths (verification hook ingestion-pipeline.md §8.5,
``pipeline.index.verify.dedupe_check``).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..audit import AuditRecord, append_jsonl
from ..ids import checksum_file, checksum_bytes, next_seq
from .manifest import (
    Manifest,
    manifest_path,
    parse_srcv_id,
    srcv_dir,
)

VERSION_HINT = re.compile(r"[Vv](\d+\.\d+)")
VALID_FROM_HINT = re.compile(r"gueltig_ab[_-]?(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)


def _existing_manifests(sources_root: Path) -> list[Manifest]:
    root = Path(sources_root)
    if not root.exists():
        return []
    found = []
    for path in sorted(root.glob("SRC-*/SRCV-*/manifest.json")):
        found.append(Manifest.from_json(path))
    return found


def _next_srcv_id(sources_root: Path, manifests: list[Manifest]) -> str:
    seq = next_seq([m.source_id for m in manifests], "SRC")
    letters = sorted(
        parse_srcv_id(m.source_id)[1] for m in manifests if parse_srcv_id(m.source_id)[0] == seq
    )
    suffix = chr(ord("A") + len(letters)) if letters else "A"
    return f"SRCV-{seq}-{suffix}"


def _hints(path: Path) -> dict:
    name = path.name
    version = VERSION_HINT.search(name)
    valid_from = VALID_FROM_HINT.search(name)
    return {
        "edition_or_version": version.group(1) if version else "",
        "valid_from": valid_from.group(1) if valid_from else None,
    }


def register_inbox(inbox: Path, sources_root: Path, task_id: str = "T10-004") -> list[Manifest]:
    """Register every file in the inbox; checksum dedupe, G0-candidate default."""
    inbox = Path(inbox)
    files = sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith("."))
    manifests = _existing_manifests(sources_root)
    registered: list[Manifest] = []
    warnings: list[str] = []

    for path in files:
        digest = checksum_file(path)
        twin = next((m for m in manifests if m.checksum == digest), None)
        if twin is not None:
            if path.name not in twin.intake_paths:
                twin.intake_paths.append(path.name)
                twin.to_json(manifest_path(sources_root, twin.source_id))
            registered.append(twin)
            continue

        srcv = _next_srcv_id(sources_root, manifests)
        hints = _hints(path)
        manifest = Manifest(
            source_id=srcv,
            title=path.stem,
            checksum=digest,
            status="candidate",
            intake_paths=[path.name],
            **hints,
        )
        vdir = srcv_dir(sources_root, srcv)
        vdir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, vdir / path.name)  # immutable original, copied once
        manifest.to_json(manifest_path(sources_root, srcv))
        manifests.append(manifest)
        registered.append(manifest)

    # manifest.json itself is not inbox content; originals sit next to it
    record = AuditRecord(
        run_id=f"IMPORT-{task_id}-{checksum_bytes(str(sorted(p.name for p in files)).encode())[:8]}",
        task_id=task_id,
        role="source_intake",
        tool="pipeline.registry.importer/0.2.0",
        input_ids=[m.source_id for m in registered],
        input_checksums={m.source_id: m.checksum for m in registered},
        counts={"files": len(files), "versions": len({m.source_id for m in registered}),
                "deduped": len(registered) - len({m.source_id for m in registered})},
        warnings=warnings,
        status="candidate",
        notes="fetch is not accept: all versions enter as candidate (G0 is human-only)",
    )
    append_jsonl(Path(sources_root) / "audit.jsonl", record.to_dict())
    return registered
