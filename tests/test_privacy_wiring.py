"""T10-043 — Datenschutz-Schleuse wired into the SÜSIE stack.

Covers the two integration points this repo added on top of Fares's privacy/
module (whose own detectors/guards are covered by privacy/test_*.py):

1. itsg.chat.turn() routes the outbound gateway payload through the airlock
   (pseudonymize + final check_clean gate, fail closed).
2. itsg.webserver.privacy_status() reports an honest, value-free status for
   the UI shield badge.
"""
from __future__ import annotations

import unittest
from unittest import mock

from itsg import chat, webserver

STATE = {
    "cases": [{"id": "TC-1", "case_type": "normal", "status": "PASS", "reason": ""}],
    "report": {"id": "RPT-1"},
}

# A synthetic Versicherungsnummer (valid-looking: area != 00, plausible DDMMYY birth date,
# in the spaced layout the airlock's detector accepts).
VSNR = "12 150685 A 123"
MESSAGE = f"Bitte prüfen Sie den Fall für die VSNR {VSNR}."


class ChatAirlockTests(unittest.TestCase):
    """The real (non-injected) gateway path must pass through the airlock."""

    def setUp(self) -> None:
        self.captured = {}

        def fake_completion(endpoint, model, system_prompt, messages, token, timeout=25):
            self.captured["content"] = messages[0]["content"]
            return '{"utterance": "Verstanden.", "confidence": "unknown", "citations": []}'

        self._patches = [
            mock.patch.object(chat, "resolve_token", return_value="test-token"),
            mock.patch.object(chat, "chat_completion", side_effect=fake_completion),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _turn(self, message: str):
        return chat.turn(message, STATE, corpus_hits=[], history=[], store_path=":memory:")

    def test_wired_module_import(self) -> None:
        self.assertIsNotNone(chat.Schleuse, "privacy.schleuse must be importable for the chat airlock")

    def test_outbound_content_pseudonymized(self) -> None:
        reply = self._turn(MESSAGE)
        self.assertFalse(reply.degraded)
        content = self.captured["content"]
        self.assertNotIn(VSNR, content, "raw VSNR must never reach the gateway")
        self.assertIn("VSNR_", content, "pseudonymized token expected in the outbound payload")

    def test_envelope_records_airlock_summary(self) -> None:
        reply = self._turn(MESSAGE)
        privacy = reply.agent_run["result"].get("privacy")
        self.assertIsInstance(privacy, dict)
        self.assertEqual(privacy.get("airlock"), "passed")
        self.assertIn("VSNR", privacy.get("categories", {}))
        # the summary holds counts, never values
        self.assertNotIn(VSNR, repr(privacy))

    def test_final_gate_blocks_residual_personal_data(self) -> None:
        # Force the final gate: even after pseudonymization something personal survives.
        class StubAirlock:
            def pseudonymize(self, obj):
                return obj, {"policy_version": "test", "key_source": "test", "categories": {}, "total": 0}

            def check_clean(self, text, allow_specimen=False):
                from privacy.schleuse import Hit
                return [Hit("VSNR", 0, 5)]

        with mock.patch.object(chat, "Schleuse", StubAirlock):
            reply = self._turn(MESSAGE)
        self.assertTrue(reply.degraded)
        self.assertIn("privacy airlock", " ".join(reply.agent_run["validation_errors"]))
        self.assertEqual(reply.agent_run["result"].get("privacy", {}).get("airlock"), "blocked")

    def test_fail_closed_without_airlock_module(self) -> None:
        with mock.patch.object(chat, "Schleuse", None):
            reply = self._turn(MESSAGE)
        self.assertTrue(reply.degraded)
        self.assertIn("fail closed", " ".join(reply.agent_run["validation_errors"]))

    def test_injected_gateway_skips_airlock(self) -> None:
        # Offline/test path: an injected gateway is by definition not external network;
        # the airlock must not rewrite the payload in that case.
        seen = {}

        def gateway(endpoint, model, system_prompt, messages, token=None, timeout=25):
            seen["content"] = messages[0]["content"]
            return '{"utterance": "ok", "confidence": "unknown", "citations": []}'

        reply = chat.turn(MESSAGE, STATE, corpus_hits=[], history=[], gateway=gateway)
        self.assertFalse(reply.degraded)
        self.assertIn(VSNR, seen["content"])
        self.assertIsNone(reply.agent_run["result"].get("privacy"))


class PrivacyStatusTests(unittest.TestCase):
    def test_status_honest_and_value_free(self) -> None:
        status = webserver.privacy_status()
        self.assertTrue(status["ok"])
        self.assertTrue(status["active"])
        self.assertIn("policy_version", status)
        self.assertIn("hessian_ai", status["destinations"])
        self.assertIn("langfuse", status["destinations"])
        self.assertIsInstance(status["key_configured"], bool)
        # no key material, no detector internals in the payload
        self.assertNotIn("sk-", repr(status))

    def test_status_without_privacy_module(self) -> None:
        import sys
        with mock.patch.dict(sys.modules, {"privacy.schleuse": None}):
            status = webserver.privacy_status()
        self.assertFalse(status["ok"])
        self.assertIn("fail closed", status["reason"])


if __name__ == "__main__":
    unittest.main()
