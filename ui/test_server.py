"""Tests for ui/server.py. Real server on a random port; the model is a fake, the seal is a real
seal server in a thread with throwaway secrets and a temp ledger. No network, no real API key.

  python -m pytest ui -q
"""
import http.client
import importlib.util
import json
import re
import secrets
import shutil
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name, path, extra_path=None):
    """Load a module from a file under a private name (several folders have a server.py)."""
    if extra_path and str(extra_path) not in sys.path:
        sys.path.append(str(extra_path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ui = load("team10_ui_server", ROOT / "ui" / "server.py")
seal_server = load("team10_seal_server", ROOT / "seal" / "server.py", extra_path=ROOT / "seal")

VENDOR, ADMIN, SECRET = "vendor-" + secrets.token_hex(8), "admin-" + secrets.token_hex(8), "secret-" + secrets.token_hex(16)
API_KEY = "sk-fake-" + secrets.token_hex(8)
INJECTION = '<script>alert(1)</script><img src=x onerror=alert(2)>'


def serve(httpd):
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    httpd.port = httpd.server_address[1]
    return httpd


# ---------------------------------------------------------------- fake model

class FakeClient:
    """Shape of the OpenAI client; the reply is built from the first retrieved chunk so quotes are real."""

    def __init__(self, mode, chunk):
        self.mode, self.chunk = mode, chunk
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        c = self.chunk
        quote = " ".join(c.text.split())[:90]
        body = {"answer": "Fake answer.", "status": "ANSWERED",
                "citations": [{"chunk_id": c.chunk_id, "section": c.section, "page": c.page_start, "quote": quote}]}
        if self.mode == "injection":
            body["answer"] = INJECTION
        elif self.mode == "needs_review":
            body["citations"][0]["quote"] = "this sentence is not in the chunk at all, invented"
        elif self.mode == "malformed":
            content = "this is not json"
            return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))])


def make_ask(mode_box):
    from retrieval.ask import ask
    from retrieval.search import search

    def ask_fn(question):
        chunks = search(question)
        return ask(question, chunks=chunks, client=FakeClient(mode_box["mode"], chunks[0]))
    return ask_fn


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def sample_report(tmp_path_factory):
    """One real report from the real run_review.py (through the server, which also tests /api/review/run)."""
    cfg = ui.Config(root=ROOT, reports_dir=ROOT / "reports", env={})
    httpd = serve(ui.make_server("127.0.0.1", 0, cfg))
    try:
        status, data = call(httpd, "POST", "/api/review/run")
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert status == 200, data
    return data


@pytest.fixture
def seal():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        env = {"SEAL_SECRET": SECRET, "SEAL_VENDOR_TOKEN": VENDOR, "SEAL_ADMIN_TOKEN": ADMIN,
               "SEAL_LEDGER": str(Path(tmp) / "ledger.jsonl")}
        httpd = serve(seal_server.make_server(env, "127.0.0.1", 0))
        httpd.url = f"http://127.0.0.1:{httpd.port}"
        yield httpd
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def mode_box():
    return {"mode": "answered"}


@pytest.fixture
def reports(tmp_path, sample_report):
    d = tmp_path / "reports"
    d.mkdir()
    (d / sample_report["file"]).write_text(json.dumps(sample_report["data"], ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def srv(reports, seal, mode_box):
    env = {"HESSIAN_API_KEY": API_KEY, "SEAL_URL": seal.url, "SEAL_VENDOR_TOKEN": VENDOR, "SEAL_ADMIN_TOKEN": ADMIN}
    cfg = ui.Config(root=ROOT, reports_dir=reports, env=env, ask_fn=make_ask(mode_box), ask_limit=4, demo_limit=50)
    httpd = serve(ui.make_server("127.0.0.1", 0, cfg))
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def call(srv, method, path, body=None, headers=None, raw=None, post_headers=True):
    hdrs = dict(headers or {})
    if method == "POST" and post_headers:
        hdrs.setdefault("X-Requested-With", "team10-ui")
    data = raw
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=130)
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(payload)
    except ValueError:
        return resp.status, payload


# ---------------------------------------------------------------- health

def test_health_reports_every_part(srv):
    status, data = call(srv, "GET", "/api/health")
    assert status == 200
    parts = data["parts"]
    assert set(parts) == {"checker", "retrieval", "seal", "harness"}
    assert parts["checker"]["status"] == "available"
    assert parts["seal"]["status"] == "available"
    assert parts["harness"]["cases"] == 500
    assert parts["retrieval"]["api_key_configured"] is True


def test_health_missing_parts_are_unavailable_not_faked(reports):
    cfg = ui.Config(root=ROOT, reports_dir=reports, env={})
    httpd = serve(ui.make_server("127.0.0.1", 0, cfg))
    try:
        _, data = call(httpd, "GET", "/api/health")
        assert data["parts"]["seal"]["status"] == "unavailable"
        assert data["parts"]["retrieval"]["status"] == "unavailable"
        assert "reason" in data["parts"]["seal"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_health_seal_down_is_unavailable(reports):
    env = {"SEAL_URL": "http://127.0.0.1:1", "SEAL_VENDOR_TOKEN": VENDOR, "SEAL_ADMIN_TOKEN": ADMIN}
    httpd = serve(ui.make_server("127.0.0.1", 0, ui.Config(root=ROOT, reports_dir=reports, env=env)))
    try:
        _, data = call(httpd, "GET", "/api/health")
        assert data["parts"]["seal"]["status"] == "unavailable"
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------- review and harness

def test_review_run_returns_a_real_report(sample_report):
    findings = sample_report["data"]["findings"]
    assert sample_report["file"].startswith("RPT-")
    # T10-043 merge: run_review.py no longer runs the C1-C8 message-flow checks
    # (lisa-update removed them); the DBVO checks F1-F7 + C9-C13 remain.
    assert {f["id"] for f in findings} >= {"F1", "C9", "C12"}
    assert all(f["status"] in ("PASS", "MISMATCH", "NOT EVALUATED", "NEEDS_REVIEW", "BLOCKED") for f in findings)
    assert sample_report["data"]["robustness"]["result"].endswith("stopped")


def test_review_latest(srv, sample_report):
    status, data = call(srv, "GET", "/api/review/latest")
    assert status == 200 and data["file"] == sample_report["file"]


def test_review_latest_without_report_is_a_plain_404(tmp_path):
    httpd = serve(ui.make_server("127.0.0.1", 0, ui.Config(root=ROOT, reports_dir=tmp_path / "none", env={})))
    try:
        status, data = call(httpd, "GET", "/api/review/latest")
        assert status == 404 and "Run review" in data["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_harness_run_small_and_limits(srv):
    for bad in (0, 301, "5", True, 2.5):
        status, _ = call(srv, "POST", "/api/harness/run", {"limit": bad})
        assert status == 400, bad
    assert call(srv, "POST", "/api/harness/run", {"limit": 5, "extra": 1})[0] == 400
    # the real harness writes to ROOT/reports, the server under test reads its own temp dir -> run with default cfg
    httpd = serve(ui.make_server("127.0.0.1", 0, ui.Config(root=ROOT, env={})))
    try:
        status, data = call(httpd, "POST", "/api/harness/run", {"limit": 5})
        assert status == 200 and data["summary"]["cases"] == 5
        status, latest = call(httpd, "GET", "/api/harness/latest")
        assert status == 200 and latest["summary"]["cases"] >= 1
        status, detail = call(httpd, "GET", "/api/testcases/GOLD-13.1")
        assert status == 200 and detail["harness_result"]["id"] == "GOLD-13.1"
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------- test cases

def test_testcases_sources_and_totals(srv):
    assert call(srv, "GET", "/api/testcases?source=all&page_size=1")[1]["total"] == 500
    assert call(srv, "GET", "/api/testcases?source=golden")[1]["total"] == 300
    assert call(srv, "GET", "/api/testcases?source=stories")[1]["total"] == 200


def test_testcases_filter_search_pagination(srv):
    _, data = call(srv, "GET", "/api/testcases?group=golden")
    assert data["total"] == 5 and all(i["group"] == "golden" for i in data["items"])
    _, p1 = call(srv, "GET", "/api/testcases?page=1&page_size=10")
    _, p2 = call(srv, "GET", "/api/testcases?page=2&page_size=10")
    assert len(p1["items"]) == 10 and p1["items"][0]["id"] != p2["items"][0]["id"]
    _, found = call(srv, "GET", "/api/testcases?q=gold-13.3")
    assert [i["id"] for i in found["items"]] == ["GOLD-13.3"]
    _, kind = call(srv, "GET", "/api/testcases?kind=correct%20output&page_size=100")
    assert kind["total"] > 0 and all(i["kind"] == "correct output" for i in kind["items"])
    assert call(srv, "GET", "/api/testcases?page_size=101")[0] == 400
    assert call(srv, "GET", "/api/testcases?page=0")[0] == 400
    assert call(srv, "GET", "/api/testcases?page=abc")[0] == 400
    assert call(srv, "GET", "/api/testcases?source=evil")[0] == 400


def test_testcase_detail(srv):
    status, data = call(srv, "GET", "/api/testcases/GOLD-13.1")
    assert status == 200 and data["case"]["id"] == "GOLD-13.1" and "observed_dbvo" in data["case"]
    assert call(srv, "GET", "/api/testcases/S1-001")[0] == 200
    assert call(srv, "GET", "/api/testcases/NOPE-1")[0] == 404
    assert call(srv, "GET", "/api/testcases/bad%20id!")[0] == 400


# ---------------------------------------------------------------- ask

def test_ask_answered(srv):
    status, data = call(srv, "POST", "/api/ask", {"question": "Was muss bei einer Stornierung (Abgabegrund 88) immer gefuellt werden?"})
    assert status == 200 and data["status"] == "ANSWERED"
    assert data["citations"][0]["match_level"] in ("exact", "table")
    assert set(data["citations"][0]) == {"chunk_id", "section", "page", "quote", "match_level"}
    assert data["validation_errors"] == [] and data["audit"]["attempts"] == 1


def test_ask_needs_review_keeps_status_and_errors(srv, mode_box):
    mode_box["mode"] = "needs_review"
    _, data = call(srv, "POST", "/api/ask", {"question": "Wann wird der Abgabegrund 41 verwendet?"})
    assert data["status"] == "NEEDS_REVIEW" and data["validation_errors"]
    assert data["citations"][0]["match_level"] is None


def test_ask_malformed_model_reply_is_needs_review(srv, mode_box):
    mode_box["mode"] = "malformed"
    _, data = call(srv, "POST", "/api/ask", {"question": "Wann wird der Abgabegrund 41 verwendet?"})
    assert data["status"] == "NEEDS_REVIEW" and data["audit"]["attempts"] == 3


def test_ask_answer_with_script_is_passed_on_as_plain_data(srv, mode_box):
    """The server never edits the text; the UI shows it with textContent (see the frontend tests below)."""
    mode_box["mode"] = "injection"
    _, data = call(srv, "POST", "/api/ask", {"question": "Wann wird der Abgabegrund 41 verwendet?"})
    assert data["answer"] == INJECTION


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "   "}, {"question": 5}, {"question": ["a"]},
                                  {"question": "ok", "extra": 1}, {"question": "bad\x00char"}, [], "text"])
def test_ask_rejects_bad_input(srv, body):
    status, data = call(srv, "POST", "/api/ask", body)
    assert status == 400 and "error" in data


def test_ask_rejects_malformed_json_and_empty_body(srv):
    assert call(srv, "POST", "/api/ask", raw=b"{not json", headers={"Content-Type": "application/json"})[0] == 400
    assert call(srv, "POST", "/api/ask")[0] == 400


def test_ask_question_length_limit(srv):
    assert call(srv, "POST", "/api/ask", {"question": "a" * 501})[0] == 400
    assert call(srv, "POST", "/api/ask", {"question": "Abgabegrund 41 " + "a" * 400})[0] == 200


def test_ask_rate_limit(srv):
    codes = [call(srv, "POST", "/api/ask", {"question": "Abgabegrund 41?"})[0] for _ in range(6)]
    assert codes[:4] == [200] * 4 and codes[4:] == [429, 429]


def test_ask_missing_key_and_failure_messages(reports):
    from retrieval.ask import MissingApiKeyError

    def no_key(q):
        raise MissingApiKeyError("HESSIAN_API_KEY is not set")

    def boom(q):
        raise RuntimeError("secret internal detail /home/x")

    for fn, code in ((no_key, 503), (boom, 502)):
        httpd = serve(ui.make_server("127.0.0.1", 0, ui.Config(root=ROOT, reports_dir=reports, env={}, ask_fn=fn)))
        try:
            status, data = call(httpd, "POST", "/api/ask", {"question": "hi"})
            assert status == code and "secret internal" not in json.dumps(data) and "Traceback" not in json.dumps(data)
        finally:
            httpd.shutdown()
            httpd.server_close()


def test_ask_timeout(reports):
    release = threading.Event()
    cfg = ui.Config(root=ROOT, reports_dir=reports, env={}, ask_fn=lambda q: release.wait(5))
    with pytest.raises(ui.ApiError) as exc:
        ui.api_ask(cfg, "1.2.3.4", {"question": "hi"}, {}, timeout=0.2)
    release.set()
    assert exc.value.status == 504


# ---------------------------------------------------------------- seal

def test_seal_demo_genuine_tampered_never_submitted(srv):
    status, data = call(srv, "POST", "/api/seal/demo")
    assert status == 200, data
    results = [s["result"] for s in data["steps"]]
    assert results == ["RUN STARTED", "RECEIPT ISSUED", "GENUINE", "TAMPERED", "NEVER SUBMITTED"]
    assert data["steps"][3]["change"]["from"] != data["steps"][3]["change"]["to"]
    hidden = data["steps"][4]["run_id"]
    run = next(r for r in data["runs"]["runs"] if r["run_id"] == hidden)
    assert run["submitted"] is False and data["runs"]["never_submitted"] >= 1
    status, runs = call(srv, "GET", "/api/seal/runs")
    assert status == 200 and runs["total"] == data["runs"]["total"]


def test_seal_unavailable_gives_clear_error(reports):
    httpd = serve(ui.make_server("127.0.0.1", 0, ui.Config(root=ROOT, reports_dir=reports, env={})))
    try:
        for method, path in (("GET", "/api/seal/runs"), ("POST", "/api/seal/demo")):
            status, data = call(httpd, method, path)
            assert status == 503 and "Seal unavailable" in data["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_alter_one_status_always_changes_something():
    report = {"findings": [{"id": "A", "status": "PASS"}, {"id": "B", "status": "NOT EVALUATED"}]}
    forged, change = ui.alter_one_status(report)
    assert change == {"finding": "B", "from": "NOT EVALUATED", "to": "PASS"} and report["findings"][1]["status"] == "NOT EVALUATED"
    forged, change = ui.alter_one_status({"findings": [{"id": "A", "status": "PASS"}]})
    assert change["to"] == "MISMATCH"
    with pytest.raises(ui.ApiError):
        ui.alter_one_status({"findings": []})


# ---------------------------------------------------------------- decision (human gate)

def test_decision_is_append_only_and_never_automatic(srv, reports):
    assert call(srv, "GET", "/api/review/decision")[1] == {"events": []}
    s1, e1 = call(srv, "POST", "/api/review/decision", {"reviewer": "Ada", "decision": "needs_changes", "comment": "C9 missing"})
    s2, e2 = call(srv, "POST", "/api/review/decision", {"reviewer": "Bob", "decision": "approve"})
    assert (s1, s2) == (200, 200)
    events = call(srv, "GET", "/api/review/decision")[1]["events"]
    assert [e["reviewer"] for e in events] == ["Ada", "Bob"] and events[0]["timestamp"] < events[1]["timestamp"] + "z"
    assert events[0]["report_id"].startswith("RPT-")
    lines = (reports / "review-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["comment"] == "C9 missing"


@pytest.mark.parametrize("body", [
    {"reviewer": "A", "decision": "maybe"}, {"reviewer": "", "decision": "approve"}, {"decision": "approve"},
    {"reviewer": "A", "decision": "approve", "comment": "x" * 1001}, {"reviewer": "A" * 81, "decision": "approve"},
    {"reviewer": "A", "decision": "approve", "extra": 1}, {"reviewer": "A\x07", "decision": "approve"},
    {"reviewer": "A", "decision": "approve", "report_id": "../../etc"}, {"reviewer": ["A"], "decision": "approve"},
])
def test_decision_rejects_bad_input(srv, reports, body):
    assert call(srv, "POST", "/api/review/decision", body)[0] == 400
    assert not (reports / "review-events.jsonl").exists()


# ---------------------------------------------------------------- web security

@pytest.mark.parametrize("path", [
    "/../server.py", "/%2e%2e/server.py", "/..%2fserver.py", "/figures/../ui/server.py", "/figures/..%2f..%2f.env",
    "/server.py", "/test_server.py", "/README.md", "/js/../server.py", "/%2e%2e/%2e%2e/.env", "/.env",
    "/css/%00.css", "/..\\server.py", "/C:/Windows/win.ini", "/js", "/figures",
])
def test_path_traversal_and_non_public_files_are_blocked(srv, path):
    status, body = call(srv, "GET", path)
    assert status in (400, 404), path
    assert b"import" not in (body if isinstance(body, bytes) else json.dumps(body).encode())


def test_static_files_and_security_headers(srv):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    for path, ctype in (("/", "text/html"), ("/js/app.js", "text/javascript"), ("/css/styles.css", "text/css"),
                        ("/figures/system-overview.png", "image/png")):
        conn.request("GET", path)
        r = conn.getresponse()
        r.read()
        assert r.status == 200 and r.getheader("Content-Type").startswith(ctype), path
        assert "default-src 'self'" in r.getheader("Content-Security-Policy")
        assert r.getheader("X-Content-Type-Options") == "nosniff"
    conn.close()


def test_post_needs_our_header_and_same_origin(srv):
    assert call(srv, "POST", "/api/ask", {"question": "hi"}, post_headers=False)[0] == 403
    assert call(srv, "POST", "/api/ask", {"question": "Abgabegrund 41"}, headers={"Origin": "http://evil.example"})[0] == 403


def test_body_limit_and_content_type(srv):
    assert call(srv, "POST", "/api/ask", raw=b"x" * (64 * 1024 + 1), headers={"Content-Type": "application/json"})[0] == 413
    assert call(srv, "POST", "/api/ask", raw=b'{"question":"hi"}', headers={"Content-Type": "text/plain"})[0] == 415


def test_unknown_paths_and_methods_give_json_errors(srv):
    assert call(srv, "GET", "/api/nope")[0] == 404
    assert call(srv, "POST", "/api/health")[0] == 405
    assert call(srv, "DELETE", "/api/health")[0] == 405
    status, data = call(srv, "GET", "/api/testcases/..%2f..%2fserver.py")
    assert status in (400, 404) and "error" in data


def test_no_secret_ever_appears_in_a_response_or_the_log(srv, caplog):
    caplog.set_level("DEBUG")
    secrets_seen = (API_KEY, VENDOR, ADMIN, SECRET)
    bodies = []
    for method, path, body in (("GET", "/api/health", None), ("GET", "/api/review/latest", None), ("GET", "/api/seal/runs", None),
                               ("POST", "/api/seal/demo", None), ("POST", "/api/ask", {"question": "Abgabegrund 41"}),
                               ("GET", "/api/testcases", None), ("GET", "/api/review/decision", None), ("GET", "/", None),
                               ("GET", "/js/app.js", None), ("GET", "/api/nope", None)):
        status, data = call(srv, method, path, body)
        bodies.append(data if isinstance(data, bytes) else json.dumps(data))
    for blob in bodies:
        text = blob.decode("utf-8", "replace") if isinstance(blob, bytes) else blob
        assert not any(s in text for s in secrets_seen)
    assert not any(s in caplog.text for s in secrets_seen)


# ---------------------------------------------------------------- frontend rules (no browser needed)

FRONTEND = sorted((ROOT / "ui" / "js").glob("*.js")) + [ROOT / "ui" / "index.html"]


@pytest.mark.parametrize("path", [p for p in FRONTEND if p.name != "data.js"], ids=lambda p: p.name)
def test_frontend_never_builds_html_from_data(path):
    text = path.read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert forbidden not in text, f"{path.name} uses {forbidden}"


def test_frontend_has_no_external_assets_and_no_inline_script():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"""(src|href)=["']https?://""", html)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and " style=" not in html and "onclick=" not in html
    css = (ROOT / "ui" / "css" / "styles.css").read_text(encoding="utf-8")
    assert "http://" not in css and "https://" not in css and "@import" not in css


def test_frontend_status_badges_cover_every_required_status():
    util = (ROOT / "ui" / "js" / "util.js").read_text(encoding="utf-8")
    for status in ("PASS", "MISMATCH", "NOT EVALUATED", "NOT_EVALUATED", "NEEDS_REVIEW", "BLOCKED", "ANSWERED",
                   "NOT_FOUND", "GENUINE", "TAMPERED", "NEVER SUBMITTED"):
        assert f'"{status}":' in util
    assert re.search(r'"NOT EVALUATED": "badge-not-evaluated"', util) and re.search(r'"NEEDS_REVIEW": "badge-needs-review"', util)
