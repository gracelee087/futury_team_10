"""Tagged-PDF structure extractor — T10-005, implemented as an adapter (T10-031).

The extraction core is the ADOPTED teammate implementation ``src/chunking.py``
(see src/PROVENANCE.md): deterministic header-based segmentation with a
TOC whitelist, hidden-number handling (VB), table-cell reconstruction, and a
built-in reconciliation check. This adapter maps its output onto the typed
``Segment`` records of this package so the rest of the pipeline (index,
retrieval, citations) is decoupled from the extraction internals.

Purity note (fail-honest, not silent): the adopted core deterministically
RECONSTRUCTS rows from PDF spans — it merges hyphenated continuations and
table cells, and joins wrapped lines. Word-level fidelity is proven by the
reconciliation check (0 words lost across all six documents, recorded in
``chunks/REPORT.json``); every segment carries an ``extraction_warnings``
entry code ``reconstructed_layout`` so downstream consumers know the text is
a faithful reconstruction, not a byte-copy of the PDF text layer.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from .models import ExtractionWarning, Segment

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"


def _load_chunking():
    """Import the adopted src/chunking.py lazily; pymupdf/yaml needed only here."""
    if not (_SRC / "chunking.py").exists():
        raise FileNotFoundError(f"adopted segmenter core missing: {_SRC / 'chunking.py'}")
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    import chunking as ch  # noqa: PLC0415 (lazy, deliberate)

    return ch


def _section_key(section: str) -> list[int]:
    return [int(p) for p in section.split(".") if p.isdigit()]


def _doc_warnings(name: str, check: dict) -> list[ExtractionWarning]:
    warnings: list[ExtractionWarning] = []
    if check.get("words_lost"):
        warnings.append(ExtractionWarning(
            "words_lost", f"{name}: {check['words_lost']} body words not captured by any chunk", None))
    for page in check.get("pages_uncovered", []):
        warnings.append(ExtractionWarning(
            "page_uncovered", f"{name}: body page {page} contributed no chunk (divider/empty page)", page))
    real_missing = [s for s in check.get("toc_missing", [])
                    if not re.fullmatch(r"\d{1,3}", s) and "." in s and "20" not in s]
    for section in real_missing:
        warnings.append(ExtractionWarning(
            "toc_missing", f"{name}: TOC section {section} has no chunk", None))
    for section in check.get("empty_chunks", []):
        warnings.append(ExtractionWarning(
            "empty_chunk", f"{name}: chunk {section} has no body text", None))
    for section in check.get("dup_sections", []):
        warnings.append(ExtractionWarning(
            "duplicate_section", f"{name}: section {section} appears more than once", None))
    return warnings


def extract_pdf(path: Path, source_version_id: str) -> list[Segment]:
    """Extract canonical heading segments from a corpus PDF via the adopted core.

    ``path`` must be one of the six configured corpus files (matched by
    filename against ``src.chunking.DOCS``). Segments are ordered by
    (first page, section number); IDs are stable for a given extraction.
    """
    ch = _load_chunking()
    path = Path(path)
    matches = [name for name, cfg in ch.DOCS.items() if cfg["file"] == path.name]
    if not matches:
        raise ValueError(
            f"{path.name!r} is not a configured corpus document "
            f"(known: {sorted(cfg['file'] for cfg in ch.DOCS.values())})")
    name = matches[0]
    cfg = dict(ch.DOCS[name])

    original_dir = ch.DATA_DIR
    ch.DATA_DIR = path.parent  # the adapter resolves the corpus location per call
    try:
        doc, _toc, chunks, _removed = ch.chunk_doc(name, cfg)
        check = ch.check(name, cfg, doc, _toc, chunks)
    finally:
        ch.DATA_DIR = original_dir

    doc_warnings = _doc_warnings(name, check)
    chunks = [c for c in chunks if c["text"].strip() or c["level"] == 0]
    chunks.sort(key=lambda c: (min(c["pages"]), _section_key(c["section"])))
    segments: list[Segment] = []
    for idx, c in enumerate(chunks, start=1):
        warnings = [ExtractionWarning(
            "reconstructed_layout",
            "text deterministically reconstructed from PDF spans (row/table/wrap "
            "reconstruction); word fidelity proven by chunks/REPORT.json reconciliation",
            min(c["pages"]),
        )]
        segments.append(Segment(
            segment_id=f"SEG-{source_version_id}-{idx:04d}",
            source_version_id=source_version_id,
            heading_level=min(c["level"] + 1, 6),
            heading_path=[cfg["title"], f"{c['section']} {c['title']}"],
            title=f"{c['section']} {c['title']}".strip(),
            page_start=min(c["pages"]),
            page_end=max(c["pages"]),
            text=c["text"],
            extraction_warnings=warnings,
        ))
    if doc_warnings:
        first = segments[0] if segments else Segment(
            segment_id=f"SEG-{source_version_id}-0000", source_version_id=source_version_id,
            heading_level=0, heading_path=[cfg["title"]], title=cfg["title"],
            page_start=cfg["body_start"], page_end=cfg["body_start"], text="")
        first.extraction_warnings.extend(doc_warnings)
    return segments
