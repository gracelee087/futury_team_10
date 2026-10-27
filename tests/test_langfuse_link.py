"""Langfuse link for the SÜSIE chat: fail-soft without keys, chat command shows datasets and a case link."""
import unittest
from unittest import mock

from itsg import chat, langfuse_link


class LangfuseLinkTest(unittest.TestCase):
    def test_no_keys_means_off(self):
        with mock.patch.dict("os.environ", {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}):
            self.assertIsNone(langfuse_link.summary())
            self.assertIsNone(langfuse_link.trace_chat("s", "hallo", "hi"))

    def test_chat_command_without_connection(self):
        with mock.patch.object(langfuse_link, "summary", return_value=None):
            reply = chat.deterministic_turn("Was ist in Langfuse?", {}, task_id="T", session_id="s")
        self.assertIn("nicht verbunden", reply.utterance)

    def test_chat_command_lists_datasets_and_case_link(self):
        info = {"host": "https://lf", "datasets": [
                    {"name": "team10-dbvo-v1", "label": "Krankengeld / Vorerkrankung (41)", "items": 300, "url": "https://lf/d1"},
                    {"name": "team10-maternity-v1", "label": "Mutterschaftsgeld (03)", "items": None, "url": None}],
                "scores": {"case_correct": {"true": 299, "false": 1}, "false_alarm": {"true": 0, "false": 130}}}
        with mock.patch.object(langfuse_link, "summary", return_value=info), \
                mock.patch.object(langfuse_link, "item_url", return_value="https://lf/item/OUT-041"):
            reply = chat.deterministic_turn("show langfuse for OUT-041", {}, task_id="T", session_id="s")
        ut = reply.utterance
        self.assertIn("300 cases — https://lf/d1", ut)
        self.assertIn("missing", ut)
        self.assertNotIn("299", ut)   # all-run score totals are not shown (they mix old runs)
        self.assertIn("OUT-041: https://lf/item/OUT-041", ut)
        self.assertEqual(reply.agent_run["result"]["deterministic_command"], "langfuse")


if __name__ == "__main__":
    unittest.main()
