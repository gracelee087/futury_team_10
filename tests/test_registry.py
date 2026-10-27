"""Tests for the registry skeleton: manifest schema (pipeline.registry.manifest)
and the human-only G0 gate (pipeline.registry.g0)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.registry import g0
from pipeline.registry.manifest import (
    STATUS_ACCEPTED,
    STATUS_CANDIDATE,
    STATUS_SUPERSEDED,
    Manifest,
    manifest_path,
    parse_srcv_id,
    srcv_dir,
)


def sample_manifest(**overrides) -> Manifest:
    defaults = dict(
        source_id="SRC-1",
        title="Grundsicherung für Arbeitsuchende (Demo-Referenz)",
        issuing_body="Demo",
        source_type="law",
        checksum="a" * 64,
    )
    defaults.update(overrides)
    return Manifest(**defaults)


class TestManifest(unittest.TestCase):
    def test_every_version_enters_as_candidate(self):
        self.assertEqual(sample_manifest().status, STATUS_CANDIDATE)

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            sample_manifest(status="approved-by-agent")

    def test_unknown_source_type_rejected(self):
        with self.assertRaises(ValueError):
            sample_manifest(source_type="blog")

    def test_from_dict_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            Manifest.from_dict({"source_id": "SRC-1", "guessed_field": True})

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            original = sample_manifest(intake_paths=["data/inbox/a.pdf"])
            original.to_json(path)
            loaded = Manifest.from_json(path)
            self.assertEqual(loaded, original)

    def test_srcv_path_layout(self):
        self.assertEqual(parse_srcv_id("SRCV-12-A"), (12, "A"))
        self.assertEqual(
            srcv_dir("data/sources", "SRCV-12-A"), Path("data/sources/SRC-12/SRCV-12-A")
        )
        self.assertEqual(
            manifest_path("data/sources", "SRCV-12-A"),
            Path("data/sources/SRC-12/SRCV-12-A/manifest.json"),
        )
        with self.assertRaises(ValueError):
            parse_srcv_id("SRC-12-A")


class TestGateG0(unittest.TestCase):
    def test_accept_moves_candidate_to_accepted(self):
        manifest = g0.accept(sample_manifest(), reviewer="Team 10 product facilitator", rationale="verified")
        self.assertEqual(manifest.status, STATUS_ACCEPTED)
        self.assertEqual(manifest.reviewer, "Team 10 product facilitator")
        self.assertIn("verified", manifest.notes)

    def test_agent_cannot_accept_without_reviewer(self):
        manifest = sample_manifest()
        with self.assertRaises(ValueError):
            g0.accept(manifest, reviewer="", rationale="verified")
        with self.assertRaises(ValueError):
            g0.accept(manifest, reviewer="   ", rationale="verified")
        self.assertEqual(manifest.status, STATUS_CANDIDATE)  # unchanged — fail closed

    def test_accept_requires_rationale(self):
        with self.assertRaises(ValueError):
            g0.accept(sample_manifest(), reviewer="human", rationale="")

    def test_double_accept_is_illegal(self):
        manifest = g0.accept(sample_manifest(), reviewer="human", rationale="ok")
        with self.assertRaises(ValueError):
            g0.accept(manifest, reviewer="human", rationale="again")

    def test_reject_and_supersede_paths(self):
        rejected = g0.reject(sample_manifest(), reviewer="human", rationale="wrong origin")
        self.assertEqual(rejected.status, "rejected")
        accepted = g0.accept(sample_manifest(), reviewer="human", rationale="ok")
        superseded = g0.supersede(accepted, "SRCV-1-B", reviewer="human", rationale="new edition")
        self.assertEqual(superseded.status, STATUS_SUPERSEDED)
        self.assertIn("SRCV-1-B", superseded.notes)
        with self.assertRaises(ValueError):
            g0.supersede(accepted, "not-an-srcv", reviewer="human", rationale="x")


if __name__ == "__main__":
    unittest.main()
