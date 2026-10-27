"""Tests for the SÜSIE local web bridge (T10-031): read-only API over the
itsg store, static frontend serving, traversal refusal, demo re-run; plus the
story-cases/reviews/harness state overlays and POST /api/review/run (T10-032)."""
import contextlib
import http.client
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from itsg import actions, chat, demo, webserver
from itsg.llm import LLMError
from itsg.store import Store
from itsg.webserver import SUSIEHandler, build_state


def _serve(frontend: Path, store: Path):
    SUSIEHandler.frontend_root = frontend
    SUSIEHandler.store_root = store
    httpd = webserver.ThreadingHTTPServer(("127.0.0.1", 0), SUSIEHandler)
    thread = __import__("threading").Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


def _request(port: int, method: str, path: str, body=None, headers=None, timeout: int = 10):
    """Loopback-only HTTP helper: the host is the literal 127.0.0.1, the port comes
    from the ephemeral test server. Returns (status, body bytes) without raising
    on 4xx/5xx, so callers assert on the status directly."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


class TestBuildState(unittest.TestCase):
    def test_state_from_demo_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                demo.run_demo(Path(tmp), live=False, fresh=True)
            state = build_state(Path(tmp))
            self.assertTrue(state["ok"])
            self.assertEqual(len(state["cases"]), 4)
            statuses = sorted(c["status"] for c in state["cases"])
            self.assertEqual(statuses, ["MISMATCH", "NOT_EVALUATED", "PASS", "PASS"])
            mismatch = next(c for c in state["cases"] if c["status"] == "MISMATCH")
            self.assertTrue(mismatch["expected"])
            self.assertTrue(mismatch["observed"])
            self.assertNotEqual(mismatch["expected"], mismatch["observed"])
            uneval = next(c for c in state["cases"] if c["status"] == "NOT_EVALUATED")
            self.assertEqual(uneval["expected"], {})
            self.assertFalse(state["report"]["compliance_claim"])
            self.assertTrue(state["backend"]["events"] > 0)
            self.assertTrue(state["source"]["id"])

    def test_state_empty_store_is_empty_not_broken(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = build_state(Path(tmp))
            self.assertEqual(state["cases"], [])
            self.assertIsNone(state["report"]["id"])


class TestWebserver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = Path(self.tmp.name) / "store"
        frontend = Path(self.tmp.name) / "www"
        frontend.mkdir()
        (frontend / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
        (frontend / "sub").mkdir()
        (frontend / "secret.txt").write_text("nope", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            demo.run_demo(store, live=False, fresh=True)
        self.httpd, self.port = _serve(frontend, store)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def _get(self, path):
        return _request(self.port, "GET", path, timeout=5)

    def test_health(self):
        status, body = self._get("/api/health")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["events"], 0)

    def test_state_endpoint(self):
        _, body = self._get("/api/state")
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["cases"]), 4)

    def test_static_served_and_traversal_refused(self):
        status, body = self._get("/index.html")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>t</title>", body)
        status, _ = self._get("/../secret.txt")
        self.assertEqual(status, 403)
        status, _ = self._get("/missing.html")
        self.assertEqual(status, 404)

    def test_run_offline_rebuilds_store(self):
        status, body = _request(
            self.port, "POST", "/api/run", body=json.dumps({"live": False}).encode(),
            headers={"Content-Type": "application/json"}, timeout=30)
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        # /api/run (re)loads and compares Team 10's 30 cases (data/eaz_cases.json)
        self.assertEqual(len([c for c in payload["cases"] if c["id"].startswith("EAZ-")]), 30)

    def test_run_rejects_non_object_body(self):
        status, _ = _request(
            self.port, "POST", "/api/run", body=b"[1]", headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)


class TestStoriesReviews(unittest.TestCase):
    """State overlays (stories / reviews / harness) and POST /api/review/run
    against temp fixtures — the real 200-case story file is never loaded."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        store, frontend = tmp / "store", tmp / "www"
        frontend.mkdir()
        (frontend / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
        (tmp / "data").mkdir()
        (tmp / "reports").mkdir()
        SUSIEHandler.story_cases_path = tmp / "data" / "story_cases.json"
        SUSIEHandler.reports_path = tmp / "reports"
        SUSIEHandler.review_script_path = webserver.ROOT / "run_review.py"
        with contextlib.redirect_stdout(io.StringIO()):
            demo.run_demo(store, live=False, fresh=True)
        self.httpd, self.port = _serve(frontend, store)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        SUSIEHandler.story_cases_path = webserver.ROOT / "data" / "story_cases.json"
        SUSIEHandler.reports_path = webserver.ROOT / "reports"
        SUSIEHandler.review_script_path = webserver.ROOT / "run_review.py"
        self.tmp.cleanup()

    def _get_state(self):
        _, body = _request(self.port, "GET", "/api/state", timeout=5)
        return json.loads(body)

    def _write_story_fixture(self):
        cases = [
            {"id": "S1-001", "story": 1, "category": "current AU is a work accident",
             "must_flag": None, "observed_kind": "correct output",
             "scenario": {"current_start": "2026-03-04", "current_end": "2026-03-27",
                          "today": "2026-03-04", "current_cert": True, "insurance": "GKV",
                          "current_reason": "work accident",
                          "prior": [{"start": "2025-12-11", "end": "2025-12-19",
                                     "cert": True, "reason": "illness"},
                                    {"start": "2025-09-20", "end": "2025-10-04",
                                     "cert": False, "reason": "illness"}]},
             "expected": {"send_41": True, "dbvo": {"ABGABEGRUND": "41", "ANZAHL-AU": 1}}},
            {"id": "S1-002", "story": 1, "category": "current AU is a work accident",
             "must_flag": "R3", "observed_kind": "41 sent although not allowed",
             "scenario": {"current_start": "2026-05-01", "current_end": "2026-05-15",
                          "today": "2026-05-01", "current_cert": True, "insurance": "GKV",
                          "current_reason": "illness", "prior": []},
             "expected": {"send_41": False}},
            {"id": "S4-001", "story": 4, "category": "88 cancels the 41",
             "must_flag": "F-88-UR", "observed_kind": "88 cancels the 41 instead of the 01",
             "scenario": {"current_start": "2026-04-02", "current_end": "2026-04-21",
                          "today": "2026-04-04", "current_cert": True, "insurance": "GKV",
                          "current_reason": "illness", "employer_41": True, "prior": []},
             "expected": {"reply_valid": False}},
        ]
        path = SUSIEHandler.story_cases_path
        path.write_text(json.dumps(cases), encoding="utf-8")
        return cases

    def _write_report(self, name, report_id, n_findings=1):
        report = {
            "report": {"id": report_id, "created_at": "01.01.2026 00:00",
                       "scope": "DTA EEL – Abgabegrund 41 (DBVO) + message flow",
                       "template": "SYNTHETIC – no official ITSG report form found; no compliance claim",
                       "overall_status": "PASS",
                       "counts": {"PASS": n_findings, "NOT EVALUATED": 0,
                                  "NEEDS_REVIEW": 0, "MISMATCH": 0, "BLOCKED": 0}},
            "test_case": {"id": "TC-" + report_id, "source": "fixture", "inputs": {}},
            "execution": {"id": "RUN-" + report_id, "file": "TEEL0-Test1-DBVO",
                          "observed": {}, "observed_sources": {}},
            "findings": [{"id": f"F{i}", "rule": "Abgabegrund = 41",
                          "source": "VB 13.4 §3.1.18 p.43", "expected": "41",
                          "actual": "41", "status": "PASS"} for i in range(n_findings)],
            "robustness": {"result": "1/1 stopped", "reason": None, "attacks": []},
            "review": {"reviewer": None, "decision": "pending", "timestamp": None},
            "trace_url": None,
        }
        (SUSIEHandler.reports_path / name).write_text(json.dumps(report), encoding="utf-8")

    def _write_harness(self, name, run_id, mtime=None):
        data = {
            "summary": {"run_id": run_id, "git_sha": "deadbee", "cases": 2, "correct": 2,
                        "false_alarms": 0, "clean_cases": 1, "detected": 1,
                        "must_flag_cases": 1,
                        "by_category": {"story1 | current AU is a work accident":
                                        {"clean": 1, "detected": 1}}},
            "results": [
                {"id": "S1-001", "group": "story1", "must_flag": None, "flagged": [],
                 "category": "current AU is a work accident", "ok": True, "outcome": "clean",
                 "findings": [{"id": "F1", "expected": "41", "actual": "41", "status": "PASS"}]},
                {"id": "S1-002", "group": "story1", "must_flag": "R3", "flagged": ["R3"],
                 "category": "current AU is a work accident", "ok": True,
                 "outcome": "detected", "findings": []},
            ],
        }
        path = SUSIEHandler.reports_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def test_stories_categories_and_case_shape(self):
        self._write_story_fixture()
        stories = self._get_state()["stories"]
        self.assertTrue(stories["ok"])
        self.assertEqual(stories["count"], 3)
        self.assertEqual(stories["by_story"], {"1": 2, "4": 1})
        self.assertEqual(stories["categories"], [
            {"story": 1, "category": "current AU is a work accident", "count": 2, "must_flag": None},
            {"story": 4, "category": "88 cancels the 41", "count": 1, "must_flag": "F-88-UR"},
        ])
        first = stories["cases"][0]
        self.assertEqual(first["id"], "S1-001")
        self.assertEqual(first["story"], 1)
        self.assertEqual(first["must_flag"], None)
        self.assertEqual(first["observed_kind"], "correct output")
        self.assertEqual(first["scenario_summary"]["current"],
                         {"start": "2026-03-04", "end": "2026-03-27", "cert": True,
                          "insurance": "GKV", "reason": "work accident"})
        self.assertEqual(first["scenario_summary"]["prior_count"], 2)
        self.assertEqual(first["scenario_summary"]["prior_certified"], 1)
        self.assertEqual(first["scenario_summary"]["today"], "2026-03-04")
        self.assertEqual(first["expected"], {"send_41": True, "dbvo": {"ABGABEGRUND": "41", "ANZAHL-AU": 1}})
        self.assertEqual(len(stories["cases"]), 3)

    def test_reviews_newest_first_and_capped(self):
        for i in range(1, 12):  # 11 reports; only the newest 10 may surface
            report_id = f"RPT-20260101-0000{i:02d}"
            self._write_report(report_id + ".json", report_id,
                               n_findings=55 if i == 11 else 1)
        reviews = self._get_state()["reviews"]
        self.assertEqual(len(reviews), 10)
        self.assertEqual(reviews[0]["file"], "RPT-20260101-000011.json")
        self.assertEqual(reviews[-1]["file"], "RPT-20260101-000002.json")
        newest = reviews[0]
        self.assertEqual(newest["id"], "RPT-20260101-000011")
        self.assertEqual(newest["created_at"], "01.01.2026 00:00")
        self.assertEqual(newest["overall_status"], "PASS")
        self.assertEqual(newest["counts"]["PASS"], 55)
        self.assertEqual(newest["test_case_id"], "TC-RPT-20260101-000011")
        self.assertEqual(len(newest["findings"]), 50)  # findings capped at 50
        self.assertEqual(newest["robustness"], {"result": "1/1 stopped", "reason": None})
        self.assertEqual(newest["review"], {"reviewer": None, "decision": "pending", "timestamp": None})
        self.assertIsNone(newest["trace_url"])

    def test_harness_newest_summary_passthrough(self):
        self._write_harness("harness-HARNESS-old.json", "HARNESS-old", mtime=1000)
        self._write_harness("harness-HARNESS-20260103-000000.json", "HARNESS-20260103",
                            mtime=2000)
        harness = self._get_state()["harness"]
        self.assertEqual(harness["run_id"], "HARNESS-20260103")  # newest by mtime
        self.assertEqual(harness["file"], "harness-HARNESS-20260103-000000.json")
        self.assertIn("T", harness["created_at"])  # ISO timestamp
        self.assertEqual(harness["cases"], 2)
        self.assertEqual(harness["correct"], 2)
        self.assertEqual(harness["false_alarms"], 0)
        self.assertEqual(harness["clean_cases"], 1)
        self.assertEqual(harness["detected"], 1)
        self.assertEqual(harness["must_flag_cases"], 1)
        self.assertEqual(harness["by_category"],
                         {"story1 | current AU is a work accident": {"clean": 1, "detected": 1}})
        self.assertEqual(harness["results"], [
            {"id": "S1-001", "group": "story1", "must_flag": None, "flagged": [],
             "category": "current AU is a work accident", "ok": True, "outcome": "clean"},
            {"id": "S1-002", "group": "story1", "must_flag": "R3", "flagged": ["R3"],
             "category": "current AU is a work accident", "ok": True, "outcome": "detected"},
        ])

    def test_state_fail_soft_without_fixtures(self):
        SUSIEHandler.story_cases_path = Path(self.tmp.name) / "data" / "missing.json"
        SUSIEHandler.reports_path = Path(self.tmp.name) / "reports" / "nowhere"
        state = self._get_state()
        self.assertTrue(state["ok"])  # store payload survives
        self.assertEqual(len(state["cases"]), 4)
        self.assertFalse(state["stories"]["ok"])
        self.assertTrue(state["stories"]["error"])
        self.assertEqual(state["stories"]["cases"], [])
        self.assertEqual(state["reviews"], [])
        self.assertIsNone(state["harness"])


class _FakeGateway:
    """Offline stand-in for the LLM gateway — no network, no credentials."""

    def __init__(self, reply=None, error=None):
        self.reply = reply if reply is not None else {
            "utterance": "Ihr aktueller Stand: 4 Fälle, 1 Mismatch.",
            "citations": [{"kind": "state", "ref": "TC-1", "locator": ""}],
            "action": None,
            "confidence": "grounded",
        }
        self.error = error
        self.calls = []

    def __call__(self, endpoint, model, system_prompt, messages, token=""):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return json.dumps(self.reply)


class TestChatEndpoints(unittest.TestCase):
    """POST /api/chat, POST /api/action and GET /api/chat/history (T10-032):
    the fake gateway is injected at module level, so tests stay offline and
    credential-free; degraded mode must stay HTTP 200 with degraded: true."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.store = tmp / "store"
        frontend = tmp / "www"
        frontend.mkdir()
        (frontend / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
        # Absent index → corpus_search degrades to [] (hermetic, no real index).
        SUSIEHandler.index_path = tmp / "data" / "index" / "fts.sqlite"
        with contextlib.redirect_stdout(io.StringIO()):
            demo.run_demo(self.store, live=False, fresh=True)
        self.httpd, self.port = _serve(frontend, self.store)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        webserver.CHAT_GATEWAY = None  # never leak a fake into other tests
        SUSIEHandler.index_path = webserver.DEFAULT_INDEX
        self.tmp.cleanup()

    def _post(self, path, payload):
        status, body = _request(self.port, "POST", path, body=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json"})
        return status, json.loads(body)

    def _get(self, path):
        status, body = _request(self.port, "GET", path)
        return status, json.loads(body)

    def test_chat_endpoint_returns_envelope_and_persists_history(self):
        gateway = _FakeGateway()
        webserver.CHAT_GATEWAY = gateway
        status, payload = self._post(
            "/api/chat", {"session_id": "s1", "message": "Wo stehe ich?", "reviewer": ""})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["utterance"], gateway.reply["utterance"])
        self.assertEqual(payload["citations"], gateway.reply["citations"])
        self.assertEqual(payload["agent_run"]["role"], "susie_assistant")
        self.assertFalse(payload["degraded"])
        self.assertFalse(payload["needs_confirmation"])
        self.assertIsNone(payload["confirm_token"])
        # the gateway saw the message plus the assembled app-state context
        self.assertIn("Wo stehe ich?", gateway.calls[0][0]["content"])
        self.assertIn("APP-STATE", gateway.calls[0][0]["content"])
        # history: one user turn + one susie turn, ordered by id
        status, history = self._get("/api/chat/history?session_id=s1")
        self.assertEqual(status, 200)
        self.assertTrue(history["ok"])
        self.assertEqual([t["id"] for t in history["turns"]], ["CHAT-1", "CHAT-2"])
        self.assertEqual([t["role"] for t in history["turns"]], ["user", "susie"])
        self.assertEqual(history["turns"][0]["message"], "Wo stehe ich?")
        self.assertEqual(history["turns"][1]["utterance"], gateway.reply["utterance"])
        self.assertEqual(history["turns"][1]["agent_run"]["role"], "susie_assistant")
        # the append-only event log carries both sides
        chat_events = [e for e in Store(self.store).events() if e["kind"] == "chat_turn"]
        self.assertEqual([e["id"] for e in chat_events], ["CHAT-1", "CHAT-2"])

    def test_chat_endpoint_degraded_when_gateway_down(self):
        webserver.CHAT_GATEWAY = _FakeGateway(error=LLMError("gateway down"))
        status, payload = self._post(
            "/api/chat", {"session_id": "s1", "message": "Wo stehe ich?"})
        self.assertEqual(status, 200)  # degraded is honest data, not an error
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["degraded"])
        self.assertEqual(payload["utterance"], chat.DEGRADED_UTTERANCE)
        self.assertIsNone(payload["action"])
        self.assertIsNone(payload["confirm_token"])
        self.assertEqual(payload["agent_run"]["status"], "error")
        # even the degraded turn is fully audited on both sides
        _, history = self._get("/api/chat/history?session_id=s1")
        self.assertEqual([t["role"] for t in history["turns"]], ["user", "susie"])

    def test_action_endpoint_refuses_missing_token(self):
        status, payload = self._post("/api/action", {
            "session_id": "s1", "action_id": "save_note",
            "params": {"text": "x", "case_id": "TC-1"},
            "confirm_token": None, "reviewer": "reviewer1"})
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])
        self.assertEqual(Store(self.store).all("note"), [])

    def test_action_endpoint_executes_with_token(self):
        params = {"text": "Boundary 41 prüfen", "case_id": "TC-1"}
        proposed = actions.propose("save_note", params, "s1")
        self.assertIsNotNone(proposed["confirm_token"])
        status, payload = self._post("/api/action", {
            "session_id": "s1", "action_id": "save_note", "params": params,
            "confirm_token": proposed["confirm_token"], "reviewer": "reviewer1"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"], {"executed": True, "mode": "server"})
        notes = Store(self.store).all("note")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "Boundary 41 prüfen")
        self.assertEqual(notes[0]["author"], "reviewer1")
        # the token was consumed: replaying it must fail closed with 403
        status, payload = self._post("/api/action", {
            "session_id": "s1", "action_id": "save_note", "params": params,
            "confirm_token": proposed["confirm_token"], "reviewer": "reviewer1"})
        self.assertEqual(status, 403)
        self.assertEqual(len(Store(self.store).all("note")), 1)

    def test_chat_history_requires_session_id(self):
        for path in ("/api/chat/history", "/api/chat/history?session_id="):
            status, payload = self._get(path)
            self.assertEqual(status, 400)
            self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
