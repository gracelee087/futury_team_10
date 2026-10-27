"""Registry + index tests (T10-004/T10-006 substance, wired in T10-031) — stdlib-only.

Covers: checksum dedupe, G0-candidate default, gate filtering (§8.4, sandbox
acceptance only), rebuild determinism (§8.6), and the dedupe hook (§8.5).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.index import verify
from pipeline.index.fts import build_index, open_db
from pipeline.registry.importer import register_inbox
from pipeline.registry.manifest import manifest_path, srcv_dir


def stage(tmp: Path) -> tuple[Path, str, str]:
    inbox = tmp / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "doc_a.pdf").write_bytes(b"PDF-A content")
    (inbox / "doc_a_copy.pdf").write_bytes(b"PDF-A content")
    (inbox / "doc_b.pdf").write_bytes(b"PDF-B content")
    manifests = register_inbox(inbox, tmp / "sources")
    srcv_a = next(m.source_id for m in manifests if "doc_a" in m.title)
    srcv_b = next(m.source_id for m in manifests if "doc_b" in m.title)
    return tmp / "sources", srcv_a, srcv_b


def add_segment(sources_root: Path, srcv: str, text: str) -> None:
    payload = {"segment_id": f"SEG-{srcv}-0001", "source_version_id": srcv,
               "heading_level": 1, "heading_path": ["T"], "title": "T",
               "page_start": 1, "page_end": 1, "text": text,
               "extraction_warnings": [], "status": "candidate"}
    (srcv_dir(sources_root, srcv) / "segments.jsonl").write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


class TestImporter(unittest.TestCase):
    def test_identical_bytes_never_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, srcv_a, _ = stage(Path(tmp))
            manifest = json.loads(manifest_path(sources, srcv_a).read_text(encoding="utf-8"))
            self.assertEqual(manifest["intake_paths"], ["doc_a.pdf", "doc_a_copy.pdf"])
            self.assertEqual(len(list(sources.glob("SRC-*/SRCV-*"))), 2)  # not 3 folders

    def test_everything_enters_as_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, _ = stage(Path(tmp))
            for manifest_file in sources.glob("SRC-*/SRCV-*/manifest.json"):
                self.assertEqual(json.loads(manifest_file.read_text(encoding="utf-8"))["status"],
                                 "candidate")

    def test_original_copied_once_and_audit_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, srcv_a, _ = stage(Path(tmp))
            originals = list(srcv_dir(sources, srcv_a).iterdir())
            self.assertEqual(len(originals), 2)  # original + manifest.json
            audit = (sources / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
            record = json.loads(audit[-1])
            self.assertEqual(record["role"], "source_intake")
            self.assertEqual(record["counts"]["deduped"], 1)
            self.assertIn("fetch is not accept", record["notes"])

    def test_second_registration_of_same_file_links_without_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, _ = stage(Path(tmp))
            before = len(list(sources.glob("SRC-*/SRCV-*")))
            register_inbox(Path(tmp) / "inbox", sources)  # same inbox again
            self.assertEqual(len(list(sources.glob("SRC-*/SRCV-*"))), before)


class TestIndexGateAndRebuild(unittest.TestCase):
    def test_candidate_version_contributes_zero_rows_until_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, srcv_a, srcv_b = stage(Path(tmp))
            add_segment(sources, srcv_a, "Vorerkrankung Testtext")
            db = Path(tmp) / "idx.db"
            record = build_index(sources, db)
            self.assertEqual(record["counts"]["rows"], 0)  # both candidate: gate filtering
            self.assertTrue(any(srcv_a in w for w in record["warnings"]))

            conn = open_db(db)
            n = conn.execute("SELECT count(*) FROM segments").fetchone()[0]
            conn.close()
            self.assertEqual(n, 0)

    def test_rebuild_determinism_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, srcv_a, _ = stage(Path(tmp))
            add_segment(sources, srcv_a, "Hallo Welt")
            result = verify.rebuild_determinism(sources, Path(tmp) / "idx.db")
            self.assertTrue(result["pass"])
            self.assertEqual(result["rows"], 0)  # candidate until G0 — consistent with §8.4

    def test_gate_filtering_hook_uses_sandbox_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, srcv_a, _ = stage(Path(tmp))
            add_segment(sources, srcv_a, "Hallo Welt")
            before = json.loads(manifest_path(sources, srcv_a).read_text(encoding="utf-8"))
            result = verify.gate_filtering(sources, Path(tmp) / "idx.db")
            self.assertTrue(result["pass"])
            self.assertEqual(result["rows_candidate"], 0)
            self.assertGreater(result["rows_accepted"], 0)
            # the real registry was never mutated by the agent (G0 stays human-only)
            after = json.loads(manifest_path(sources, srcv_a).read_text(encoding="utf-8"))
            self.assertEqual(after["status"], before["status"])

    def test_dedupe_hook_reports_multi_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, _, _ = stage(Path(tmp))
            result = verify.dedupe_check(sources)
            self.assertTrue(result["pass"])
            self.assertEqual(result["distinct_versions"], 2)
            self.assertEqual(len(result["multi_intake"]), 1)


if __name__ == "__main__":
    unittest.main()
