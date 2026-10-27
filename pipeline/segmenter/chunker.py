"""Two-level chunker (T10-005) — dispatch, implemented by the T10-031 adoption.

The PDF path is the ADOPTED teammate segmenter (``pdf_extractor`` adapter over
``src/chunking.py``, see src/PROVENANCE.md): one canonical Segment per detected
heading section, tables kept inside their section (§9 #3 provisional default,
rows preserved as ``col | col`` lines), stable IDs per source version.

DOCX remains unimplemented: the adopted core covers PDFs only; the DOCX
extractor is still a stub for its owning task (T10-005 follow-up).
"""
from __future__ import annotations

from pathlib import Path

from .models import Segment
from .pdf_extractor import extract_pdf


def segment_document(path: Path, source_version_id: str, source_type: str) -> list[Segment]:
    """Dispatch on source_type and return the chunk set."""
    if source_type == "pdf":
        return extract_pdf(path, source_version_id)
    raise NotImplementedError(
        f"segmentation for source_type {source_type!r} is not implemented yet "
        "(adopted core covers PDFs; DOCX extraction remains a stub)")
