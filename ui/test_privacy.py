"""Tests for the privacy endpoints, the BLOCKED answer, and report retention (T10-007, phases C and D)."""
import json
import os
import re
import time
from types import SimpleNamespace

import pytest

from test_server import API_KEY, ROOT, call, mode_box, reports, sample_report, seal, serve, srv, ui  # noqa: F401

EXAMPLE = ("Frau Anna Beispiel (VSNR 12 150685 B 123, anna.beispiel@example.org, Tel. 069/123456) war vom 11.03.2026 "
           "bis 20.03.2026 arbeitsunfähig. Abgabegrund 41.")
SECRETS = ("Anna", "Beispiel", "12 150685 B 123", "anna.beispiel@example.org", "069/123456")


def make(reports, env=None, **kw):
    cfg = ui.Config(root=ROOT, reports_dir=reports, env=env if env is not None else {}, **kw)
    return serve(ui.make_server("127.0.0.1", 0, cfg))


def stop(httpd):
    httpd.shutdown()
    httpd.server_close()


# ---------------------------------------------------------------- preview

def test_preview_cleans_and_never_echoes_the_original(srv):
    status, data = call(srv, "POST", "/api/privacy/preview", {"text": EXAMPLE})
    assert status == 200 and data["blocked"] is False
    blob = json.dumps(data, ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in blob
    assert "20260311" not in blob and "11.03.2026" in data["clean_text"]  # AU dates are kept
    assert "Abgabegrund 41" in data["clean_text"]
    assert data["summary"]["categories"] == {"PERSON": 1, "VSNR": 1, "EMAIL": 1, "PHONE": 1}
    assert data["policy_version"] == "privacy-policy-v1"


def test_preview_blocked_returns_no_text(srv, monkeypatch):
    monkeypatch.setattr(ui.schleuse.Schleuse, "check_clean", lambda self, text, allow_specimen=False: [ui.schleuse.Hit("PERSON", 0, 1)])
    status, data = call(srv, "POST", "/api/privacy/preview", {"text": EXAMPLE})
    assert status == 200 and data["blocked"] is True and data["clean_text"] is None
    assert data["blocked_categories"] == ["PERSON"]
    for secret in SECRETS:
        assert secret not in json.dumps(data, ensure_ascii=False)


def test_preview_validation_and_headers(srv):
    assert call(srv, "POST", "/api/privacy/preview", {"text": "x" * 5001})[0] == 400
    assert call(srv, "POST", "/api/privacy/preview", {"text": ""})[0] == 400
    assert call(srv, "POST", "/api/privacy/preview", {"text": "hi", "extra": 1})[0] == 400
    assert call(srv, "POST", "/api/privacy/preview", {"text": "hi"}, post_headers=False)[0] == 403
    assert call(srv, "GET", "/api/privacy/preview")[0] == 405


def test_preview_is_rate_limited(reports):
    httpd = make(reports)
    try:
        codes = [call(httpd, "POST", "/api/privacy/preview", {"text": "hallo"})[0] for _ in range(22)]
        assert codes[:20] == [200] * 20 and codes[20:] == [429, 429]
    finally:
        stop(httpd)


def test_preview_with_invalid_key_is_a_clear_error(reports):
    httpd = make(reports, {"PRIVACY_KEY": "short"})
    try:
        status, data = call(httpd, "POST", "/api/privacy/preview", {"text": "hallo"})
        assert status == 503 and "PRIVACY_KEY" in data["error"] and "short" not in data["error"].replace("PRIVACY_KEY", "")
    finally:
        stop(httpd)


def test_no_original_value_or_key_in_the_log(srv, caplog):
    caplog.set_level("DEBUG")
    call(srv, "POST", "/api/privacy/preview", {"text": EXAMPLE})
    for secret in SECRETS:
        assert secret not in caplog.text


# ---------------------------------------------------------------- flows

def test_flows_are_built_from_the_policy_and_config(reports):
    httpd = make(reports, {"PRIVACY_KEY": "k" * 20})
    try:
        status, data = call(httpd, "GET", "/api/privacy/flows")
        assert status == 200
        rows = {f["id"]: f for f in data["flows"]}
        assert set(rows) == {"hessian_ai", "langfuse", "seal", "logs", "reports"}
        assert rows["hessian_ai"]["mode"] == "pseudonymize" and rows["hessian_ai"]["light"] == "green"
        assert rows["langfuse"]["light"] == "green" and "nothing is sent" in rows["langfuse"]["note"]
        assert rows["seal"]["mode"] == "hash_only" and rows["logs"]["mode"] == "none"
        assert data["retention_days"] == 7 and "k" * 20 not in json.dumps(data)
    finally:
        stop(httpd)


def test_flow_lights_change_with_the_configuration(reports):
    cases = [({}, "yellow", "green"), ({"PRIVACY_KEY": "short"}, "red", "green"),
             ({"PRIVACY_KEY": "k" * 20, "LANGFUSE_PUBLIC_KEY": "p", "LANGFUSE_SECRET_KEY": "s"}, "green", "yellow")]
    for env, ai_light, langfuse_light in cases:
        httpd = make(reports, env)
        try:
            rows = {f["id"]: f for f in call(httpd, "GET", "/api/privacy/flows")[1]["flows"]}
            assert (rows["hessian_ai"]["light"], rows["langfuse"]["light"]) == (ai_light, langfuse_light), env
            assert "pk" not in json.dumps(rows) and '"s"' not in json.dumps(rows)
        finally:
            stop(httpd)


# ---------------------------------------------------------------- leak-test result

def test_leaktest_returns_the_stored_result(reports):
    (reports / ui.LEAKTEST_FILE).write_text(json.dumps({"author": {"leaked": 0}}), encoding="utf-8")
    httpd = make(reports)
    try:
        status, data = call(httpd, "GET", "/api/privacy/leaktest")
        assert status == 200 and data["result"]["author"]["leaked"] == 0 and "stored" in data["source"]
    finally:
        stop(httpd)


def test_leaktest_runs_on_demand_when_nothing_is_stored(reports):
    httpd = make(reports)
    try:
        status, data = call(httpd, "GET", "/api/privacy/leaktest")
        assert status == 200 and data["source"] == "run just now"
        result = data["result"]
        assert result["author"]["planted"] > 150 and result["author"]["leaked"] == 0
        assert result["independent"]["planted"] == 19 and result["independent"]["first_run_before_fix"]["caught"] == 18
        assert (reports / ui.LEAKTEST_FILE).exists()
    finally:
        stop(httpd)


# ---------------------------------------------------------------- BLOCKED from /api/ask

def test_ask_returns_blocked_and_never_calls_the_model(reports, monkeypatch):
    from retrieval.ask import ask
    from retrieval.search import Chunk

    calls = []
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw))))
    dirty = Chunk(chunk_id="X/1", doc="X", version="1", section="1", title="t", page_start=1, page_end=1, abgabegrund=(),
                  datenbaustein=(), text="Rueckfragen an Frau Anna Meier, a.meier@example.org")
    httpd = make(reports, {}, ask_fn=lambda question: ask(question, chunks=[dirty], client=client))
    try:
        status, data = call(httpd, "POST", "/api/ask", {"question": "Abgabegrund 41?"})
        assert status == 200 and data["status"] == "BLOCKED" and calls == []
        assert data["audit"]["privacy"]["blocked"] is True and "Meier" not in json.dumps(data)
    finally:
        stop(httpd)


# ---------------------------------------------------------------- retention

def age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_purge_deletes_only_old_reports_and_harness_results(tmp_path):
    names = ["RPT-20260101-000001.json", "RPT-20260101-000002.json", "harness-HARNESS-1.json", "review-events.jsonl",
             "leaktest-latest.json", "notes.txt"]
    for n in names:
        (tmp_path / n).write_text("{}", encoding="utf-8")
    for n in ("RPT-20260101-000001.json", "harness-HARNESS-1.json", "review-events.jsonl", "leaktest-latest.json", "notes.txt"):
        age(tmp_path / n, 30)
    deleted = ui.purge_old_reports(tmp_path, 7)
    assert sorted(deleted) == ["RPT-20260101-000001.json", "harness-HARNESS-1.json"]
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["RPT-20260101-000002.json", "leaktest-latest.json", "notes.txt", "review-events.jsonl"]


def test_purge_leaves_a_seal_ledger_alone(tmp_path):
    reports_dir, seal_dir = tmp_path / "reports", tmp_path / "seal-data"
    reports_dir.mkdir()
    seal_dir.mkdir()
    ledger = seal_dir / "ledger.jsonl"
    ledger.write_text('{"seq":1}\n', encoding="utf-8")
    age(ledger, 400)
    (reports_dir / "RPT-20250101-000001.json").write_text("{}", encoding="utf-8")
    age(reports_dir / "RPT-20250101-000001.json", 400)
    ui.purge_old_reports(reports_dir, 7)
    ui.purge_old_reports(seal_dir, 7)  # even when pointed at the seal folder, the ledger name does not match
    assert ledger.exists() and not (reports_dir / "RPT-20250101-000001.json").exists()


def test_retention_days_setting():
    assert ui.retention_days({}) == 7 and ui.retention_days({"RETENTION_DAYS": "30"}) == 30
    assert ui.retention_days({"RETENTION_DAYS": "abc"}) == 7 and ui.retention_days({"RETENTION_DAYS": "0"}) == 7


def test_start_retention_purges_at_start(tmp_path):
    old = tmp_path / "RPT-20250101-000001.json"
    old.write_text("{}", encoding="utf-8")
    age(old, 40)
    cfg = ui.Config(root=ROOT, reports_dir=tmp_path, env={"RETENTION_DAYS": "7"})
    thread = ui.start_retention(cfg, interval=3600)
    for _ in range(50):
        if not old.exists():
            break
        time.sleep(0.05)
    assert not old.exists() and thread.daemon
