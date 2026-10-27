"""T10-008: privacy gate + provider switch in orchestrator/llm.py. Run: python -m pytest orchestrator -q
Recording fakes only: no network, no API key."""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT)]
import llm  # noqa: E402
from privacy import schleuse  # noqa: E402

TEEL0 = ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"
SECRETS = ("17241280Q497", "Mustermann", "Peter", "Testfrau", "Mia", "systemuntersuchung@gmx.de",
           "systemuntersuchung@itsg.de", "069/8700", "19801224", "99302811")
SYSTEM = 'Answer in JSON only: {"ok": true}'
pytestmark = pytest.mark.skipif(not TEEL0.exists(), reason="TEEL0 test file not in this checkout")


def leaked(text):
    return [s for s in SECRETS if s in text]   # plain substring: stricter than a word-boundary search


def payload():
    return "Pruefe diesen Datensatz:\n" + TEEL0.read_bytes().decode("latin-1")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("TEAM10_MOCK", "LANGFUSE_PUBLIC_KEY", "TEAM10_HESSIAN_MODEL", "TEAM10_HESSIAN_MODEL_LIGHT", "HESSIAN_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PRIVACY_KEY", "k" * 32)
    monkeypatch.setattr(llm, "PROVIDER", "anthropic")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_hessian_client", None)
    monkeypatch.setattr(llm, "_guard", None)


# ---------------------------------------------------------------- fakes
class FakeAnthropic:
    def __init__(self, text='{"ok": true}', stop="end_turn"):
        self.sent, self._text, self._stop = [], text, stop
        self.messages = self

    def stream(self, **kw):
        self.sent.append(json.dumps(kw, ensure_ascii=False))
        reply = SimpleNamespace(stop_reason=self._stop, usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                                content=[SimpleNamespace(type="text", text=self._text)])
        outer = self

        class Ctx:
            def __enter__(self): return outer
            def __exit__(self, *a): return False
        outer.get_final_message = lambda: reply
        return Ctx()


class FakeHessian:
    def __init__(self, text='{"ok": true}', error=None):
        self.sent, self._text, self._error = [], text, error
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.sent.append(json.dumps(kw, ensure_ascii=False))
        if self._error:
            raise RuntimeError(self._error)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._text), finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class FakeLangfuse:
    def __init__(self):
        self.calls = []

    def start_as_current_generation(self, **kw):
        self.calls.append(("start", kw))
        outer = self

        class Gen:
            def __enter__(self): return SimpleNamespace(update=lambda **u: outer.calls.append(("update", u)))
            def __exit__(self, *a): return False
        return Gen()

    def everything(self):
        return json.dumps(self.calls, ensure_ascii=False, default=str)


def mock_recording(seen):
    def mock(user):
        seen.append(user)
        return {"ok": True}
    return mock


# ---------------------------------------------------------------- the TEEL0 payload really contains the secrets
def test_the_test_payload_is_personal():
    assert set(leaked(payload())) >= {"17241280Q497", "Mustermann", "Testfrau", "systemuntersuchung@gmx.de"}


# ---------------------------------------------------------------- gate, mock mode
def test_mock_mode_the_mock_never_sees_personal_data(monkeypatch):
    monkeypatch.setenv("TEAM10_MOCK", "1")
    seen = []
    assert llm.call("a", "light", SYSTEM, payload(), mock_recording(seen)) == {"ok": True}
    assert len(seen) == 1 and leaked(seen[0]) == []
    assert "20260311" in seen[0] and "N41001J" in seen[0]   # AU dates / Abgabegrund stay (not personal)


def test_broken_mock_still_fails_closed(monkeypatch):
    monkeypatch.setenv("TEAM10_MOCK", "broken")
    with pytest.raises(llm.AgentError):
        llm.call("a", "light", SYSTEM, payload(), lambda u: {"ok": True})


# ---------------------------------------------------------------- gate, real call path (fake client)
def test_anthropic_path_nothing_personal_reaches_the_model(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(llm, "_client", fake)
    assert llm.call("a", "light", SYSTEM, payload(), lambda u: {}) == {"ok": True}
    assert len(fake.sent) == 1 and leaked(fake.sent[0]) == []
    assert "claude-haiku-5-5" in fake.sent[0]   # default provider and models unchanged


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("TEAM10_LLM_PROVIDER", raising=False)
    assert importlib.reload(llm).PROVIDER == "anthropic"


def test_langfuse_generation_input_and_output_are_clean(monkeypatch):
    fake, lf = FakeAnthropic(text=json.dumps({"echo": "17241280Q497 systemuntersuchung@gmx.de"})), FakeLangfuse()
    monkeypatch.setattr(llm, "_client", fake)
    monkeypatch.setattr(llm, "lf_client", lambda: lf)
    llm.call("a", "light", SYSTEM, payload(), lambda u: {})
    assert [c[0] for c in lf.calls].count("update") >= 2
    assert leaked(lf.everything()) == [], leaked(lf.everything())
    updates = {k: v for kind, u in lf.calls if kind == "update" for k, v in u.items()}
    assert "input" in updates and "output" in updates and llm.langfuse_guard().all_clean


# ---------------------------------------------------------------- leftovers -> BLOCKED, no model call
def test_leftover_personal_data_blocks_before_any_model_call(monkeypatch):
    fake, lf = FakeAnthropic(), FakeLangfuse()
    monkeypatch.setattr(llm, "_client", fake)
    monkeypatch.setattr(llm, "lf_client", lambda: lf)
    # simulate a detector gap: pseudonymize leaves the text as it is, check_clean still finds the VSNR
    monkeypatch.setattr(schleuse.Schleuse, "pseudonymize", lambda self, obj: (obj, {"categories": {}}))
    with pytest.raises(llm.PrivacyBlockedError) as err:
        llm.call("a", "light", SYSTEM, payload(), lambda u: {})
    assert isinstance(err.value, llm.AgentError) and "VSNR" in str(err.value)
    assert fake.sent == [] and leaked(str(err.value)) == []
    assert leaked(lf.everything()) == []   # Langfuse saw the error, never the payload


def test_personal_data_in_the_system_prompt_blocks(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(llm, "_client", fake)
    with pytest.raises(llm.PrivacyBlockedError):
        llm.call("a", "light", SYSTEM + " Versicherungsnummer 17241280Q497", "hello", lambda u: {})
    assert fake.sent == []


def test_invalid_privacy_key_blocks_instead_of_sending(monkeypatch):
    monkeypatch.setenv("PRIVACY_KEY", "short")
    fake = FakeAnthropic()
    monkeypatch.setattr(llm, "_client", fake)
    with pytest.raises(llm.PrivacyBlockedError):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})
    assert fake.sent == []


# ---------------------------------------------------------------- provider switch
def test_hessian_provider_uses_env_model_and_the_same_gate(monkeypatch):
    fake = FakeHessian()
    monkeypatch.setattr(llm, "PROVIDER", "hessian")
    monkeypatch.setattr(llm, "_hessian_client", fake)
    monkeypatch.setenv("TEAM10_HESSIAN_MODEL", "vllm/test-author")
    monkeypatch.setenv("TEAM10_HESSIAN_MODEL_LIGHT", "vllm/test-light")
    assert llm.call("a", "light", SYSTEM, payload(), lambda u: {}) == {"ok": True}
    assert llm.call("b", "author", SYSTEM, payload(), lambda u: {}) == {"ok": True}
    assert '"model": "vllm/test-light"' in fake.sent[0] and '"model": "vllm/test-author"' in fake.sent[1]
    assert all(leaked(s) == [] for s in fake.sent)
    assert llm.HESSIAN_URL == "https://hip-gw.hessian.ai/v1"


def test_hessian_light_model_falls_back_to_the_author_model(monkeypatch):
    fake = FakeHessian()
    monkeypatch.setattr(llm, "PROVIDER", "hessian")
    monkeypatch.setattr(llm, "_hessian_client", fake)
    monkeypatch.setenv("TEAM10_HESSIAN_MODEL", "vllm/only")
    llm.call("a", "light", SYSTEM, "hello", lambda u: {})
    assert '"model": "vllm/only"' in fake.sent[0]


def test_hessian_without_model_or_key_fails_closed(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "hessian")
    with pytest.raises(llm.AgentError, match="TEAM10_HESSIAN_MODEL"):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})
    monkeypatch.setenv("TEAM10_HESSIAN_MODEL", "vllm/x")
    with pytest.raises(llm.AgentError, match="HESSIAN_API_KEY"):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "other")
    with pytest.raises(llm.AgentError, match="TEAM10_LLM_PROVIDER"):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})


def test_provider_error_text_is_scrubbed(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "hessian")
    monkeypatch.setattr(llm, "_hessian_client", FakeHessian(error="bad request for 17241280Q497"))
    monkeypatch.setenv("TEAM10_HESSIAN_MODEL", "vllm/x")
    with pytest.raises(llm.AgentError) as err:
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})
    assert "17241280Q497" not in str(err.value)


def test_malformed_answer_and_refusal_are_agent_errors(monkeypatch):
    monkeypatch.setattr(llm, "_client", FakeAnthropic(text="no json here"))
    with pytest.raises(llm.AgentError):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})
    monkeypatch.setattr(llm, "_client", FakeAnthropic(stop="refusal"))
    with pytest.raises(llm.AgentError):
        llm.call("a", "light", SYSTEM, "hello", lambda u: {})
