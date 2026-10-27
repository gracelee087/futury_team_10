"""Privacy airlock inside ask(): T10-007. No network; the model is a recording fake."""
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ask as ask_mod  # noqa: E402
from ask import ask  # noqa: E402
from privacy import schleuse  # noqa: E402
from search import Chunk  # noqa: E402

KEY = "integration-test-key-0123"
RULE = "Die Anforderung der Vorerkrankungszeiten erfolgt mit dem Abgabegrund 41."


def chunk(text=RULE, cid="GG_EEL/2.1.2", title="Anforderung"):
    return Chunk(chunk_id=cid, doc="GG_EEL", version="13.1", section="2.1.2", title=title, page_start=7,
                 page_end=8, abgabegrund=("41",), datenbaustein=("DBVO",), text=text)


class Recorder:
    def __init__(self, answer="Keine Regel fuer PERSON_1 und PERSON_9", status="NOT_FOUND", citations=()):
        self.calls = []
        self._reply = json.dumps({"answer": answer, "status": status, "citations": list(citations)})
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(json.dumps(kwargs, ensure_ascii=False))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._reply))], model="fake")


@pytest.fixture(autouse=True)
def privacy_key(monkeypatch):
    monkeypatch.setenv("PRIVACY_KEY", KEY)


def test_personal_data_in_question_never_reaches_the_model():
    client = Recorder()
    result = ask("Frau Anna Meier (VSNR 17241280Q497, a.meier@example.org) fragt zu Abgabegrund 41", [chunk()], client)
    sent = "".join(client.calls)
    for secret in ("Meier", "17241280Q497", "example.org", "Anna"):
        assert secret not in sent
    assert "PERSON_1" in sent and "VSNR_1" in sent and "EMAIL_1" in sent
    assert result.status == "NOT_FOUND"


def test_answer_maps_tokens_back_only_for_values_from_the_question():
    client = Recorder(answer="Keine Regel fuer PERSON_1 und PERSON_9")
    result = ask("Frau Anna Meier fragt zu Abgabegrund 41", [chunk()], client)
    assert result.answer == "Keine Regel fuer Anna Meier und PERSON_9"  # PERSON_9 was never in the question


def test_audit_has_privacy_counts_and_policy_version_but_no_values():
    client = Recorder()
    result = ask("Frau Anna Meier, 17241280Q497, a@example.org", [chunk()], client)
    privacy = result.audit["privacy"]
    assert privacy["policy_version"] == schleuse.POLICY_VERSION and privacy["blocked"] is False
    assert privacy["categories_removed"] == {"PERSON": 1, "VSNR": 1, "EMAIL": 1}
    blob = json.dumps(result.audit)
    assert "Meier" not in blob and "17241280Q497" not in blob and KEY not in blob


def test_question_without_personal_data_is_unchanged():
    client = Recorder()
    ask("Wann wird der Abgabegrund 41 verwendet? AU 20260311, Punkt 3.1.18", [chunk()], client)
    assert "Wann wird der Abgabegrund 41 verwendet? AU 20260311, Punkt 3.1.18" in client.calls[0]


def test_blocked_when_a_chunk_contains_personal_data_and_no_api_call():
    client = Recorder()
    result = ask("Abgabegrund 41?", [chunk(text="Rueckfragen an Frau Anna Meier, a.meier@example.org")], client)
    assert result.status == "BLOCKED" and client.calls == []
    assert "Meier" not in result.answer and result.audit["privacy"]["blocked"] is True
    assert result.audit["privacy"]["blocked_categories"] == ["EMAIL", "PERSON"]


def test_blocked_when_check_clean_still_finds_something(monkeypatch):
    monkeypatch.setattr(schleuse.Schleuse, "check_clean", lambda self, text, allow_specimen=False: [schleuse.Hit("PERSON", 0, 3)])
    client = Recorder()
    result = ask("Frau Anna Meier fragt", [chunk()], client)
    assert result.status == "BLOCKED" and client.calls == []
    assert "still present" in result.validation_errors[0]


def test_blocked_without_search_or_key_when_privacy_key_is_invalid(monkeypatch):
    monkeypatch.setenv("PRIVACY_KEY", "short")
    client = Recorder()
    result = ask("Abgabegrund 41?", [chunk()], client)
    assert result.status == "BLOCKED" and client.calls == []


def test_public_specimen_values_in_chunks_do_not_block():
    client = Recorder()
    result = ask("Abgabegrund 41?", [chunk(text="Beispiel: Name: Max Mustermann, Musterstraße 1")], client)
    assert result.status == "NOT_FOUND" and len(client.calls) == 1


def test_log_line_of_the_ask_logger_is_scrubbed(caplog):
    with caplog.at_level(logging.INFO, logger="retrieval.ask"):
        logging.getLogger("retrieval.ask").info("question was %s", "Frau Anna Meier 17241280Q497")
    assert "Meier" not in caplog.text and "17241280Q497" not in caplog.text and "[VSNR]" in caplog.text
