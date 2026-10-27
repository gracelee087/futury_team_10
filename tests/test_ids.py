"""Tests for pipeline.ids — stable IDs and checksums (stdlib only)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.ids import checksum_bytes, checksum_file, new_id, next_seq


class TestIds(unittest.TestCase):
    def test_new_id_basic(self):
        self.assertEqual(new_id("SRC", 12), "SRC-12")
        self.assertEqual(new_id("SRCV", 12, "A"), "SRCV-12-A")

    def test_new_id_rejects_zero_and_negative(self):
        for bad in (0, -3):
            with self.assertRaises(ValueError):
                new_id("SRC", bad)

    def test_next_seq(self):
        self.assertEqual(next_seq(["SRC-1", "SRC-3"], "SRC"), 4)
        self.assertEqual(next_seq([], "SRC"), 1)
        self.assertEqual(next_seq(["SRCV-1-A"], "SRC"), 1)  # prefix must not partial-match

    def test_checksum_bytes_known_vector(self):
        self.assertEqual(
            checksum_bytes(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_checksum_file_streamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.pdf"
            payload = b"\x25PDF-fixture-bytes" * 1000
            path.write_bytes(payload)
            self.assertEqual(checksum_file(path), checksum_bytes(payload))


if __name__ == "__main__":
    unittest.main()
