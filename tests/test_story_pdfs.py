"""T10-037 — story showcase: selection, layered evaluation, PDF rendering."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from itsg import story_pdfs
from itsg.report_pdf import generate_report_pdf

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "data" / "story_cases.json"


def _load():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


class SelectionTests(unittest.TestCase):
    def test_selects_exactly_ten_deterministically(self) -> None:
        cases = _load()
        first = story_pdfs.select_cases(cases)
        second = story_pdfs.select_cases(cases)
        self.assertEqual(len(first), 10)
        self.assertEqual([c["id"] for c in first], [c["id"] for c in second])
        self.assertEqual({c["story"] for c in first}, {1, 3, 4, 6})
        clean = [c for c in first if c["must_flag"] is None]
        defects = [c for c in first if c["must_flag"] is not None]
        self.assertEqual(len(clean), 5)
        self.assertEqual(len(defects), 5)


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = {c["id"]: c for c in _load()}

    def _by_category(self, story: int, needle: str) -> dict:
        return next(c for c in self.cases.values()
                    if c["story"] == story and needle in c["category"])

    def test_clean_transmit_case_all_pass(self) -> None:
        case = self._by_category(1, "current AU is a work accident")
        artifact = story_pdfs.evaluate_case(case)
        self.assertFalse(artifact["compliance_claim"])
        self.assertTrue(all(r["result_status"] == "PASS" for r in artifact["results"]),
                        artifact["results"])
        self.assertEqual(artifact["counts"]["MISMATCH"], 0)

    def test_under_30_days_defect_detected_by_rule_layer(self) -> None:
        case = self._by_category(1, "mixed reasons, under 30 days")
        artifact = story_pdfs.evaluate_case(case)
        # the rule decision itself agrees with the expectation (no 41 allowed):
        rule = next(r for r in artifact["results"] if r["case_id"] == "Regelprüfung")
        self.assertEqual(rule["result_status"], "PASS")
        self.assertIn("NO_TRIGGER", rule["reason"])
        # the defect is that a 41 was sent anyway -> caught by the field compare
        dbvo = next(r for r in artifact["results"] if r["case_id"] == "DBVO-Feldvergleich")
        self.assertEqual(dbvo["result_status"], "MISMATCH")
        # the ground-truth row must agree with the independent must_flag tag
        gt = next(r for r in artifact["results"] if r["case_id"] == "Ground-Truth-Abgleich")
        self.assertEqual(gt["result_status"], "PASS")

    def test_pkv_case_uses_outside_procedure_rule(self) -> None:
        case = self._by_category(1, "privately insured")
        artifact = story_pdfs.evaluate_case(case)
        rule = next(r for r in artifact["results"] if r["case_id"] == "Regelprüfung")
        self.assertIn("PKV", rule["criterion_id"])
        self.assertEqual(rule["result_status"], "MISMATCH")  # a 41 was sent although PKV

    def test_story3_defect_caught_in_dbvo_compare(self) -> None:
        case = self._by_category(3, "non-seamless short days reported")
        artifact = story_pdfs.evaluate_case(case)
        dbvo = next(r for r in artifact["results"] if r["case_id"] == "DBVO-Feldvergleich")
        self.assertEqual(dbvo["result_status"], "MISMATCH")

    def test_story4_reply_rules_detect_reorder(self) -> None:
        case = next(c for c in self.cases.values() if c["must_flag"] == "R61-order")
        artifact = story_pdfs.evaluate_case(case)
        reply = next(r for r in artifact["results"] if r["case_id"] == "61-Antwort-Prüfung")
        self.assertEqual(reply["result_status"], "MISMATCH")

    def test_story6_flow_detects_88_on_wrong_message(self) -> None:
        case = next(c for c in self.cases.values() if c["must_flag"] == "F-88-UR")
        artifact = story_pdfs.evaluate_case(case)
        flow = [r for r in artifact["results"] if r["case_id"].startswith("Ablauf/")]
        self.assertTrue(any(r["result_status"] == "MISMATCH" for r in flow), flow)

    def test_clean_story6_flow_passes(self) -> None:
        case = self._by_category(6, "correct cancel-and-correct flow")
        artifact = story_pdfs.evaluate_case(case)
        self.assertTrue(all(r["result_status"] == "PASS" for r in artifact["results"]),
                        artifact["results"])


class RenderTests(unittest.TestCase):
    def test_ten_artifacts_render_with_context_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metas = story_pdfs.build_all(CASES_PATH, tmp)
            self.assertEqual(len(metas), 10)
            pdfs = sorted(Path(tmp).glob("SUSIE-showcase-*.pdf"))
            self.assertEqual(len(pdfs), 10)
            sample = next(p for p in pdfs if "S1-0" in p.name)
            case_id = sample.stem.removeprefix("SUSIE-showcase-")
            doc = fitz.open(str(sample))
            text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
            doc.close()
            self.assertIn("Maschinell erzeugt von SÜSIE", text)
            self.assertIn("Konformitätsaussage dieses Berichts: NEIN", text)
            self.assertIn("Story", text)          # context rows rendered
            self.assertIn("Regeltaxonomie-Tag", text)
            artifact = json.loads((Path(tmp) / f"artifact-{case_id}.json")
                                  .read_text(encoding="utf-8"))
            self.assertIn("SHA-256", text)
            self.assertIn(artifact["report_id"], text)
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index), 10)


if __name__ == "__main__":
    unittest.main()
