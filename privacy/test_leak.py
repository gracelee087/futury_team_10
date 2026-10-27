"""Tests around privacy/leak_test.py: the generated records must not leak, the real TEEL0 file must not reach the model."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "retrieval"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import leak_test  # noqa: E402
from ask import ask  # noqa: E402
from search import Chunk  # noqa: E402

TEEL0 = ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"
NEUTRAL = Chunk(chunk_id="GG_EEL/2.1.2", doc="GG_EEL", version="13.1", section="2.1.2", title="Anforderung", page_start=7,
                page_end=8, abgabegrund=("41",), datenbaustein=("DBVO",), text="Die Anforderung erfolgt mit dem Abgabegrund 41.")


def test_generated_records_are_deterministic_and_varied():
    a, b = leak_test.make_records(50), leak_test.make_records(50)
    assert [r.text for r in a] == [r.text for r in b]
    assert len(a) == 50 and sum(len(r.planted) for r in a) > 150
    assert {c for r in a for c, _ in r.planted} == {"VSNR", "PERSON", "IBAN", "EMAIL", "PHONE", "DOB", "ADDRESS", "BBNR"}


def test_no_planted_value_leaks_to_model_logs_or_audit():
    leaks, stats = leak_test.run_records(leak_test.make_records(50))
    assert leaks == []
    assert stats["blocked"] == 0 and stats["answered_not_found"] == 50


def test_leak_detector_would_notice_a_leak():
    assert leak_test._leaked("VSNR", "17241280Q497", "x 17 241280 q497 y")
    assert leak_test._leaked("PERSON", "Anna Meier", "ruft Meier an")
    assert not leak_test._leaked("PERSON", "Anna Meier", "ruft PERSON_1 an")


@pytest.mark.skipif(not TEEL0.exists(), reason="TEEL0 test file not in this checkout")
def test_real_teel0_file_never_reaches_the_fake_model(monkeypatch):
    monkeypatch.setenv("PRIVACY_KEY", leak_test.TEST_KEY)
    text = TEEL0.read_bytes().decode("latin-1")
    client = leak_test.RecordingClient()
    result = ask("Was bedeutet Abgabegrund 41 in diesem Datensatz?\n" + text, [NEUTRAL], client)
    sent = "\n".join(client.payloads)
    assert result.status == "NOT_FOUND" and len(client.payloads) == 1
    for secret in ("17241280Q497", "Mustermann", "Peter", "Testfrau", "Mia", "systemuntersuchung@gmx.de",
                   "systemuntersuchung@itsg.de", "19801224", "99302811"):
        assert not re.search(r"(?<![A-Za-z0-9])" + re.escape(secret), sent), secret
    assert "20260311" in sent and "N41001J" in sent  # AU dates and the Abgabegrund field are kept
