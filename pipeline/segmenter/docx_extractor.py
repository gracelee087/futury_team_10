"""DOCX heading-style extractor (task T10-005).

DOCX files carry heading styles readable natively via ``python-docx``
(paragraph.style Heading 1..6); the two DOCX files in the corpus are
segmented from those styles. Exact text, same purity rules as the PDF
extractor (ingestion-pipeline.md §6).
"""
from __future__ import annotations

from pathlib import Path

from .models import Segment

# import docx  # python-docx — imported lazily inside extract_docx when T10-005 is implemented


def extract_docx(path: Path, source_version_id: str) -> list[Segment]:
    """Extract canonical heading segments from a DOCX file. STUB — implemented by T10-005."""
    raise NotImplementedError("T10-005: DOCX extraction")
