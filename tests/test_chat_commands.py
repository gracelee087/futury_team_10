"""T10-042 — deterministic chat command layer: demo-critical navigation works
without the LLM; every reply carries the AgentRun envelope; mutating proposals
carry confirmation tokens; free-form questions still fall through to the LLM."""
from __future__ import annotations

import unittest

from itsg import chat

STATE = {
    "cases": [
        {"id": "TC-1", "case_type": "normal", "status": "PASS", "reason": ""},
        {"id": "TC-2", "case_type": "boundary", "status": "MISMATCH",
         "reason": "EAZ-BEGINN-1: expected '20XX0101', observed '20XX0401'"},
        {"id": "TC-3", "case_type": "invalid", "status": "NOT_EVALUATED",
         "reason": "missing expected value"},
    ],
    "report": {"id": "RPT-1"},
}


class DeterministicCommandTests(unittest.TestCase):
    def _turn(self, message: str):
        return chat.deterministic_turn(message, STATE, "T10-042", "s1")

    def test_start_over_proposes_read_only_action(self) -> None:
        for msg in ("Start over", "Neu starten", "fangen wir neu an", "reset"):
            with self.subTest(msg=msg):
                reply = self._turn(msg)
                self.assertIsNotNone(reply, msg)
                self.assertEqual(reply.action["id"], "start_over")
                self.assertFalse(reply.needs_confirmation)
                self.assertTrue(reply.agent_run.get("run_id"))

    def test_go_back(self) -> None:
        reply = self._turn("zurück")
        self.assertIsNotNone(reply)
        self.assertEqual(reply.action["id"], "go_back")

    def test_next_and_previous_case_stepping(self) -> None:
        for msg, expected in (("nächster Fall", "next_case"), ("next case", "next_case"),
                              ("weiter", "next_case"), ("vorheriger Fall", "prev_case"),
                              ("previous case", "prev_case")):
            with self.subTest(msg=msg):
                reply = self._turn(msg)
                self.assertIsNotNone(reply, msg)
                self.assertEqual(reply.action["id"], expected)

    def test_sources_question_answered_deterministically(self) -> None:
        state = dict(STATE, source={
            "id": "SRC-BP", "title": "Beispielpapier DTA EEL",
            "issuer": "GKV-Spitzenverband", "version": "V13.3",
            "valid_from": "01.01.2027"})
        reply = chat.deterministic_turn("Welche Quellen liegen zugrunde?", state,
                                        "T10-042", "s1")
        self.assertIsNotNone(reply)
        self.assertIsNone(reply.action)
        self.assertIn("SRC-BP", reply.utterance)
        self.assertIn("Beispielpapier", reply.utterance)

    def test_status_summary_is_deterministic_and_human(self) -> None:
        reply = self._turn("Wo stehe ich?")
        self.assertIsNotNone(reply)
        self.assertIsNone(reply.action)
        self.assertIn("1 MISMATCH", reply.utterance)
        self.assertIn("TC-2", reply.utterance)
        self.assertIn("Beginn der Entgeltersatzleistung", reply.utterance)
        self.assertNotIn("JSON", reply.utterance)

    def test_select_case_with_human_reason(self) -> None:
        reply = self._turn("öffne fall tc-2")
        self.assertIsNotNone(reply)
        self.assertEqual(reply.action["id"], "open_evidence")
        self.assertEqual(reply.action["params"], {"case_id": "TC-2"})
        self.assertIn("erwartet 20XX0101", reply.utterance)

    def test_deviation_without_case_id_selects_first_mismatch(self) -> None:
        reply = self._turn("zeig mir die abweichung")
        self.assertIsNotNone(reply)
        self.assertEqual(reply.action["params"], {"case_id": "TC-2"})

    def test_run_comparison_and_export_need_confirmation(self) -> None:
        run = self._turn("generiere testfälle aus dem gesetz")
        self.assertIsNotNone(run)
        self.assertEqual(run.action["id"], "run_comparison")
        self.assertTrue(run.needs_confirmation)
        self.assertEqual(run.action["params"], {"live": True})
        export = self._turn("Erstelle mir den Bericht als PDF")
        self.assertIsNotNone(export)
        self.assertEqual(export.action["id"], "export_report")
        self.assertTrue(export.needs_confirmation)

    def test_software_abgleich_proposes_offline_comparison(self) -> None:
        for msg in ("Starte den Abgleich mit der Softwareausgabe",
                    "Führe den Abgleich durch",
                    "Run the field comparison against the software output"):
            with self.subTest(msg=msg):
                reply = self._turn(msg)
                self.assertIsNotNone(reply, msg)
                self.assertEqual(reply.action["id"], "run_comparison")
                self.assertTrue(reply.needs_confirmation)
                self.assertEqual(reply.action["params"], {"live": False})
                self.assertRegex(reply.utterance.lower(), r"deterministisch|deterministic")

    def test_feldvergleich_anzeigen_is_not_a_run(self) -> None:
        # "zeig mir den Feldvergleich" is navigation, not a run proposal
        reply = self._turn("Zeig mir den Feldvergleich")
        if reply is not None and reply.action:
            self.assertEqual(reply.action["id"], "open_evidence")

    def test_free_form_questions_fall_through_to_llm(self) -> None:
        for msg in ("Was ist eine Vorerkrankung?", "Warum ist der Himmel blau?"):
            with self.subTest(msg=msg):
                self.assertIsNone(self._turn(msg))

    def test_every_deterministic_reply_carries_envelope(self) -> None:
        for msg in ("Start over", "zurück", "Wo stehe ich?", "öffne fall tc-2",
                    "generiere testfälle", "exportiere den bericht"):
            with self.subTest(msg=msg):
                reply = self._turn(msg)
                self.assertTrue(reply.agent_run.get("run_id"))
                self.assertEqual(reply.agent_run.get("role"), chat.ROLE_SUSIE_ASSISTANT)
                self.assertTrue(reply.agent_run.get("result", {}).get("deterministic_command"))


if __name__ == "__main__":
    unittest.main()
