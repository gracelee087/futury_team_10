"""Unit tests for privacy/schleuse.py. Synthetic values only."""
import json
import logging
import re
from pathlib import Path

import pytest

from privacy import schleuse
from privacy.schleuse import (Hit, LogFilter, PrivacyBlocked, PrivacyConfigError, Schleuse, apply_policy,
                              check_clean, pseudonymize, scrub_for_log)

KEY = "unit-test-key-0123456789"
TEEL0 = Path(__file__).resolve().parent.parent / "ITSG Files" / "TEEL0-Test1-DBVO"


def clean(text):
    return pseudonymize(text, KEY)[0]


# ---------------------------------------------------------------- detectors

def test_vsnr_is_replaced_and_birth_date_is_derived():
    out = clean("Nummer 17241280Q497, Eintrag 19801224 und 24.12.1980.")
    assert "17241280Q497" not in out and "19801224" not in out and "24.12.1980" not in out
    assert "VSNR_1" in out and out.count("DOB_1") == 2


def test_vsnr_with_impossible_birth_date_is_not_flagged():
    assert check_clean("Kennung 17321380Q497 und 17001280Q497") == []  # month 13, day 00


def test_vsnr_with_spaces():
    assert "VSNR_1" in clean("VSNR 17 241280 Q 497 bitte pruefen")


def test_au_dates_abgabegrund_and_section_numbers_are_not_personal():
    text = "AU von 20260311 bis 20260320 (11.03.2026), Abgabegrund 41, DSID 11111111-2222-AAAA-EEEE-111111111111, Punkt 3.1.18, DBVO."
    assert pseudonymize(text, KEY)[0] == text
    assert check_clean(text) == []


def test_iban_needs_a_valid_checksum():
    assert "IBAN_1" in clean("Konto DE89 3704 0044 0532 0130 00 bitte")
    assert "IBAN_1" in clean("Konto DE89370400440532013000.")
    assert "IBAN" not in clean("Konto DE89 3704 0044 0532 0130 01 bitte")  # wrong check digits
    assert "IBAN" not in clean("Order DE12 abcd")


def test_email_and_phone_formats():
    text = ("Mail max.beispiel@example.org, Tel 069/8700, +49 171 1234567, 0171-9876543, (0221) 123456, "
            "+49 (0)30 1234567, Telefon: 040 123456")
    out = clean(text)
    assert "@" not in out and out.count("PHONE_") >= 6
    assert not re.search(r"\d{4}", out.replace("PHONE_", ""))


def test_field_ranges_and_dates_are_not_phone_numbers():
    text = "Felder 031-048 und 014-060, Datum 05.03.2026, Zeit 12:30, Satzart 0000000012587964"
    assert check_clean(text) == []


def test_birth_date_only_with_cue_or_from_vsnr():
    assert "DOB_1" in clean("geboren am 03.04.1985")
    assert "DOB_1" in clean("Geburtsdatum: 1985-04-03")
    assert "DOB_1" in clean("Frau Meier, geb. 03.04.85")
    assert clean("Beginn am 03.04.2026") == "Beginn am 03.04.2026"
    assert clean("geboren am 31.02.1985") == "geboren am 31.02.1985"  # not a real date


def test_betriebsnummer_needs_context_or_dta_header():
    assert "BBNR_1" in clean("Betriebsnummer des Arbeitgebers: 12345678")
    assert clean("Zahl 12345678 steht hier") == "Zahl 12345678 steht hier"
    out = clean("DSLWLEIST99302811       00000000  rest 99302811")
    assert "99302811" not in out and out.count("BBNR_1") == 2


def test_names_from_cues():
    for text in ("Frau Anna Meier ruft an", "Herr Dr. Hans Weber ruft an", "Name: Lukas Brandt", "Der Versicherte Jonas Keller ruft an",
                 "FAMILIENNAME=Schäfer VORNAME=Birgit", "mein Name ist Svenja Roth"):
        out, summary = pseudonymize(text, KEY)
        assert "PERSON_" in out, text
    out = clean("FAMILIENNAME=Schäfer VORNAME=Birgit EMAIL=a.b@example.org")
    assert "Schäfer" not in out and "Birgit" not in out and "EMAIL_1" in out


def test_common_nouns_after_cue_words_are_not_names():
    assert check_clean("Der Versicherte Person Datensatz") == []
    assert check_clean("Name | Vorname | Geburtsdatum") == []
    assert check_clean("wenn eine Frau Mutterschaftsgeld beantragt") == []
    assert check_clean("Verordnung für schwangere Frau Arznei-, Verband- und Heilmittel") == []


def test_name_found_once_is_replaced_everywhere_including_genitive():
    out = clean("Frau Meier hat angerufen. Meiers Antrag liegt vor. MEIER wartet.")
    assert "Meier" not in out and "MEIER" not in out


def test_address_lines():
    out = clean("Hauptstraße 5a, 50667 Köln und Am Mühlenberg 12 sowie Bahnhofstr. 7")
    assert "Hauptstraße" not in out and "50667" not in out and "Mühlenberg" not in out and "Bahnhofstr" not in out


def test_rulebook_words_that_look_like_addresses_are_kept():
    text = "Im Abschnitt 4 steht: In der Tabelle 3 maximal 10000 Zeichen, Rechtsweg und Arbeitsplatz."
    assert check_clean(text) == []


# ---------------------------------------------------------------- DTA records

@pytest.mark.skipif(not TEEL0.exists(), reason="TEEL0 test file not in this checkout")
def test_teel0_file_is_fully_cleaned():
    text = TEEL0.read_bytes().decode("latin-1")
    sch = Schleuse(KEY)
    out, summary = sch.pseudonymize(text)
    for secret in ("17241280Q497", "19801224", "Mustermann", "Peter", "Testfrau", "Mia", "systemuntersuchung",
                   "069/8700", "069-8700", "99302811", "Offenbach", "63067", "Kaiserleistra"):
        assert secret not in out, secret
    for kept in ("20260311", "20260214", "N41001J", "DBVO", "DBNA", "DBAP", "11111111-2222-AAAA-EEEE-111111111111"):
        assert kept in out, kept
    assert sch.check_clean(out) == []
    assert set(summary["categories"]) == {"VSNR", "DOB", "BBNR", "PERSON", "EMAIL", "PHONE", "ADDRESS"}


def test_record_dict_with_name_fields():
    record = {"FAMILIENNAME": "Müller-Schmidt", "VORNAME": "Jürgen", "note": "Jürgen ruft an, Müller-Schmidt ist krank",
              "AU-AB-AG": "20260311", "rows": [{"NACHNAME": "Kowalski", "x": "Kowalski"}]}
    out, summary = pseudonymize(record, KEY)
    flat = json.dumps(out, ensure_ascii=False)
    for secret in ("Müller-Schmidt", "Jürgen", "Kowalski"):
        assert secret not in flat
    assert out["AU-AB-AG"] == "20260311"
    assert summary["categories"]["PERSON"] >= 5


# ---------------------------------------------------------------- tokens, summary, gate

def test_same_value_same_token_different_value_different_token():
    sch = Schleuse(KEY)
    a, _ = sch.pseudonymize("Mail x.y@example.org und wieder X.Y@example.org, dann z@example.org")
    assert a == "Mail EMAIL_1 und wieder EMAIL_1, dann EMAIL_2"
    b, _ = sch.pseudonymize("noch einmal x.y@example.org")
    assert b == "noch einmal EMAIL_1"  # stable across calls inside one run


def test_summary_has_counts_only_and_no_values():
    out, summary = pseudonymize("Frau Anna Meier, 17241280Q497, a@example.org", KEY)
    assert summary["categories"] == {"PERSON": 1, "VSNR": 1, "EMAIL": 1} and summary["total"] == 3
    blob = json.dumps(summary)
    assert "Meier" not in blob and "17241280Q497" not in blob and KEY not in blob


def test_hit_has_no_value_field():
    hits = check_clean("Mail a@example.org")
    assert hits and isinstance(hits[0], Hit)
    assert not hasattr(hits[0], "value") and "example" not in repr(hits[0])


def test_check_clean_second_pass_knows_values_seen_in_the_run():
    sch = Schleuse(KEY)
    sch.pseudonymize("Frau Anna Meier ruft an")
    assert sch.check_clean("PERSON_1 ruft an") == []
    assert sch.check_clean("später: Anna Meier schreibt") != []  # a value already seen must not reappear


def test_check_clean_specimen_values_only_when_allowed():
    text = "Beispiel: Name: Max Mustermann"
    assert check_clean(text) != []
    assert check_clean(text, allow_specimen=True) == []


def test_restore_maps_tokens_back_only_when_kept():
    sch = Schleuse(KEY, keep_reverse=True)
    out, _ = sch.pseudonymize("Frau Anna Meier, a@example.org")
    assert sch.restore(f"Zu {out.split(',')[0].split()[-1]} und EMAIL_1 und PERSON_9") == "Zu Anna Meier und a@example.org und PERSON_9"
    assert Schleuse(KEY).restore("PERSON_1") == "PERSON_1"


# ---------------------------------------------------------------- key

def test_key_from_env_and_checks(monkeypatch):
    monkeypatch.setenv("PRIVACY_KEY", "x" * 20)
    assert schleuse.get_key() == (b"x" * 20, "env")
    monkeypatch.setenv("PRIVACY_KEY", "short")
    with pytest.raises(PrivacyConfigError):
        schleuse.get_key()
    monkeypatch.delenv("PRIVACY_KEY")
    key, source = schleuse.get_key()
    assert source == "ephemeral" and len(key) == 32


def test_key_changes_the_digest_but_not_the_tokens():
    a, b = Schleuse("a" * 20), Schleuse("b" * 20)
    assert a._digest("EMAIL", "x@example.org") != b._digest("EMAIL", "x@example.org")
    assert a.pseudonymize("x@example.org")[0] == b.pseudonymize("x@example.org")[0] == "EMAIL_1"


# ---------------------------------------------------------------- logs and policy

def test_scrub_for_log_removes_everything():
    out = scrub_for_log("Frau Anna Meier 17241280Q497 a@example.org 069/8700")
    assert out == "Frau [PERSON] [VSNR] [EMAIL] [PHONE]"


def test_log_filter_scrubs_message_args_and_exceptions():
    logger = logging.getLogger("test.privacy.filter")
    logger.addFilter(LogFilter())
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(handler.format(record))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("question: %s", "Frau Anna Meier 17241280Q497")
    try:
        raise ValueError("a@example.org")
    except ValueError:
        logger.exception("failed for a@example.org")
    blob = "\n".join(records)
    assert "Meier" not in blob and "17241280Q497" not in blob and "example.org" not in blob
    assert "ValueError" in blob


def test_policy_hessian_ai_pseudonymizes_and_blocks_unknown_destinations():
    safe, summary = apply_policy("hessian_ai", "Frau Anna Meier fragt", KEY)
    assert safe == "Frau PERSON_1 fragt" and summary["mode"] == "pseudonymize"
    with pytest.raises(PrivacyBlocked):
        apply_policy("somewhere_else", "x", KEY)


def test_policy_seal_hash_only():
    a, _ = apply_policy("seal", {"result": "Anna Meier"}, KEY)
    b, _ = apply_policy("seal", {"result": "Anna Meier"}, KEY)
    c, _ = apply_policy("seal", {"result": "Anna Meyer"}, KEY)
    assert a == b != c and a.startswith("hmac-sha256:") and "Meier" not in a


def test_policy_langfuse_minimizes():
    payload = {"run_id": "RUN-1", "status": "PASS", "raw": "Frau Anna Meier", "rule": "x" * 500}
    safe, _ = apply_policy("langfuse", payload, KEY)
    assert set(safe) == {"run_id", "status", "rule"} and len(safe["rule"]) < 260


def test_policy_logs_has_no_personal_data():
    safe, _ = apply_policy("logs", "Frau Anna Meier a@example.org")
    assert safe == "Frau [PERSON] [EMAIL]"
