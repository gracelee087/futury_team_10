"""T10-036 — formal report PDF generator: structure, footer/hash honesty, fail-closed."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

from itsg import report_pdf
from itsg.candidates import ROLE_GATES, ROLE_REPORT_EXPLAINER, new_run, record_gate_decision


def _artifact(path: Path, results: list[dict] | None = None) -> Path:
    artifact = {
        "report_id": "RPT-TEST-1",
        "template_id": "TPL-SYNTH-1",
        "template_version": "synthetic-0.1",
        "template_warning": "SYNTHETIC TEMPLATE PROFILE — NOT an official ITSG form profile.",
        "official_form_id": None,
        "renderer_version": "itsg.renderer/0.1.0",
        "field_map_version": "itsg.fieldmap/synth-1",
        "generated_at": "2026-10-26T21:58:30+00:00",
        "compliance_claim": False,
        "compliance_claim_reason": "synthetic template: no compliance claim may be derived",
        "results": results if results is not None else [
            {"case_id": "TC-1", "criterion_id": "CRIT-1", "result_status": "PASS",
             "reason": "observed output matches expected value", "evidence_links": ["TC-1"]},
            {"case_id": "TC-2", "criterion_id": "CRIT-1", "result_status": "MISMATCH",
             "reason": "EAZ-BEGINN-1: expected '20XX0101', observed '20XX0401'",
             "evidence_links": ["TC-2"]},
            {"case_id": "TC-3", "criterion_id": "CRIT-1", "result_status": "NOT_EVALUATED",
             "reason": "missing expected value", "evidence_links": ["TC-3"]},
        ],
    }
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


class ReportPdfGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.artifact = _artifact(self.dir / "report.artifact.json")
        self.pdf = self.dir / "out" / "report.pdf"

    def _text(self) -> tuple[list[str], dict]:
        meta = report_pdf.generate_report_pdf(
            self.artifact, self.pdf, client_name="Muster Software GmbH",
            generated_at="2026-10-26 23:30:00 UTC")
        doc = fitz.open(str(self.pdf))
        pages = [doc[i].get_text() for i in range(doc.page_count)]
        doc.close()
        return pages, meta

    def test_generates_formal_structure(self) -> None:
        pages, _meta = self._text()
        self.assertTrue(self.pdf.read_bytes().startswith(b"%PDF"))
        joined = "\n".join(pages)
        for needle in ("Systemüberprüfungsbericht",          # formal German title (umlauts OK)
                       "Prüfobjekt / Kunde",
                       "Muster Software GmbH",
                       "Prüfbericht-Kopfdaten",
                       "Konformitätsaussage dieses Berichts: NEIN",
                       "Freigabe bleibt gesperrt",
                       "SHA-256"):
            self.assertIn(needle, joined, f"missing in PDF text: {needle!r}")

    def test_footer_on_every_page_discloses_machine_generation(self) -> None:
        many = [{"case_id": f"TC-{i}", "criterion_id": "CRIT-1",
                 "result_status": "MISMATCH", "reason": f"Abweichung {i}",
                 "evidence_links": [f"TC-{i}"]} for i in range(60)]
        artifact = _artifact(self.dir / "many.json", many)
        meta = report_pdf.generate_report_pdf(artifact, self.pdf)
        self.assertGreater(meta["pages"], 1, "expected pagination for the footer test")
        doc = fitz.open(str(self.pdf))
        for i in range(doc.page_count):
            page_text = doc[i].get_text()
            self.assertIn("Maschinell erzeugt von SÜSIE", page_text, f"page {i + 1}")
            self.assertIn("SHA-256:", page_text, f"page {i + 1}")
        doc.close()

    def test_footer_hash_is_content_hash_of_artifact(self) -> None:
        _pages, meta = self._text()
        expected = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.assertEqual(meta["content_hash"], expected)
        doc = fitz.open(str(self.pdf))
        self.assertIn(f"SHA-256: {expected}", doc[0].get_text())
        doc.close()

    def test_hash_stable_across_timestamps(self) -> None:
        _pages, meta1 = self._text()
        other = self.dir / "out2" / "report.pdf"
        meta2 = report_pdf.generate_report_pdf(self.artifact, other,
                                               generated_at="1999-01-01 00:00:00 UTC")
        self.assertEqual(meta1["content_hash"], meta2["content_hash"])
        self.assertEqual(meta1["content_hash"],
                         report_pdf.artifact_hash(self.artifact))

    def test_deterministic_bytes_with_pinned_timestamp(self) -> None:
        _pages, _ = self._text()
        other = self.dir / "out3" / "report.pdf"
        report_pdf.generate_report_pdf(self.artifact, other, client_name="Muster Software GmbH",
                                       generated_at="2026-10-26 23:30:00 UTC")
        self.assertEqual(self.pdf.read_bytes(), other.read_bytes())

    def test_summary_absent_is_honest(self) -> None:
        pages, meta = self._text()
        self.assertFalse(meta["summary_used"])
        self.assertIn("Keine KI-Zusammenfassung", "\n".join(pages))

    def test_summary_rendered_as_marked_draft(self) -> None:
        meta = report_pdf.generate_report_pdf(
            self.artifact, self.pdf, client_name="Muster Software GmbH",
            generated_at="2026-10-26 23:30:00 UTC",
            summary="Die Prüfung umfasst TC-1 (PASS), TC-2 (MISMATCH) und TC-3 "
                    "(NOT_EVALUATED).")
        doc = fitz.open(str(self.pdf))
        joined = "\n".join(doc[i].get_text() for i in range(doc.page_count))
        doc.close()
        self.assertTrue(meta["summary_used"])
        self.assertIn("KI-Entwurf", joined)
        self.assertIn("ungeprüft", joined)
        self.assertIn("TC-2 (MISMATCH)", joined)


class ReportLayoutRegressionTests(unittest.TestCase):
    def test_long_finding_preserves_every_word_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            words = [f"evidence{i:04d}" for i in range(800)]
            artifact = _artifact(root / "artifact.json", [{
                "case_id": "LONG-FINDING", "criterion_id": "CR-1",
                "result_status": "MISMATCH", "reason": " ".join(words),
                "evidence_links": ["SRCV-TEST p.135", "TRACE-END-800"],
            }])
            report_pdf.generate_report_pdf(artifact, root / "out.pdf")
            with fitz.open(root / "out.pdf") as doc:
                joined = "\n".join(p.get_text() for p in doc)
                for word in words:
                    self.assertEqual(joined.count(word), 1, word)
                self.assertIn("TRACE-END-800", joined)
                self.assertIn("Fortsetzung", joined)
                for page in doc:
                    # Body must never enter the reserved footer area.
                    for block in page.get_text("dict")["blocks"]:
                        for line in block.get("lines", []):
                            for span in line["spans"]:
                                if "evidence" in span["text"]:
                                    self.assertLess(span["bbox"][3], page.rect.height - 90)

    def test_unbroken_identifiers_wrap_within_measured_width(self):
        token = "ABCDEF0123456789" * 100
        lines = report_pdf._wrap(token, 160, 10)
        self.assertEqual("".join(lines), token)
        self.assertTrue(all(fitz.get_text_length(line, "helv", 10) <= 160 for line in lines))

    def test_source_punctuation_draws_inside_margins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _artifact(root / "artifact.json", [{
                "case_id": "PUNCTUATION", "criterion_id": "CR-1", "result_status": "PASS",
                "reason": "Deutsch: Prüfung, Größen und Übereinstimmung.",
                "evidence_links": ['Verfahrensbeschreibung DTA EEL „Datenbaustein DBVO – Vorerkrankungszeiten“, Version 13.4, ab 01.01.2027, S. 135'],
            }])
            report_pdf.generate_report_pdf(artifact, root / "out.pdf")
            with fitz.open(root / "out.pdf") as doc:
                for page in doc:
                    for word in page.get_text("words"):
                        self.assertGreaterEqual(word[0], 50)
                        self.assertLessEqual(word[2], page.rect.width - 50)

    def test_heading_and_status_share_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = _artifact(root / "artifact.json", [{
                "case_id": "ALIGNMENT-PROBE", "criterion_id": "CR-1",
                "result_status": "MISMATCH", "reason": "Body probe.",
                "evidence_links": ["SRCV-PROBE"],
            }])
            report_pdf.generate_report_pdf(artifact, root / "out.pdf")
            with fitz.open(root / "out.pdf") as doc:
                pg = next(p for p in doc if p.search_for("01  ALIGNMENT-PROBE"))
                title = pg.search_for("01  ALIGNMENT-PROBE")[0]
                statuses = pg.search_for("MISMATCH")
                self.assertTrue(any(abs(r.y0 - title.y0) < 5 for r in statuses))
                self.assertIn("SRCV-PROBE", pg.get_text())

    def test_invalid_gateway_json_degrades_to_error_run(self):
        for raw in ("not json", "[]", '{"summary_de": null}',
                    '{"summary_de": "text", "unexpected": true}'):
            with self.subTest(raw=raw), \
                 mock.patch.object(report_pdf.llm, "resolve_token", return_value="synthetic-token"), \
                 mock.patch.object(report_pdf.llm, "chat_completion", return_value=raw):
                run = report_pdf.draft_summary_live({"report_id": "TEST"}, [], "TEST")
                self.assertEqual(run.status, "error")
                self.assertNotIn("summary_de", run.result)


class ExplainerRoleTests(unittest.TestCase):
    def test_role_registered_and_recommendation_only(self) -> None:
        self.assertIn(ROLE_REPORT_EXPLAINER, ROLE_GATES)
        self.assertIsNone(ROLE_GATES[ROLE_REPORT_EXPLAINER])
        run = new_run(ROLE_REPORT_EXPLAINER, "REPORT-RPT-1", "provider", "model",
                      ["RPT-1"], result={"summary_de": "kurz"})
        self.assertTrue(run.review_required)
        with self.assertRaises(ValueError):
            record_gate_decision(run, reviewer="human", decision="approved",
                                 rationale="explainer owns no gate")

    def test_draft_summary_without_credentials_fails_closed(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        missing_store = Path(tmp.name) / "no-secrets-here"
        artifact = {"report_id": "RPT-TEST-1"}
        findings = [{"case_id": "TC-1", "criterion_id": "CRIT-1",
                     "result_status": "PASS", "reason": "ok"}]
        env_patch = os.environ.copy()
        env_patch.pop("SUSIE_LLM_TOKEN", None)
        with mock.patch.dict(os.environ, env_patch, clear=True):
            run = report_pdf.draft_summary_live(
                artifact, findings, "REPORT-RPT-1", store_path=str(missing_store),
                endpoint="https://203.0.113.1/v1/chat/completions")  # TEST-NET, never called
        self.assertEqual(run.status, "error")
        self.assertNotIn("summary_de", run.result)


if __name__ == "__main__":
    unittest.main()
