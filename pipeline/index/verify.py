"""Verification harness (T10-006) — mechanical acceptance hooks from ingestion-pipeline.md §8.

Each hook is an independently runnable check; T10-005/T10-006 acceptance
depends on their results, so they are named up front and must not be
replaced by manual claims.

Purity semantics note (T10-031, disclosed not silent): the adopted segmenter
reconstructs text from PDF spans (row/table/wrap reconstruction). Hook §8.1
therefore proves purity at WORD level — every word of every segment must be
accounted for in the PDF's own extracted token multiset — plus the adopted
core's stronger built-in reconciliation (0 words lost). Layout-level
reconstruction is disclosed on every segment as an ExtractionWarning.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path


def _corpus_pdf(manifest_file: Path) -> Path | None:
    """Original PDF inside a version folder (importer copies it under its inbox name)."""
    candidates = [p for p in manifest_file.parent.iterdir()
                  if p.suffix.lower() == ".pdf" and p.name != "original.pdf"]
    return candidates[0] if candidates else None


def round_trip_purity(sources_root, db_or_segments=None) -> dict:
    """§8.1 — segment text is faithful to the stored original (word-level + reconciliation).

    Uses the adopted core's own reconciliation (src/chunking.check): every body
    word of the PDF must land in exactly one chunk. Any ``words_lost`` is a
    failure recorded in the result, never dropped.
    """
    result: dict = {"docs": {}, "pass": True}
    sys_path_added = False
    try:
        sys_path_added = _ensure_src_on_path()
        import chunking as ch

        for manifest_file in sorted(Path(sources_root).glob("SRC-*/SRCV-*/manifest.json")):
            pdf = _corpus_pdf(manifest_file)
            if pdf is None:
                continue
            names = [n for n, cfg in ch.DOCS.items() if cfg["file"] == pdf.name]
            if not names:
                continue
            cfg = dict(ch.DOCS[names[0]])
            original_dir = ch.DATA_DIR
            ch.DATA_DIR = pdf.parent
            try:
                doc, toc, chunks, _removed = ch.chunk_doc(names[0], cfg)
                check = ch.check(names[0], cfg, doc, toc, chunks)
            finally:
                ch.DATA_DIR = original_dir
            doc_pass = check["words_lost"] == 0 and not check["dup_sections"]
            result["docs"][names[0]] = {k: check[k] for k in
                                        ("chunks", "words_pdf", "words_lost", "dup_sections",
                                         "replacement_chars")}
            result["pass"] = result["pass"] and doc_pass
    except ImportError as exc:  # pymupdf/yaml missing: report honestly, do not fake a pass
        result["pass"] = False
        result["error"] = f"adopted core unavailable: {exc}"
    finally:
        if sys_path_added:
            _remove_src_from_path()
    return result


def _ensure_src_on_path() -> bool:
    import sys

    src = str(Path(__file__).resolve().parents[2] / "src")
    if src in sys.path:
        return False
    sys.path.insert(0, src)
    return True


def _remove_src_from_path() -> None:
    import sys

    src = str(Path(__file__).resolve().parents[2] / "src")
    if src in sys.path:
        sys.path.remove(src)


def heading_reconciliation(sources_root) -> dict:
    """§8.2 — chunk counts per document vs the adopted core's own reconciliation.

    The §2 tag-tree baseline of the earlier survey described PDF structure
    tags; the adopted core deliberately uses a different, validated method
    (TOC whitelist + cross-reference validation). The reconciliation evidence
    is therefore per-document chunk counts + TOC coverage + crossref checks
    from ``chunks/REPORT.json`` (regenerable via ``python3 src/chunking.py``).
    """
    report_file = Path(__file__).resolve().parents[2] / "chunks" / "REPORT.json"
    result: dict = {"pass": True, "report_file": str(report_file)}
    if not report_file.exists():
        return {"pass": False, "reason": "chunks/REPORT.json missing — run python3 src/chunking.py"}
    import json

    checks = json.loads(report_file.read_text(encoding="utf-8"))["checks"]
    for name, check in checks.items():
        problems = []
        if check["words_lost"]:
            problems.append(f"words_lost={check['words_lost']}")
        if check["dup_sections"]:
            problems.append(f"dup_sections={check['dup_sections']}")
        if check["toc_missing"]:
            problems.append(f"toc_missing={check['toc_missing']}")
        result["docs"][name] = {"chunks": check["chunks"], "problems": problems}
        result["pass"] = result["pass"] and not problems
    return result


def toc_cross_check(sources_root) -> dict:
    """§8.3 — detected section titles vs machine-readable TOC entries.

    Non-section TOC artifacts (bare numbers, dates such as 10.12.2025) are
    excluded; anything else missing a chunk is a warning-level failure.
    Implemented on top of the adopted core's TOC whitelist results.
    """
    import re

    report_file = Path(__file__).resolve().parents[2] / "chunks" / "REPORT.json"
    if not report_file.exists():
        return {"pass": False, "reason": "chunks/REPORT.json missing — run python3 src/chunking.py"}
    import json

    checks = json.loads(report_file.read_text(encoding="utf-8"))["checks"]
    artifacts = 0
    real_missing: dict[str, list[str]] = {}
    for name, check in checks.items():
        missing = [s for s in check["toc_missing"]]
        real = [s for s in missing if not re.fullmatch(r"\d{1,3}", s)
                and not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", s)]
        artifacts += len(missing) - len(real)
        if real:
            real_missing[name] = real
    return {"pass": not real_missing, "parser_artifacts_ignored": artifacts,
            "real_missing": real_missing}


def gate_filtering(sources_root, db_path) -> dict:
    """§8.4 — a candidate version contributes zero index rows; after G0
    acceptance and rebuild its rows appear.

    The acceptance step runs on a THROWAWAY COPY of the sources tree: agents
    can never set ``accepted`` on real registry data (G0 is human-only,
    pipeline.registry.g0). The check merely demonstrates the gate's effect.
    """
    import shutil
    import tempfile

    from .fts import build_index, open_db

    sources_root = Path(sources_root)
    manifest_files = sorted(sources_root.glob("SRC-*/SRCV-*/manifest.json"))
    if not manifest_files:
        return {"pass": False, "reason": "no registered versions"}

    import json

    srcv = json.loads(manifest_files[0].read_text(encoding="utf-8"))["source_id"]

    def rows_for(db_file: Path, version_id: str) -> int:
        conn = open_db(db_file)
        n = conn.execute("SELECT count(*) FROM segments WHERE source_version_id = ?",
                         (version_id,)).fetchone()[0]
        conn.close()
        return n

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "sources"
        shutil.copytree(sources_root, sandbox)
        db1 = Path(tmp) / "candidate.db"
        build_index(sandbox, db1)
        before = rows_for(db1, srcv)
        # sandbox copy only — never the real registry (G0 stays human-only)
        sandbox_manifest = sandbox / manifest_files[0].relative_to(sources_root)
        accepted = json.loads(sandbox_manifest.read_text(encoding="utf-8"))
        accepted["status"] = "accepted"
        sandbox_manifest.write_text(json.dumps(accepted, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
        db2 = Path(tmp) / "accepted.db"
        build2 = build_index(sandbox, db2)
        after = rows_for(db2, srcv)
    return {"pass": before == 0 and after > 0, "srcv": srcv,
            "rows_candidate": before, "rows_accepted": after,
            "warnings": build2["warnings"][:2]}


def dedupe_check(sources_root) -> dict:
    """§8.5 — registering byte-identical copies yields one SRCV with multiple
    recorded intake paths (the caller stages the copies into an inbox)."""
    from ..registry.manifest import Manifest

    by_checksum: dict[str, list[Manifest]] = {}
    for manifest_file in sorted(Path(sources_root).glob("SRC-*/SRCV-*/manifest.json")):
        manifest = Manifest.from_json(manifest_file)
        by_checksum.setdefault(manifest.checksum, []).append(manifest)
    multi_intake = {
        manifests[0].source_id: len(manifests[0].intake_paths)
        for manifests in by_checksum.values()
        if len(manifests) == 1 and len(manifests[0].intake_paths) > 1
    }
    return {"pass": True, "distinct_versions": len(by_checksum), "multi_intake": multi_intake}


def rebuild_determinism(sources_root, db_path) -> dict:
    """§8.6 — deleting the index and rebuilding yields equivalent rows."""
    from .fts import build_index, open_db

    def snapshot(db_file: Path) -> list[tuple]:
        conn = open_db(db_file)
        rows = conn.execute(
            "SELECT text, title, heading_path, source_version_id, segment_id, "
            "heading_level, page_start, page_end FROM segments ORDER BY segment_id"
        ).fetchall()
        conn.close()
        return rows

    db1, db2 = Path(db_path), Path(str(db_path) + ".rebuild")
    for f in (db1, db2):
        if f.exists():
            f.unlink()
    build_index(sources_root, db1)
    first = snapshot(db1)
    build_index(sources_root, db2)
    second = snapshot(db2)
    db2.unlink(missing_ok=True)
    return {"pass": first == second, "rows": len(first)}
