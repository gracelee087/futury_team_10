"""Stdlib-unittest port of seal/test_seal.py (T10-034 gap fix A).

The pytest original stays in seal/test_seal.py (adopted verbatim); this port
is the version our verification contract runs (`python3 -m unittest discover
-s tests`, stdlib only). Coverage is 1:1 with the original, including the
parametrized cases (expanded as subTests) plus the T10-034 SÜSIE integration
test for the demo's optional --seal step.

A real seal server runs in a thread on a random port with a temp ledger.
"""
from __future__ import annotations

import contextlib
import copy
import http.client
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEAL_DIR = ROOT / "seal"
sys.path.insert(0, str(SEAL_DIR))

import client as seal_client  # noqa: E402
import server as seal_server  # noqa: E402
import verify as seal_verify  # noqa: E402
from seal_common import canonical, make_mac, report_hash, sha256_hex  # noqa: E402

VENDOR, ADMIN, SECRET = "vendor-token-abc", "admin-token-xyz", "test-secret-123"
REPORT = {"report": {"id": "RPT-1", "overall_status": "MISMATCH"},
          "findings": [{"id": "C2", "status": "MISMATCH", "note": "Stornierung fehlt"}]}


class SealServerTestCase(unittest.TestCase):
    """One seal server per test: random port, temp ledger, throwaway tokens."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.tmp_path = tmp
        self.env = {"SEAL_SECRET": SECRET, "SEAL_VENDOR_TOKEN": VENDOR, "SEAL_ADMIN_TOKEN": ADMIN,
                    "SEAL_LEDGER": str(tmp / "ledger.jsonl")}
        self.httpd = seal_server.make_server(self.env, "127.0.0.1", 0)
        self.srv = type("Srv", (), {})()
        self.srv.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.srv.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()

    # -- helpers (ported from the pytest fixtures/helpers) --------------------
    def raw(self, method, path, token=None, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        hdrs = dict(headers or {})
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, json.loads(payload)

    def sealed_run(self, report=REPORT):
        run = seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur")
        path = self.tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        res = seal_client.submit(path, url=self.srv.url, token=VENDOR,
                                 state_file=self.tmp_path / "cur")
        return run, path, Path(res["receipt_file"]), res["receipt"]

    def check(self, report_path, receipt_path):
        return seal_verify.verify_files(report_path, receipt_path, self.srv.url, ADMIN)


class TestSealVerification(SealServerTestCase):
    def test_genuine_report_verifies(self):
        _, rpt, rcpt, receipt = self.sealed_run()
        result = self.check(rpt, rcpt)
        self.assertEqual(result["result"], "GENUINE")
        self.assertEqual(receipt["report_sha256"], report_hash(REPORT))
        self.assertEqual(receipt["seq"], 2)

    def test_key_order_and_whitespace_do_not_matter(self):
        _, rpt, rcpt, _ = self.sealed_run()
        rpt.write_text(json.dumps(REPORT, indent=4, sort_keys=True), encoding="utf-8")
        self.assertEqual(self.check(rpt, rcpt)["result"], "GENUINE")

    def test_one_changed_character_is_tampered(self):
        _, rpt, rcpt, _ = self.sealed_run()
        edited = copy.deepcopy(REPORT)
        edited["findings"][0]["note"] = "Stornierung fehlt."
        rpt.write_text(json.dumps(edited), encoding="utf-8")
        res = self.check(rpt, rcpt)
        self.assertEqual(res["result"], "TAMPERED")
        self.assertIn("differs", res["reason"])

    def test_mismatch_turned_into_pass_is_tampered(self):
        _, rpt, rcpt, _ = self.sealed_run()
        edited = copy.deepcopy(REPORT)
        edited["findings"][0]["status"] = "PASS"
        rpt.write_text(json.dumps(edited), encoding="utf-8")
        self.assertEqual(self.check(rpt, rcpt)["result"], "TAMPERED")

    def test_forged_mac_is_tampered(self):
        _, rpt, rcpt, receipt = self.sealed_run()
        receipt["mac"] = "0" * 64
        rcpt.write_text(json.dumps(receipt), encoding="utf-8")
        res = self.check(rpt, rcpt)
        self.assertEqual(res["result"], "TAMPERED")
        self.assertIn("MAC", res["reason"])

    def test_receipt_with_edited_hash_is_tampered(self):
        # vendor edits the report AND rewrites the hash in the receipt: the MAC no longer fits
        _, rpt, rcpt, receipt = self.sealed_run()
        edited = copy.deepcopy(REPORT)
        edited["findings"][0]["status"] = "PASS"
        receipt["report_sha256"] = report_hash(edited)
        rpt.write_text(json.dumps(edited), encoding="utf-8")
        rcpt.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(self.check(rpt, rcpt)["result"], "TAMPERED")

    def test_unknown_run_id(self):
        _, rpt, rcpt, receipt = self.sealed_run()
        receipt["run_id"] = "RUN-" + "ab" * 12
        rcpt.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertEqual(self.check(rpt, rcpt)["result"], "UNKNOWN_RUN")

    def test_malformed_receipt_is_tampered_not_a_crash(self):
        _, rpt, rcpt, _ = self.sealed_run()
        for bad in ({}, {"run_id": 5},
                    {"run_id": "x", "report_sha256": "y", "issued_at": 1, "submitted_at": 2,
                     "seq": "3", "mac": 4}):
            with self.subTest(bad=bad):
                rcpt.write_text(json.dumps(bad), encoding="utf-8")
                self.assertEqual(self.check(rpt, rcpt)["result"], "TAMPERED")

    def test_old_receipt_does_not_validate_a_different_report(self):
        _, _, rcpt, _ = self.sealed_run()
        other = self.tmp_path / "other.json"
        other.write_text(json.dumps({"older": "report"}), encoding="utf-8")
        self.assertEqual(self.check(other, rcpt)["result"], "TAMPERED")


class TestSealReplayAndAuth(SealServerTestCase):
    def test_second_submit_for_same_run_is_rejected(self):
        run, rpt, _, _ = self.sealed_run()
        other = self.tmp_path / "other.json"
        other.write_text(json.dumps({"different": True}), encoding="utf-8")
        with self.assertRaisesRegex(seal_client.SealError, "409"):
            seal_client.submit(other, run_id=run["run_id"], url=self.srv.url, token=VENDOR)

    def test_replaying_an_old_report_for_a_new_run_is_rejected(self):
        _, rpt, _, _ = self.sealed_run()
        new_run = seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur2")
        with self.assertRaisesRegex(seal_client.SealError, "409"):
            seal_client.submit(rpt, run_id=new_run["run_id"], url=self.srv.url, token=VENDOR)

    def test_submit_for_unknown_run_is_404(self):
        status, body = self.raw("POST", "/runs/RUN-" + "0" * 24 + "/submit", VENDOR,
                                {"report_sha256": "a" * 64})
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_wrong_or_missing_token_is_rejected(self):
        cases = [("POST", "/runs/start", None), ("POST", "/runs/start", "wrong"),
                 ("POST", "/runs/start", ADMIN),
                 ("GET", "/runs", None), ("GET", "/runs", VENDOR), ("GET", "/runs", "wrong"),
                 ("POST", "/verify", None), ("POST", "/verify", VENDOR),
                 ("POST", "/runs/RUN-" + "0" * 24 + "/submit", ADMIN)]
        for method, path, token in cases:
            with self.subTest(method=method, path=path, token=token):
                status, body = self.raw(method, path, token, {} if method == "POST" else None)
                self.assertEqual(status, 401)
                self.assertIn("error", body)

    def test_runs_lists_unsubmitted_runs(self):
        first, *_ = self.sealed_run()
        hidden = seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur3")
        data = seal_verify.list_runs(self.srv.url, ADMIN)
        by_id = {r["run_id"]: r for r in data["runs"]}
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["never_submitted"], 1)
        self.assertTrue(by_id[first["run_id"]]["submitted"])
        self.assertFalse(by_id[hidden["run_id"]]["submitted"])
        self.assertIn("NEVER SUBMITTED", seal_verify.format_runs(data))


class TestSealLedger(SealServerTestCase):
    def test_editing_a_past_ledger_line_is_detected(self):
        _, rpt, rcpt, _ = self.sealed_run()
        seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur3")
        ledger = Path(self.env["SEAL_LEDGER"])
        lines = ledger.read_text(encoding="utf-8").split("\n")
        lines[0] = lines[0].replace("start", "stark", 1)  # edit the first line only
        ledger.write_text("\n".join(lines), encoding="utf-8")
        res = self.check(rpt, rcpt)
        self.assertEqual(res["result"], "LEDGER_TAMPERED")
        self.assertIn("line 1", res["reason"])
        self.assertEqual(seal_verify.list_runs(self.srv.url, ADMIN)["result"], "LEDGER_TAMPERED")
        with self.assertRaisesRegex(seal_client.SealError, "503"):  # damaged ledger: no new runs
            seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur4")

    def test_editing_the_last_ledger_line_or_removing_a_middle_line_is_detected(self):
        self.sealed_run()
        seal_client.start_run(self.srv.url, VENDOR, state_file=self.tmp_path / "cur3")
        ledger = Path(self.env["SEAL_LEDGER"])
        original = ledger.read_text(encoding="utf-8")
        lines = original.strip().split("\n")

        last_edited = lines[:-1] + [lines[-1].replace("issued_at", "issued_xx", 1)]
        ledger.write_text("\n".join(last_edited) + "\n", encoding="utf-8")
        self.assertIsNotNone(seal_server.Ledger(ledger, SECRET.encode()).read()[1])

        ledger.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")  # delete line 2
        self.assertIsNotNone(seal_server.Ledger(ledger, SECRET.encode()).read()[1])

        ledger.write_bytes(original.encode("utf-8"))
        self.assertIsNone(seal_server.Ledger(ledger, SECRET.encode()).read()[1])

    def test_ledger_is_hash_chained_and_append_only(self):
        self.sealed_run()
        lines = Path(self.env["SEAL_LEDGER"]).read_text(encoding="utf-8").strip().split("\n")
        entries = [json.loads(line) for line in lines]
        self.assertEqual(entries[0]["prev"], "0" * 64)
        for prev_line, entry in zip(lines, entries[1:]):
            self.assertEqual(entry["prev"], sha256_hex(prev_line))
        self.assertEqual([e["seq"] for e in entries], [1, 2])

    def test_ledger_survives_server_restart(self):
        first = seal_server.make_server(self.env, "127.0.0.1", 0)
        status, body = first.app.start_run()
        first.server_close()
        second = seal_server.make_server(self.env, "127.0.0.1", 0)
        runs = second.app.runs()[1]["runs"]
        second.server_close()
        self.assertEqual(status, 201)
        self.assertEqual([r["run_id"] for r in runs], [body["run_id"]])

    def test_ledger_mac_depends_on_secret(self):
        srv_a = seal_server.make_server(self.env, "127.0.0.1", 0)
        srv_a.app.start_run()
        srv_a.server_close()
        other = dict(self.env, SEAL_SECRET="another-secret")
        self.assertIsNotNone(
            seal_server.Ledger(Path(self.env["SEAL_LEDGER"]), b"another-secret").read()[1])
        self.assertNotEqual(make_mac(b"a", "receipt", {"x": 1}), make_mac(b"b", "receipt", {"x": 1}))
        self.assertNotEqual(make_mac(b"a", "receipt", {"x": 1}), make_mac(b"a", "ledger", {"x": 1}))
        self.assertEqual(canonical({"b": 1, "a": "ä"}), '{"a":"ä","b":1}')


class TestSealServerHardening(SealServerTestCase):
    def test_missing_secret_refuses_to_start(self):
        for missing in ("SEAL_SECRET", "SEAL_VENDOR_TOKEN", "SEAL_ADMIN_TOKEN"):
            with self.subTest(missing=missing):
                env = dict(self.env)
                env.pop(missing)
                with self.assertRaisesRegex(seal_server.ConfigError, missing):
                    seal_server.make_server(env, "127.0.0.1", 0)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = seal_server.main(env)
                self.assertEqual(code, 2)
                self.assertIn(missing, err.getvalue())
                self.assertNotIn(SECRET, err.getvalue())
                self.assertNotIn(VENDOR, err.getvalue())

    def test_empty_secret_refuses_to_start(self):
        env = dict(self.env, SEAL_SECRET="   ")
        with self.assertRaises(seal_server.ConfigError):
            seal_server.make_server(env, "127.0.0.1", 0)

    def test_oversized_body_gets_clean_413(self):
        status, body = self.raw("POST", "/verify", ADMIN,
                                headers={"Content-Length": str(seal_server.MAX_BODY + 1)})
        self.assertEqual(status, 413)
        self.assertIn("error", body)
        big = json.dumps({"report": {"x": "a" * seal_server.MAX_BODY}, "receipt": {}}).encode()
        status, body = self.raw("POST", "/verify", ADMIN, big)
        self.assertEqual(status, 413)

    def test_malformed_verify_bodies_give_clean_400(self):
        bodies = [b"not json", b"[1,2]", b'{"report": 1, "receipt": 2}', b'{"report": {}}',
                  b'{"report": {}, "receipt": {}, "extra": 1}', b"\xff\xfe",
                  b'{"report": NaN, "receipt": {}}', b"[" * 5000 + b"]" * 5000]
        for body in bodies:
            with self.subTest(body=body[:20]):
                status, resp = self.raw("POST", "/verify", ADMIN, body)
                self.assertEqual(status, 400)
                self.assertEqual(list(resp), ["error"])

    def test_malformed_submit_bodies_give_clean_400(self):
        bodies = [b"not json", {"report_sha256": "ABC"}, {"report_sha256": "a" * 63},
                  {"report_sha256": 5}, {"report_sha256": "a" * 64, "x": 1}, {}, [1]]
        run = self.httpd.app.start_run()[1]
        for body in bodies:
            with self.subTest(body=body):
                status, resp = self.raw("POST", f"/runs/{run['run_id']}/submit", VENDOR, body)
                self.assertEqual(status, 400)
                self.assertEqual(list(resp), ["error"])

    def test_bad_run_id_format_and_unknown_routes(self):
        self.assertIn(self.raw("POST", "/runs/../../etc/submit", VENDOR,
                               {"report_sha256": "a" * 64})[0], (400, 404))
        self.assertEqual(self.raw("POST", "/runs/not-a-run/submit", VENDOR,
                                  {"report_sha256": "a" * 64})[0], 400)
        self.assertEqual(self.raw("GET", "/nothing", ADMIN)[0], 404)
        self.assertEqual(self.raw("PUT", "/runs", ADMIN)[0], 405)

    def test_errors_never_contain_stack_traces_or_secrets(self):
        status, body = self.raw("POST", "/verify", ADMIN, b"{bad")
        text = json.dumps(body)
        self.assertNotIn("Traceback", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(ADMIN, text)

    def test_secrets_are_not_logged(self):
        with self.assertLogs("seal.server", level="DEBUG") as captured:
            self.sealed_run()
            self.raw("GET", "/runs", "wrong-token-value")
        self.assertTrue(captured.records)
        for secret in (SECRET, VENDOR, ADMIN, "wrong-token-value"):
            self.assertNotIn(secret, captured.output.__str__())


class TestSusieSealIntegration(SealServerTestCase):
    """T10-034 gap fix B: the SÜSIE demo's optional --seal step against a real seal server."""

    def test_demo_report_seals_and_verifies_genuine(self):
        from itsg import demo

        store_root = self.tmp_path / "demo"
        demo.run_demo(store_root, live=False, fresh=True, seal=True,
                      seal_url=self.srv.url, seal_vendor_token=VENDOR,
                      seal_admin_token=ADMIN)
        artifact = store_root / "report.artifact.json"
        receipt_file = store_root / "report.artifact.json.receipt.json"
        self.assertTrue(receipt_file.exists(), "receipt must be saved next to the report")
        result = seal_verify.verify_files(artifact, receipt_file, self.srv.url, ADMIN)
        self.assertEqual(result["result"], "GENUINE")

    def test_demo_without_seal_flag_writes_no_receipt(self):
        from itsg import demo

        store_root = self.tmp_path / "demo"
        demo.run_demo(store_root, live=False, fresh=True)
        self.assertFalse((store_root / "report.artifact.json.receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
