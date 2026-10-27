"""Tests for the adopted segmenter adapter (T10-031): src/chunking.py → typed Segments.

Skipped cleanly when PyMuPDF/PyYAML or the corpus PDF is absent — the rest of
the suite stays stdlib-only. The heavyweight reconciliation evidence lives in
chunks/REPORT.json (regenerable: DATA_DIR=<corpus> python3 src/chunking.py).
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GG_EEL = ROOT / "ITSG Files" / "Laws" / "GG_EEL_V13.1_06.05.2025.pdf"

try:
    import yaml  # noqa: F401
    import fitz  # noqa: F401
    DEPS = True
except ImportError:
    DEPS = False

from pipeline.segmenter.chunker import segment_document
from pipeline.segmenter.models import Segment, load_segments_jsonl


@unittest.skipUnless(DEPS and GG_EEL.exists(), "pymupdf/pyyaml or corpus PDF not available")
class TestAdoptedSegmenter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.segments = segment_document(GG_EEL, "SRCV-TEST-A", "pdf")

    def test_gg_eel_yields_the_documented_chunks(self):
        # adopted core reconciliation: 27 chunks for GG_EEL, of which 2 are empty
        self.assertEqual(len(self.segments), 25)

    def test_segments_are_candidate_and_carry_layout_disclosure(self):
        for segment in self.segments:
            self.assertEqual(segment.status, "candidate")
            codes = {w.code for w in segment.extraction_warnings}
            self.assertIn("reconstructed_layout", codes)

    def test_ids_are_stable_and_ordered(self):
        again = segment_document(GG_EEL, "SRCV-TEST-A", "pdf")
        self.assertEqual([s.segment_id for s in self.segments], [s.segment_id for s in again])
        self.assertEqual([s.text for s in self.segments], [s.text for s in again])
        self.assertEqual([s.segment_id for s in self.segments],
                         sorted((s.segment_id for s in self.segments)))

    def test_locators_point_into_the_document(self):
        for segment in self.segments:
            self.assertGreaterEqual(segment.page_start, 3)  # GG body starts p.3
            self.assertLessEqual(segment.page_end, 16)
            self.assertTrue(segment.title.strip())

    def test_jsonl_roundtrip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "segments.jsonl"
            from pipeline.segmenter.models import dump_segments_jsonl

            dump_segments_jsonl(self.segments, path)
            loaded = load_segments_jsonl(path)
            self.assertEqual(len(loaded), len(self.segments))
            self.assertEqual(loaded[0].text, self.segments[0].text)

    def test_unknown_file_rejected(self):
        with self.assertRaises(ValueError):
            segment_document(ROOT / "fixtures" / "synthetic_template.json", "SRCV-X", "pdf")

    def test_docx_still_stub(self):
        with self.assertRaises(NotImplementedError):
            segment_document(GG_EEL, "SRCV-X", "docx")


class TestSegmentModelGuards(unittest.TestCase):
    def test_unknown_chunk_type_rejected(self):
        with self.assertRaises(ValueError):
            Segment(segment_id="SEG-x-0001", source_version_id="SRCV-1-A", heading_level=1,
                    heading_path=["t"], title="t", page_start=1, page_end=1, text="x",
                    chunk_type="prose")


if __name__ == "__main__":
    unittest.main()
