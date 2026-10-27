"""Tests for seal/. A real server runs in a thread on a random port with a temp ledger."""
import copy
import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
import server  # noqa: E402
import verify  # noqa: E402
from seal_common import canonical, make_mac, report_hash, sha256_hex  # noqa: E402

VENDOR, ADMIN, SECRET = "vendor-token-abc", "admin-token-xyz", "test-secret-123"
REPORT = {"report": {"id": "RPT-1", "overall_status": "MISMATCH"},
          "findings": [{"id": "C2", "status": "MISMATCH", "note": "Stornierung fehlt"}]}


@pytest.fixture
def env(tmp_path):
    return {"SEAL_SECRET": SECRET, "SEAL_VENDOR_TOKEN": VENDOR, "SEAL_ADMIN_TOKEN": ADMIN,
            "SEAL_LEDGER": str(tmp_path / "ledger.jsonl")}


@pytest.fixture
def srv(env):
    httpd = server.make_server(env, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    httpd.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.port = httpd.server_address[1]
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def raw(srv, method, path, token=None, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, json.loads(payload)


def sealed_run(srv, tmp_path, report=REPORT):
    run = client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur")
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    res = client.submit(path, url=srv.url, token=VENDOR, state_file=tmp_path / "cur")
    return run, path, Path(res["receipt_file"]), res["receipt"]


def check(srv, report_path, receipt_path):
    return verify.verify_files(report_path, receipt_path, srv.url, ADMIN)


def test_genuine_report_verifies(srv, tmp_path):
    _, rpt, rcpt, receipt = sealed_run(srv, tmp_path)
    assert check(srv, rpt, rcpt)["result"] == "GENUINE"
    assert receipt["report_sha256"] == report_hash(REPORT) and receipt["seq"] == 2


def test_key_order_and_whitespace_do_not_matter(srv, tmp_path):
    _, rpt, rcpt, _ = sealed_run(srv, tmp_path)
    rpt.write_text(json.dumps(REPORT, indent=4, sort_keys=True), encoding="utf-8")
    assert check(srv, rpt, rcpt)["result"] == "GENUINE"


def test_one_changed_character_is_tampered(srv, tmp_path):
    _, rpt, rcpt, _ = sealed_run(srv, tmp_path)
    edited = copy.deepcopy(REPORT)
    edited["findings"][0]["note"] = "Stornierung fehlt."
    rpt.write_text(json.dumps(edited), encoding="utf-8")
    res = check(srv, rpt, rcpt)
    assert res["result"] == "TAMPERED" and "differs" in res["reason"]


def test_mismatch_turned_into_pass_is_tampered(srv, tmp_path):
    _, rpt, rcpt, _ = sealed_run(srv, tmp_path)
    edited = copy.deepcopy(REPORT)
    edited["findings"][0]["status"] = "PASS"
    rpt.write_text(json.dumps(edited), encoding="utf-8")
    assert check(srv, rpt, rcpt)["result"] == "TAMPERED"


def test_forged_mac_is_tampered(srv, tmp_path):
    _, rpt, rcpt, receipt = sealed_run(srv, tmp_path)
    receipt["mac"] = "0" * 64
    rcpt.write_text(json.dumps(receipt), encoding="utf-8")
    res = check(srv, rpt, rcpt)
    assert res["result"] == "TAMPERED" and "MAC" in res["reason"]


def test_receipt_with_edited_hash_is_tampered(srv, tmp_path):
    # vendor edits the report AND rewrites the hash in the receipt: the MAC no longer fits
    _, rpt, rcpt, receipt = sealed_run(srv, tmp_path)
    edited = copy.deepcopy(REPORT)
    edited["findings"][0]["status"] = "PASS"
    receipt["report_sha256"] = report_hash(edited)
    rpt.write_text(json.dumps(edited), encoding="utf-8")
    rcpt.write_text(json.dumps(receipt), encoding="utf-8")
    assert check(srv, rpt, rcpt)["result"] == "TAMPERED"


def test_unknown_run_id(srv, tmp_path):
    _, rpt, rcpt, receipt = sealed_run(srv, tmp_path)
    receipt["run_id"] = "RUN-" + "ab" * 12
    rcpt.write_text(json.dumps(receipt), encoding="utf-8")
    assert check(srv, rpt, rcpt)["result"] == "UNKNOWN_RUN"


def test_malformed_receipt_is_tampered_not_a_crash(srv, tmp_path):
    _, rpt, rcpt, _ = sealed_run(srv, tmp_path)
    for bad in ({}, {"run_id": 5}, {"run_id": "x", "report_sha256": "y", "issued_at": 1, "submitted_at": 2, "seq": "3", "mac": 4}):
        rcpt.write_text(json.dumps(bad), encoding="utf-8")
        assert check(srv, rpt, rcpt)["result"] == "TAMPERED"


def test_second_submit_for_same_run_is_rejected(srv, tmp_path):
    run, rpt, _, _ = sealed_run(srv, tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"different": True}), encoding="utf-8")
    with pytest.raises(client.SealError, match="409"):
        client.submit(other, run_id=run["run_id"], url=srv.url, token=VENDOR)


def test_replaying_an_old_report_for_a_new_run_is_rejected(srv, tmp_path):
    _, rpt, _, _ = sealed_run(srv, tmp_path)
    new_run = client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur2")
    with pytest.raises(client.SealError, match="409"):
        client.submit(rpt, run_id=new_run["run_id"], url=srv.url, token=VENDOR)


def test_old_receipt_does_not_validate_a_different_report(srv, tmp_path):
    _, _, rcpt, _ = sealed_run(srv, tmp_path)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"older": "report"}), encoding="utf-8")
    assert check(srv, other, rcpt)["result"] == "TAMPERED"


def test_submit_for_unknown_run_is_404(srv):
    status, body = raw(srv, "POST", "/runs/RUN-" + "0" * 24 + "/submit", VENDOR, {"report_sha256": "a" * 64})
    assert status == 404 and "error" in body


@pytest.mark.parametrize("method, path, token", [
    ("POST", "/runs/start", None), ("POST", "/runs/start", "wrong"), ("POST", "/runs/start", ADMIN),
    ("GET", "/runs", None), ("GET", "/runs", VENDOR), ("GET", "/runs", "wrong"),
    ("POST", "/verify", None), ("POST", "/verify", VENDOR),
    ("POST", "/runs/RUN-" + "0" * 24 + "/submit", ADMIN),
])
def test_wrong_or_missing_token_is_rejected(srv, method, path, token):
    status, body = raw(srv, method, path, token, {} if method == "POST" else None)
    assert status == 401 and "error" in body


def test_runs_lists_unsubmitted_runs(srv, tmp_path):
    first, *_ = sealed_run(srv, tmp_path)
    hidden = client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur3")
    data = verify.list_runs(srv.url, ADMIN)
    by_id = {r["run_id"]: r for r in data["runs"]}
    assert data["total"] == 2 and data["never_submitted"] == 1
    assert by_id[first["run_id"]]["submitted"] is True and by_id[hidden["run_id"]]["submitted"] is False
    assert "NEVER SUBMITTED" in verify.format_runs(data)


def test_editing_a_past_ledger_line_is_detected(srv, env, tmp_path):
    _, rpt, rcpt, _ = sealed_run(srv, tmp_path)
    client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur3")
    ledger = Path(env["SEAL_LEDGER"])
    lines = ledger.read_text(encoding="utf-8").split("\n")
    lines[0] = lines[0].replace("start", "stark", 1)  # edit the first line only
    ledger.write_text("\n".join(lines), encoding="utf-8")
    res = check(srv, rpt, rcpt)
    assert res["result"] == "LEDGER_TAMPERED" and "line 1" in res["reason"]
    assert verify.list_runs(srv.url, ADMIN)["result"] == "LEDGER_TAMPERED"
    with pytest.raises(client.SealError, match="503"):  # a damaged ledger accepts no new runs
        client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur4")


def test_editing_the_last_ledger_line_or_removing_a_middle_line_is_detected(srv, env, tmp_path):
    sealed_run(srv, tmp_path)
    client.start_run(srv.url, VENDOR, state_file=tmp_path / "cur3")
    ledger = Path(env["SEAL_LEDGER"])
    original = ledger.read_text(encoding="utf-8")
    lines = original.strip().split("\n")

    last_edited = lines[:-1] + [lines[-1].replace("issued_at", "issued_xx", 1)]
    ledger.write_text("\n".join(last_edited) + "\n", encoding="utf-8")
    assert server.Ledger(ledger, SECRET.encode()).read()[1] is not None

    ledger.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")  # delete line 2
    assert server.Ledger(ledger, SECRET.encode()).read()[1] is not None

    ledger.write_bytes(original.encode("utf-8"))
    assert server.Ledger(ledger, SECRET.encode()).read()[1] is None


def test_ledger_is_hash_chained_and_append_only(srv, env, tmp_path):
    sealed_run(srv, tmp_path)
    lines = Path(env["SEAL_LEDGER"]).read_text(encoding="utf-8").strip().split("\n")
    entries = [json.loads(line) for line in lines]
    assert entries[0]["prev"] == "0" * 64
    for prev_line, entry in zip(lines, entries[1:]):
        assert entry["prev"] == sha256_hex(prev_line)
    assert [e["seq"] for e in entries] == [1, 2]


def test_ledger_survives_server_restart(env, tmp_path):
    first = server.make_server(env, "127.0.0.1", 0)
    status, body = first.app.start_run()
    first.server_close()
    second = server.make_server(env, "127.0.0.1", 0)
    runs = second.app.runs()[1]["runs"]
    second.server_close()
    assert status == 201 and [r["run_id"] for r in runs] == [body["run_id"]]


@pytest.mark.parametrize("missing", ["SEAL_SECRET", "SEAL_VENDOR_TOKEN", "SEAL_ADMIN_TOKEN"])
def test_missing_secret_refuses_to_start(env, missing, capsys):
    env.pop(missing)
    with pytest.raises(server.ConfigError, match=missing):
        server.make_server(env, "127.0.0.1", 0)
    assert server.main(env) == 2
    err = capsys.readouterr().err
    assert missing in err and SECRET not in err and VENDOR not in err


def test_empty_secret_refuses_to_start(env):
    env["SEAL_SECRET"] = "   "
    with pytest.raises(server.ConfigError):
        server.make_server(env, "127.0.0.1", 0)


def test_oversized_body_gets_clean_413(srv):
    status, body = raw(srv, "POST", "/verify", ADMIN, headers={"Content-Length": str(server.MAX_BODY + 1)})
    assert status == 413 and "error" in body
    big = json.dumps({"report": {"x": "a" * server.MAX_BODY}, "receipt": {}}).encode()
    status, body = raw(srv, "POST", "/verify", ADMIN, big)
    assert status == 413


@pytest.mark.parametrize("body", [b"not json", b"[1,2]", b'{"report": 1, "receipt": 2}', b'{"report": {}}',
                                  b'{"report": {}, "receipt": {}, "extra": 1}', b"\xff\xfe", b'{"report": NaN, "receipt": {}}',
                                  b"[" * 5000 + b"]" * 5000])
def test_malformed_verify_bodies_give_clean_400(srv, body):
    status, resp = raw(srv, "POST", "/verify", ADMIN, body)
    assert status == 400 and list(resp) == ["error"]


@pytest.mark.parametrize("body", [b"not json", {"report_sha256": "ABC"}, {"report_sha256": "a" * 63}, {"report_sha256": 5},
                                  {"report_sha256": "a" * 64, "x": 1}, {}, [1]])
def test_malformed_submit_bodies_give_clean_400(srv, body):
    run = srv.app.start_run()[1]
    status, resp = raw(srv, "POST", f"/runs/{run['run_id']}/submit", VENDOR, body)
    assert status == 400 and list(resp) == ["error"]


def test_bad_run_id_format_and_unknown_routes(srv):
    assert raw(srv, "POST", "/runs/../../etc/submit", VENDOR, {"report_sha256": "a" * 64})[0] in (400, 404)
    assert raw(srv, "POST", "/runs/not-a-run/submit", VENDOR, {"report_sha256": "a" * 64})[0] == 400
    assert raw(srv, "GET", "/nothing", ADMIN)[0] == 404
    assert raw(srv, "PUT", "/runs", ADMIN)[0] == 405


def test_errors_never_contain_stack_traces_or_secrets(srv):
    status, body = raw(srv, "POST", "/verify", ADMIN, b"{bad")
    text = json.dumps(body)
    assert "Traceback" not in text and SECRET not in text and ADMIN not in text


def test_secrets_are_not_logged(srv, tmp_path, caplog):
    with caplog.at_level("DEBUG", logger="seal.server"):
        sealed_run(srv, tmp_path)
        raw(srv, "GET", "/runs", "wrong-token-value")
    assert caplog.records
    for secret in (SECRET, VENDOR, ADMIN, "wrong-token-value"):
        assert secret not in caplog.text


def test_ledger_mac_depends_on_secret(env, tmp_path):
    srv_a = server.make_server(env, "127.0.0.1", 0)
    srv_a.app.start_run()
    srv_a.server_close()
    other = dict(env, SEAL_SECRET="another-secret")
    assert server.Ledger(Path(env["SEAL_LEDGER"]), b"another-secret").read()[1] is not None
    assert make_mac(b"a", "receipt", {"x": 1}) != make_mac(b"b", "receipt", {"x": 1})
    assert make_mac(b"a", "receipt", {"x": 1}) != make_mac(b"a", "ledger", {"x": 1})
    assert canonical({"b": 1, "a": "ä"}) == '{"a":"ä","b":1}'
