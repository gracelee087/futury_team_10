"""Hermetic tests for the encrypted secrets store and the LLM client boundary.

No test contacts the network and none touches the real store under
data/secrets — the store is exercised in a temp directory with an env
passphrase; the client is exercised only on its fail-closed paths.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from itsg.candidates import ROLE_REQUIREMENT_EXTRACTOR
from itsg.llm import (
    LLMError,
    ROLE_MODELS,
    ROLE_TEST_CASE_DESIGNER,
    ROLE_TEST_CHALLENGER,
    extract_json_payload,
    resolve_token,
    run_role,
    validate_endpoint,
)
from itsg.secrets import SecretsStore


class TestSecretsStore(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        self._old_env = dict(os.environ)
        os.environ["SUSIE_SECRETS_PASSPHRASE"] = "test-passphrase-1234"
        os.environ.pop("SUSIE_LLM_TOKEN", None)

    def tearDown(self):
        self._dir.cleanup()
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_roundtrip_and_isolation(self):
        path = self.root / "store.json"
        store = SecretsStore(path=path, prompt=False)
        store.set("LLM_API_KEY", "sk-test-value")
        self.assertTrue(path.exists())
        self.assertEqual(SecretsStore(path=path).get("LLM_API_KEY"), "sk-test-value")
        # ciphertext must not contain the plaintext
        self.assertNotIn("sk-test-value", path.read_text(encoding="utf-8"))

    def test_wrong_passphrase_fails_closed(self):
        path = self.root / "store.json"
        SecretsStore(path=path).set("S", "v")
        os.environ["SUSIE_SECRETS_PASSPHRASE"] = "wrong"
        with self.assertRaises(Exception):
            SecretsStore(path=path).get("S")

    def test_overwrite_without_passphrase_refused(self):
        path = self.root / "store.json"
        store = SecretsStore(path=path)
        store.set("A", "1")
        os.environ["SUSIE_SECRETS_PASSPHRASE"] = "other-passphrase"
        with self.assertRaises(ValueError):
            store.set("B", "2")  # cannot decrypt existing payload — refuse, never clobber

    def test_names_and_missing_secret(self):
        path = self.root / "store.json"
        store = SecretsStore(path=path)
        store.set("A", "1")
        self.assertEqual(store.names(), ["A"])
        with self.assertRaises(KeyError):
            store.get("B")


class TestEndpointPolicy(unittest.TestCase):
    def test_public_https_accepted(self):
        self.assertEqual(
            validate_endpoint("https://hip-gw.hessian.ai/v1/chat/completions"),
            "https://hip-gw.hessian.ai/v1/chat/completions",
        )

    def test_private_and_reserved_refused(self):
        for url in ("http://127.0.0.1:8000/v1", "https://localhost/v1", "https://10.0.0.1/v1",
                    "https://192.168.1.4/v1", "https://169.254.169.254/meta",
                    "https://100.64.0.1/v1", "http://0.0.0.0/v1", "ftp://example.com/v1"):
            with self.assertRaises(LLMError, msg=url):
                validate_endpoint(url)


class TestResponseContract(unittest.TestCase):
    def test_extracts_fenced_json_and_strips_thinking(self):
        raw = "<think>internal</think>```json\n{\"requirements\": []}\n```"
        self.assertEqual(extract_json_payload(raw), '{"requirements": []}')

    def test_empty_content_raises(self):
        with self.assertRaises(LLMError):
            extract_json_payload("")


class TestFailClosedClient(unittest.TestCase):
    def test_role_model_assignment(self):
        self.assertEqual(ROLE_MODELS[ROLE_TEST_CASE_DESIGNER], "vllm/Kolibri-1")
        self.assertEqual(ROLE_MODELS[ROLE_REQUIREMENT_EXTRACTOR], "vllm/GLM-Flash:Latest")
        self.assertEqual(ROLE_MODELS[ROLE_TEST_CHALLENGER], "vllm/GLM-Flash:Latest")

    def test_chat_completion_refuses_private_endpoint(self):
        from itsg import llm
        with self.assertRaises(llm.LLMError):
            llm.chat_completion("http://127.0.0.1:9/v1", "m", "sys",
                                [{"role": "user", "content": "hi"}], token="t")

    def test_assistant_role_maps_to_glm_flash(self):
        from itsg import llm, candidates
        self.assertEqual(
            llm.ROLE_MODELS[candidates.ROLE_SUSIE_ASSISTANT], "vllm/GLM-Flash:Latest")

    def test_no_credentials_yields_error_run_without_network(self):
        run = run_role(ROLE_REQUIREMENT_EXTRACTOR, "T10-018", ["SRCV-X"], "content",
                       store_path="/nonexistent/secrets.json")
        self.assertEqual(run.status, "error")
        self.assertTrue(any("credentials" in e for e in run.validation_errors))
        self.assertTrue(run.review_required)

    def test_env_token_precedes_store(self):
        os.environ["SUSIE_LLM_TOKEN"] = "env-token"
        try:
            self.assertEqual(resolve_token(store_path="/nonexistent/secrets.json"), "env-token")
        finally:
            os.environ.pop("SUSIE_LLM_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
