"""ITSG receipt office: issues run IDs, seals report hashes, keeps an append-only hash-chained ledger.

Environment (the first three are required, never printed or logged):
  SEAL_SECRET        HMAC key
  SEAL_VENDOR_TOKEN  token the software vendor uses to start and submit runs
  SEAL_ADMIN_TOKEN   token ITSG uses to list runs and verify reports
Optional: SEAL_LEDGER (default ./seal-data/ledger.jsonl), SEAL_HOST (127.0.0.1), SEAL_PORT (8080).
"""
import json
import logging
import os
import secrets
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from seal_common import (HEX64_RE, RECEIPT_FIELDS, RUN_ID_RE, ZERO_HASH, canonical, make_mac, receipt_mac,
                         report_hash, same, sha256_hex)

MAX_BODY = 1024 * 1024  # 1 MB
REQUEST_TIMEOUT = 10  # seconds a client may take to send its request

log = logging.getLogger("seal.server")


class ConfigError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    """Append-only JSON lines. Every line has a MAC and the sha256 of the previous line."""

    def __init__(self, path, secret: bytes):
        self.path, self.secret = Path(path), secret

    def _entry_mac(self, entry: dict) -> str:
        return make_mac(self.secret, "ledger", {k: v for k, v in entry.items() if k != "mac"})

    def read(self):
        """Returns (entries, error). error is None when the whole chain is intact."""
        if not self.path.exists():
            return [], None
        try:
            lines = self.path.read_bytes().decode("utf-8").split("\n")
        except (OSError, UnicodeDecodeError):
            return [], "ledger file cannot be read"
        if lines and lines[-1] == "":
            lines.pop()
        entries, prev = [], ZERO_HASH
        for i, line in enumerate(lines, start=1):
            try:
                entry = json.loads(line)
            except ValueError:
                return [], f"line {i} is not valid JSON"
            if not isinstance(entry, dict) or not isinstance(entry.get("mac"), str):
                return [], f"line {i} has no MAC"
            if line != canonical(entry):
                return [], f"line {i} was edited (not in canonical form)"
            if entry.get("seq") != i:
                return [], f"line {i} has the wrong sequence number"
            if entry.get("prev") != prev:
                return [], f"line {i} does not follow line {i - 1} (hash chain broken)"
            if not same(self._entry_mac(entry), entry["mac"]):
                return [], f"line {i} has an invalid MAC (entry edited)"
            if entry.get("type") not in ("start", "submit"):
                return [], f"line {i} has an unknown entry type"
            entries.append(entry)
            prev = sha256_hex(line)
        return entries, None

    def append(self, entries: list, entry: dict) -> dict:
        """Add one entry after `entries` (already verified). Writes and fsyncs before returning."""
        prev = sha256_hex(canonical(entries[-1])) if entries else ZERO_HASH
        entry = {**entry, "seq": len(entries) + 1, "prev": prev}
        entry["mac"] = self._entry_mac(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "ab") as fh:
            fh.write((canonical(entry) + "\n").encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        return entry


class SealApp:
    def __init__(self, env):
        names = ("SEAL_SECRET", "SEAL_VENDOR_TOKEN", "SEAL_ADMIN_TOKEN")
        missing = [k for k in names if not (env.get(k) or "").strip()]
        if missing:
            raise ConfigError("missing environment variable(s): " + ", ".join(missing))
        self.secret = env["SEAL_SECRET"].encode("utf-8")
        self.vendor_token = env["SEAL_VENDOR_TOKEN"]
        self.admin_token = env["SEAL_ADMIN_TOKEN"]
        self.ledger = Ledger(env.get("SEAL_LEDGER") or "./seal-data/ledger.jsonl", self.secret)
        self.lock = threading.Lock()

    # ---- operations: each returns (http_status, json_body) --------------------

    def start_run(self):
        with self.lock:
            entries, err = self.ledger.read()
            if err:
                return 503, {"error": "ledger is damaged, no new runs", "result": "LEDGER_TAMPERED", "reason": err}
            entry = self.ledger.append(entries, {"type": "start", "run_id": "RUN-" + secrets.token_hex(12),
                                                 "issued_at": now()})
        log.info("run started %s", entry["run_id"])
        return 201, {"run_id": entry["run_id"], "issued_at": entry["issued_at"]}

    def submit(self, run_id: str, body):
        if not RUN_ID_RE.match(run_id):
            return 400, {"error": "invalid run_id format"}
        if not isinstance(body, dict) or set(body) != {"report_sha256"}:
            return 400, {"error": 'body must be exactly {"report_sha256": "<64 hex>"}'}
        digest = body["report_sha256"]
        if not isinstance(digest, str) or not HEX64_RE.match(digest):
            return 400, {"error": "report_sha256 must be 64 lowercase hex characters"}
        with self.lock:
            entries, err = self.ledger.read()
            if err:
                return 503, {"error": "ledger is damaged, no new receipts", "result": "LEDGER_TAMPERED", "reason": err}
            start = next((e for e in entries if e["type"] == "start" and e["run_id"] == run_id), None)
            if start is None:
                return 404, {"error": "unknown run_id"}
            if any(e["type"] == "submit" and e["run_id"] == run_id for e in entries):
                return 409, {"error": "this run already has a receipt"}
            if any(e["type"] == "submit" and e["report_sha256"] == digest for e in entries):
                return 409, {"error": "this report hash was already submitted for another run (replay)"}
            entry = self.ledger.append(entries, {"type": "submit", "run_id": run_id, "report_sha256": digest,
                                                 "submitted_at": now()})
            receipt = {"run_id": run_id, "report_sha256": digest, "issued_at": start["issued_at"],
                       "submitted_at": entry["submitted_at"], "seq": entry["seq"]}
            receipt["mac"] = receipt_mac(self.secret, receipt)
        log.info("receipt issued %s", run_id)
        return 200, receipt

    def runs(self):
        with self.lock:
            entries, err = self.ledger.read()
        if err:
            return 409, {"result": "LEDGER_TAMPERED", "reason": err}
        submits = {e["run_id"]: e for e in entries if e["type"] == "submit"}
        runs = []
        for e in entries:
            if e["type"] != "start":
                continue
            s = submits.get(e["run_id"])
            runs.append({"run_id": e["run_id"], "issued_at": e["issued_at"], "submitted": s is not None,
                         "submitted_at": s["submitted_at"] if s else None,
                         "report_sha256": s["report_sha256"] if s else None})
        return 200, {"runs": runs, "total": len(runs), "never_submitted": sum(not r["submitted"] for r in runs)}

    def verify(self, body):
        if not isinstance(body, dict) or set(body) != {"report", "receipt"} \
                or not isinstance(body["report"], dict) or not isinstance(body["receipt"], dict):
            return 400, {"error": 'body must be {"report": {...}, "receipt": {...}}'}
        report, receipt = body["report"], body["receipt"]
        with self.lock:
            entries, err = self.ledger.read()
        if err:
            return 200, {"result": "LEDGER_TAMPERED", "reason": err}

        def out(result, reason):
            return 200, {"result": result, "reason": reason}

        if set(receipt) != set(RECEIPT_FIELDS) | {"mac"}:
            return out("TAMPERED", "receipt has missing or extra fields")
        if not (isinstance(receipt["run_id"], str) and RUN_ID_RE.match(receipt["run_id"])
                and isinstance(receipt["report_sha256"], str) and HEX64_RE.match(receipt["report_sha256"])
                and isinstance(receipt["issued_at"], str) and isinstance(receipt["submitted_at"], str)
                and type(receipt["seq"]) is int and isinstance(receipt["mac"], str)):
            return out("TAMPERED", "receipt fields have the wrong format")
        start = next((e for e in entries if e["type"] == "start" and e["run_id"] == receipt["run_id"]), None)
        if start is None:
            return out("UNKNOWN_RUN", "this run_id was never issued by ITSG")
        if not same(receipt_mac(self.secret, receipt), receipt["mac"]):
            return out("TAMPERED", "receipt MAC is invalid (receipt forged or edited)")
        sub = next((e for e in entries if e["type"] == "submit" and e["run_id"] == receipt["run_id"]), None)
        if sub is None:
            return out("TAMPERED", "the ledger has no submission for this run")
        if not (sub["report_sha256"] == receipt["report_sha256"] and sub["submitted_at"] == receipt["submitted_at"]
                and start["issued_at"] == receipt["issued_at"] and sub["seq"] == receipt["seq"]):
            return out("TAMPERED", "receipt does not match the ledger entry")
        if report_hash(report) != receipt["report_sha256"]:
            return out("TAMPERED", "report content differs from the report that was submitted")
        return out("GENUINE", "receipt is valid and the report matches the sealed hash")


def _reject_constant(name):
    raise ValueError(f"invalid JSON constant {name}")


class Handler(BaseHTTPRequestHandler):
    server_version = "SealServer"
    sys_version = ""
    timeout = REQUEST_TIMEOUT

    def log_message(self, fmt, *args):  # never log headers (they hold tokens)
        log.info("%s %s", self.command, self.path.split("?")[0][:80])

    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, token: str) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return same(header[7:].strip(), token)

    def _drain(self):
        """Read and drop an unwanted request body (up to 2 MB) so the client gets our answer, not a reset."""
        try:
            left = min(int(self.headers.get("Content-Length") or 0), 2 * MAX_BODY)
        except ValueError:
            return
        try:
            self.connection.settimeout(1)  # a client that announced a body but sends none must not hold us up
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
        except OSError:
            pass

    def _read_body(self):
        """Returns (obj, error_response). An empty body gives obj=None."""
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return None, None
        if not raw_len.isdigit():
            return None, (400, {"error": "invalid Content-Length"})
        length = int(raw_len)
        if length > MAX_BODY:
            self.close_connection = True
            self._drain()  # the oversized body is dropped, never parsed
            return None, (413, {"error": f"body larger than {MAX_BODY} bytes"})
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None, None
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant), None
        except (ValueError, RecursionError):
            return None, (400, {"error": "body is not valid JSON"})

    def _route(self, method):
        app: SealApp = self.server.app
        path = self.path.split("?")[0].rstrip("/")
        parts = path.strip("/").split("/")
        if method == "POST" and path == "/runs/start":
            return self._guarded(app.vendor_token, lambda body: app.start_run(), read_body=False)
        if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "submit":
            return self._guarded(app.vendor_token, lambda body: app.submit(parts[1], body))
        if method == "GET" and path == "/runs":
            return self._guarded(app.admin_token, lambda body: app.runs(), read_body=False)
        if method == "POST" and path == "/verify":
            return self._guarded(app.admin_token, app.verify)
        return self._send(404, {"error": "not found"})

    def _guarded(self, token, fn, read_body=True):
        if not self._authorized(token):
            self.close_connection = True
            self._drain()
            return self._send(401, {"error": "missing or wrong token"})
        body, err = self._read_body() if read_body else (None, None)
        return self._send(*(err or fn(body)))

    def _handle(self, method):
        try:
            self._route(method)
        except (BrokenPipeError, ConnectionError, TimeoutError):
            pass
        except Exception as exc:  # no stack trace to the client; log only the type
            log.error("internal error: %s", type(exc).__name__)
            try:
                self._send(500, {"error": "internal error"})
            except Exception:
                pass

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _not_allowed(self):
        self.close_connection = True
        self._send(405, {"error": "method not allowed"})

    do_PUT = do_DELETE = do_PATCH = _not_allowed


def make_server(env=None, host="127.0.0.1", port=8080) -> ThreadingHTTPServer:
    env = os.environ if env is None else env
    app = SealApp(env)  # raises ConfigError if a secret is missing
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.app = app
    return httpd


def main(env=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    env = os.environ if env is None else env
    try:
        httpd = make_server(env, env.get("SEAL_HOST") or "127.0.0.1", int(env.get("SEAL_PORT") or 8080))
    except ConfigError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 2
    entries, err = httpd.app.ledger.read()
    state = f"OK, {len(entries)} entries" if not err else f"LEDGER_TAMPERED - {err}"
    print(f"ledger {httpd.app.ledger.path}: {state}")
    print(f"listening on {httpd.server_address[0]}:{httpd.server_address[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
