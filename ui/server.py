"""Team 10 demo server: serves ui/ (and figures/) plus a small JSON API over the existing parts.

  python ui/server.py            ->  http://localhost:8000

Python standard library only. Secrets (HESSIAN_API_KEY, SEAL_*) stay on the server and are never
sent to the browser or written to the log. Everything shown to the user comes from the real parts
(run_review.py, harness, retrieval, seal); a part that is missing is reported "unavailable".

Environment: UI_HOST (default 0.0.0.0), UI_PORT (default 8000), HESSIAN_API_KEY,
SEAL_URL, SEAL_VENDOR_TOKEN, SEAL_ADMIN_TOKEN, PRIVACY_KEY (min. 16 characters), RETENTION_DAYS (default 7).
A .env file in the repository root is read first;
real environment variables win.
"""
import copy
import hashlib
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_review import load_env  # noqa: E402  (the repo's own .env reader)
from privacy import schleuse  # noqa: E402  (privacy airlock, T10-007)

UI_VERSION = "ui-1.0"
MAX_BODY = 64 * 1024
MAX_QUESTION = 500
MAX_COMMENT = 1000
MAX_NAME = 80
REVIEW_TIMEOUT = 120
HARNESS_TIMEOUT = 120
ASK_TIMEOUT = 90
SEAL_TIMEOUT = 10
PAGE_SIZE_MAX = 100
HISTORY_MAX = 500

DECISIONS = ("approve", "reject", "needs_changes")
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
                ".ico": "image/x-icon"}
STATIC_ROOTS = ("figures",)  # besides ui/ itself
NEEDS_FAILURE = ("MISMATCH", "NOT EVALUATED", "BLOCKED", "NEEDS_REVIEW")
SECRET_ENV = ("HESSIAN_API_KEY", "SEAL_SECRET", "SEAL_VENDOR_TOKEN", "SEAL_ADMIN_TOKEN", "LANGFUSE_SECRET_KEY", "PRIVACY_KEY")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
REPORT_ID_RE = re.compile(r"^RPT-[0-9]{8}-[0-9]{6}$")

CSP = ("default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}

log = logging.getLogger("ui.server")
log.addFilter(schleuse.LogFilter())   # logs may hold no personal data at all


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


class RateLimiter:
    """At most `limit` hits per `window` seconds per key (the client IP)."""

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits, self.lock = {}, threading.Lock()

    def allow(self, key):
        now = self.clock()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self.hits) > 5000:  # forget idle clients
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= self.window]:
                    del self.hits[k]
            return True


class Config:
    def __init__(self, root=ROOT, reports_dir=None, env=None, ask_fn=None, clock=time.monotonic,
                 ask_limit=10, demo_limit=5):
        self.root = Path(root)
        self.ui_dir = self.root / "ui"
        self.reports_dir = Path(reports_dir) if reports_dir else self.root / "reports"
        self.env = os.environ if env is None else env
        self.ask_fn = ask_fn
        self.ask_limiter = RateLimiter(ask_limit, 60, clock)
        self.demo_limiter = RateLimiter(demo_limit, 60, clock)
        self.privacy_limiter = RateLimiter(20, 60, clock)
        self.leak_lock = threading.Lock()
        self.review_lock = threading.Lock()   # one review / harness subprocess at a time
        self.demo_lock = threading.Lock()
        self.events_lock = threading.Lock()
        self.ask_slots = threading.BoundedSemaphore(4)
        self._cases = {}


# ---------------------------------------------------------------- small helpers

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_text(value, field, max_len, required=True):
    if not isinstance(value, str):
        raise ApiError(400, f"'{field}' must be text.")
    value = value.strip()
    if required and not value:
        raise ApiError(400, f"'{field}' must not be empty.")
    if len(value) > max_len:
        raise ApiError(400, f"'{field}' is too long (maximum {max_len} characters).")
    if CONTROL.search(value):
        raise ApiError(400, f"'{field}' contains characters that are not allowed.")
    return value


def only_fields(body, allowed):
    if not isinstance(body, dict):
        raise ApiError(400, "The request body must be a JSON object.")
    extra = sorted(set(body) - set(allowed))
    if extra:
        raise ApiError(400, "Unknown field: " + ", ".join(extra[:3]) + ".")
    return body


def read_json_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ApiError(500, f"The file {Path(path).name} could not be read.") from None


def newest(directory, pattern):
    files = sorted(Path(directory).glob(pattern), key=lambda p: p.name)
    return files[-1] if files else None


def child_env():
    """Environment for run_review.py / the harness: no API key and no seal secrets."""
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_script(cfg, args, timeout):
    """Run a repo script with a fixed argument list (no shell). Returns (exit code, stdout)."""
    try:
        proc = subprocess.run([sys.executable, *args], cwd=cfg.root, capture_output=True, timeout=timeout,
                              env=child_env(), shell=False)
    except subprocess.TimeoutExpired:
        raise ApiError(504, f"The run took longer than {timeout} seconds and was stopped.") from None
    except OSError:
        raise ApiError(500, "The script could not be started.") from None
    tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
    if proc.returncode != 0:
        log.error("%s exited with %s: %s", Path(args[0]).name, proc.returncode, " | ".join(tail)[:300])
        raise ApiError(500, f"The script {Path(args[0]).name} failed (exit code {proc.returncode}).")
    return proc.stdout.decode("utf-8", "replace")


def file_hash(path):
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


# ---------------------------------------------------------------- review

def latest_report(cfg):
    path = newest(cfg.reports_dir, "RPT-*.json")
    if path is None:
        raise ApiError(404, "There is no review report yet. Click 'Run review' to create one.")
    return {"file": path.name, "data": read_json_file(path)}


def api_review_latest(cfg, ip, body, query):
    return latest_report(cfg)


def api_review_run(cfg, ip, body, query):
    with cfg.review_lock:
        before = {p.name for p in cfg.reports_dir.glob("RPT-*.json")}
        run_script(cfg, [str(cfg.root / "run_review.py")], REVIEW_TIMEOUT)
        fresh = sorted({p.name for p in cfg.reports_dir.glob("RPT-*.json")} - before)
        path = cfg.reports_dir / fresh[-1] if fresh else newest(cfg.reports_dir, "RPT-*.json")
        if path is None:
            raise ApiError(500, "The review ran but no report file was found.")
        return {"file": path.name, "data": read_json_file(path)}


# ---------------------------------------------------------------- test cases and harness

def load_cases(cfg):
    """Both case files, read-only, cached by modification time."""
    out, sig = [], []
    for name, source in (("testcases.json", "golden"), ("story_cases.json", "stories")):
        path = cfg.root / "data" / name
        try:
            sig.append((name, path.stat().st_mtime_ns))
        except OSError:
            sig.append((name, None))
    if cfg._cases.get("sig") == sig:
        return cfg._cases["cases"]
    for (name, source) in (("testcases.json", "golden"), ("story_cases.json", "stories")):
        path = cfg.root / "data" / name
        if not path.exists():
            continue
        for c in read_json_file(path):
            c = dict(c)
            c["source"] = source
            if source == "stories":
                c["group"] = "stories"
            out.append(c)
    cfg._cases = {"sig": sig, "cases": out}
    return out


def case_summary(c):
    return {"id": c.get("id"), "source": c["source"], "group": c.get("group"), "category": c.get("category"),
            "kind": c.get("observed_kind"), "must_flag": c.get("must_flag")}


def api_testcases(cfg, ip, body, query):
    source = query.get("source", "all")
    if source not in ("golden", "stories", "all"):
        raise ApiError(400, "'source' must be golden, stories or all.")
    cases = [c for c in load_cases(cfg) if source == "all" or c["source"] == source]
    facets = {"groups": sorted({str(c.get("group")) for c in cases}),
              "categories": sorted({str(c.get("category")) for c in cases}),
              "kinds": sorted({str(c.get("observed_kind")) for c in cases})}
    for key, field in (("group", "group"), ("category", "category"), ("kind", "observed_kind")):
        if query.get(key):
            cases = [c for c in cases if str(c.get(field)) == query[key]]
    q = check_text(query.get("q", ""), "q", 100, required=False).lower()
    if q:
        cases = [c for c in cases if q in f"{c.get('id')} {c.get('category')} {c.get('observed_kind')} "
                                         f"{c.get('group')}".lower()]
    try:
        page, size = int(query.get("page", 1)), int(query.get("page_size", 25))
    except ValueError:
        raise ApiError(400, "'page' and 'page_size' must be numbers.") from None
    if page < 1 or not 1 <= size <= PAGE_SIZE_MAX:
        raise ApiError(400, f"'page' must be 1 or more and 'page_size' between 1 and {PAGE_SIZE_MAX}.")
    total = len(cases)
    chunk = cases[(page - 1) * size:page * size]
    return {"total": total, "page": page, "page_size": size, "items": [case_summary(c) for c in chunk],
            "facets": facets}


def latest_harness(cfg, with_results=False):
    path = newest(cfg.reports_dir, "harness-*.json")
    if path is None:
        return None
    data = read_json_file(path)
    out = {"file": path.name, "summary": data.get("summary", {})}
    if with_results:
        out["results"] = {r["id"]: r for r in data.get("results", []) if isinstance(r, dict) and "id" in r}
    return out


def api_testcase_detail(cfg, ip, body, query, case_id=""):
    if not ID_RE.match(case_id):
        raise ApiError(400, "That test case id is not valid.")
    case = next((c for c in load_cases(cfg) if c.get("id") == case_id), None)
    if case is None:
        raise ApiError(404, "No test case with that id.")
    harness = latest_harness(cfg, with_results=True)
    result = harness["results"].get(case_id) if harness else None
    return {"case": case, "harness_result": result, "harness_file": harness["file"] if harness else None}


def api_harness_latest(cfg, ip, body, query):
    h = latest_harness(cfg)
    if h is None:
        raise ApiError(404, "There is no harness run yet. Use 'Run harness' to create one.")
    return h


def api_harness_run(cfg, ip, body, query):
    body = only_fields(body or {}, ("limit",))
    limit = body.get("limit", 300)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 300:
        raise ApiError(400, "'limit' must be a whole number from 1 to 300.")
    with cfg.review_lock:
        before = {p.name for p in cfg.reports_dir.glob("harness-*.json")}
        run_script(cfg, [str(cfg.root / "harness" / "run_harness.py"), "--limit", str(limit)], HARNESS_TIMEOUT)
        fresh = sorted({p.name for p in cfg.reports_dir.glob("harness-*.json")} - before)
        if not fresh:
            raise ApiError(500, "The harness ran but no result file was found.")
        data = read_json_file(cfg.reports_dir / fresh[-1])
        return {"file": fresh[-1], "summary": data.get("summary", {})}


# ---------------------------------------------------------------- ask the rulebook

def default_ask(question):
    from retrieval.ask import ask  # imported late: needs pydantic/openai, and the key is read here
    return ask(question)


def shape_answer(result):
    data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    return {"answer": data.get("answer"), "status": data.get("status"),
            "citations": [{k: c.get(k) for k in ("chunk_id", "section", "page", "quote", "match_level")}
                          for c in data.get("citations", [])],
            "validation_errors": list(data.get("validation_errors", [])), "audit": data.get("audit", {})}


def run_with_timeout(fn, seconds):
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # handed back to the request thread
            box["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError
    if "error" in box:
        raise box["error"]
    return box["value"]


def api_ask(cfg, ip, body, query, timeout=ASK_TIMEOUT):
    body = only_fields(body, ("question",))
    question = check_text(body.get("question"), "question", MAX_QUESTION)
    if not cfg.ask_limiter.allow(ip):
        raise ApiError(429, "Too many questions. Please wait a minute and try again.")
    if not cfg.ask_slots.acquire(blocking=False):
        raise ApiError(503, "The question service is busy. Please try again in a moment.")
    try:
        ask_fn = cfg.ask_fn or default_ask
        try:
            result = run_with_timeout(lambda: ask_fn(question), timeout)
        except TimeoutError:
            raise ApiError(504, f"The answer took longer than {timeout} seconds.") from None
        except Exception as exc:
            if type(exc).__name__ == "MissingApiKeyError":
                raise ApiError(503, "The question service is not set up on this server (API key missing).") from None
            log.error("ask failed: %s", type(exc).__name__)
            raise ApiError(502, "The question service failed. Please try again later.") from None
    finally:
        cfg.ask_slots.release()
    return shape_answer(result)


# ---------------------------------------------------------------- review decision (human gate)

def events_path(cfg):
    return cfg.reports_dir / "review-events.jsonl"


def read_events(cfg):
    events = []
    try:
        lines = events_path(cfg).read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # a damaged line is skipped, never repaired
    return events[-HISTORY_MAX:]


def api_decision_get(cfg, ip, body, query):
    return {"events": read_events(cfg)}


def api_decision_post(cfg, ip, body, query):
    body = only_fields(body, ("reviewer", "decision", "comment", "report_id"))
    reviewer = check_text(body.get("reviewer"), "reviewer", MAX_NAME)
    decision = body.get("decision")
    if decision not in DECISIONS:
        raise ApiError(400, "'decision' must be approve, reject or needs_changes.")
    comment = check_text(body.get("comment", ""), "comment", MAX_COMMENT, required=False)
    report_id = body.get("report_id")
    if report_id is None:
        path = newest(cfg.reports_dir, "RPT-*.json")
        report_id = path.stem if path else None
    elif not isinstance(report_id, str) or not REPORT_ID_RE.match(report_id):
        raise ApiError(400, "'report_id' is not a valid report id.")
    event = {"timestamp": now_iso(), "report_id": report_id, "reviewer": reviewer, "decision": decision,
             "comment": comment}
    with cfg.events_lock:
        cfg.reports_dir.mkdir(parents=True, exist_ok=True)
        with open(events_path(cfg), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"event": event}


# ---------------------------------------------------------------- seal

class SealUnavailable(Exception):
    pass


def load_seal_common(cfg):
    path = cfg.root / "seal" / "seal_common.py"
    spec = importlib.util.spec_from_file_location("seal_common_ui", path)
    if not path.exists() or spec is None:
        raise SealUnavailable("the seal code is not part of this installation")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seal_call(cfg, method, path, token_name, body=None, timeout=SEAL_TIMEOUT):
    url = (cfg.env.get("SEAL_URL") or "").rstrip("/")
    token = cfg.env.get(token_name) or ""
    if not url or not token or not url.startswith(("http://", "https://")):
        raise SealUnavailable("the seal is not configured on this server")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except ValueError:
            payload = {}
        if exc.code in (409, 503) and payload.get("result"):  # ledger damaged: a real, reportable answer
            return payload
        raise SealUnavailable(f"the seal answered with an error ({exc.code})") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise SealUnavailable("the seal cannot be reached") from None


def seal_error(exc):
    return ApiError(503, f"Seal unavailable: {exc}.")


def api_seal_runs(cfg, ip, body, query):
    try:
        return seal_call(cfg, "GET", "/runs", "SEAL_ADMIN_TOKEN")
    except SealUnavailable as exc:
        raise seal_error(exc) from None


def alter_one_status(report):
    """Dishonest vendor: copy of the report with one status changed. Returns (copy, what changed)."""
    forged = copy.deepcopy(report)
    findings = forged.get("findings") if isinstance(forged, dict) else None
    if not isinstance(findings, list) or not findings:
        raise ApiError(409, "The latest report has no findings to alter for the demo.")
    for f in findings:
        if isinstance(f, dict) and f.get("status") in NEEDS_FAILURE:
            old, f["status"] = f["status"], "PASS"
            return forged, {"finding": f.get("id"), "from": old, "to": "PASS"}
    for f in findings:
        if isinstance(f, dict) and f.get("status") == "PASS":
            f["status"] = "MISMATCH"
            return forged, {"finding": f.get("id"), "from": "PASS", "to": "MISMATCH"}
    raise ApiError(409, "The latest report has no status that can be altered for the demo.")


def api_seal_demo(cfg, ip, body, query):
    if not cfg.demo_limiter.allow(ip):
        raise ApiError(429, "The demo was started too often. Please wait a minute.")
    report = latest_report(cfg)["data"]  # 404 with a plain message if no review has run yet
    with cfg.demo_lock:
        try:
            common = load_seal_common(cfg)
            steps = []
            run = seal_call(cfg, "POST", "/runs/start", "SEAL_VENDOR_TOKEN")
            steps.append({"step": 1, "title": "The vendor asks ITSG for a run ID before the review",
                          "result": "RUN STARTED", "run_id": run["run_id"]})
            receipt = seal_call(cfg, "POST", f"/runs/{run['run_id']}/submit", "SEAL_VENDOR_TOKEN",
                                {"report_sha256": common.report_hash(report)})
            steps.append({"step": 2, "title": "The vendor submits the fingerprint (hash) of the finished report",
                          "result": "RECEIPT ISSUED", "run_id": run["run_id"], "seq": receipt.get("seq")})
            ok = seal_call(cfg, "POST", "/verify", "SEAL_ADMIN_TOKEN", {"report": report, "receipt": receipt})
            steps.append({"step": 3, "title": "ITSG checks the report it received against the receipt",
                          "result": ok.get("result"), "detail": ok.get("reason"), "run_id": run["run_id"]})
            forged, change = alter_one_status(report)
            bad = seal_call(cfg, "POST", "/verify", "SEAL_ADMIN_TOKEN", {"report": forged, "receipt": receipt})
            steps.append({"step": 4, "title": "A dishonest vendor changes one result and sends the edited report",
                          "result": bad.get("result"), "detail": bad.get("reason"), "run_id": run["run_id"],
                          "change": change})
            hidden = seal_call(cfg, "POST", "/runs/start", "SEAL_VENDOR_TOKEN")
            steps.append({"step": 5, "title": "The vendor starts a second run and never submits it",
                          "result": "NEVER SUBMITTED", "run_id": hidden["run_id"]})
            runs = seal_call(cfg, "GET", "/runs", "SEAL_ADMIN_TOKEN")
        except SealUnavailable as exc:
            raise seal_error(exc) from None
        except (KeyError, TypeError):
            raise ApiError(502, "The seal gave an answer this page does not understand.") from None
    return {"steps": steps, "runs": runs, "report_id": report.get("report", {}).get("id")}


# ---------------------------------------------------------------- privacy (T10-007)

MAX_PREVIEW = 5000
RETENTION_DEFAULT_DAYS = 7
RETENTION_PATTERNS = ("RPT-*.json", "harness-*.json")   # never review-events.jsonl, leaktest-latest.json or the seal ledger
LEAKTEST_TIMEOUT = 120
LEAKTEST_FILE = "leaktest-latest.json"


def privacy_gate(cfg):
    try:
        return schleuse.Schleuse(cfg.env.get("PRIVACY_KEY") or None)
    except schleuse.PrivacyConfigError:
        raise ApiError(503, "The privacy key on this server is invalid (PRIVACY_KEY must have at least 16 characters).") from None


def api_privacy_preview(cfg, ip, body, query):
    """Show what would leave the system. The original text is never stored or logged; it is not echoed back."""
    body = only_fields(body, ("text",))
    text = check_text(body.get("text"), "text", MAX_PREVIEW)
    if not cfg.privacy_limiter.allow(ip):
        raise ApiError(429, "Too many previews. Please wait a minute and try again.")
    gate = privacy_gate(cfg)
    clean, summary = gate.pseudonymize(text)
    left = gate.check_clean(clean)
    return {"clean_text": None if left else clean,   # a text with leftovers is not shown: it still holds personal data
            "summary": {"categories": summary["categories"], "total": summary["total"]},
            "blocked": bool(left), "blocked_categories": sorted({hit.category for hit in left}),
            "policy_version": schleuse.POLICY_VERSION, "key_source": gate.key_source}


def retention_days(env):
    try:
        days = int(env.get("RETENTION_DAYS") or RETENTION_DEFAULT_DAYS)
    except (TypeError, ValueError):
        return RETENTION_DEFAULT_DAYS
    return days if days >= 1 else RETENTION_DEFAULT_DAYS


def purge_old_reports(reports_dir, days, now=None):
    """Delete review reports and harness results older than `days`. Returns the deleted file names.

    Only RPT-*.json and harness-*.json in the reports folder are touched. The seal ledger lives elsewhere
    (it holds only hashes), and the decision log and the leak-test result are not matched.
    """
    cutoff = (time.time() if now is None else now) - days * 86400
    deleted = []
    for pattern in RETENTION_PATTERNS:
        for path in Path(reports_dir).glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted.append(path.name)
            except OSError:
                log.error("retention: could not delete one file")
    if deleted:
        log.info("retention: deleted %d old report file(s) (older than %d days)", len(deleted), days)
    return deleted


def start_retention(cfg, interval=86400):
    """Purge now and then once a day, in a daemon thread."""
    def loop():
        while True:
            try:
                purge_old_reports(cfg.reports_dir, retention_days(cfg.env))
            except Exception as exc:   # a failed purge must not stop the server
                log.error("retention failed: %s", type(exc).__name__)
            time.sleep(interval)
    thread = threading.Thread(target=loop, name="retention", daemon=True)
    thread.start()
    return thread


def api_privacy_flows(cfg, ip, body, query):
    """Data-flow map built from the policy dict (privacy/schleuse.py) and this server's configuration."""
    env = cfg.env
    policy = schleuse.POLICY
    try:
        _key, key_state = schleuse.get_key(env.get("PRIVACY_KEY") or None)
    except schleuse.PrivacyConfigError:
        key_state = "invalid"
    langfuse_on = bool(env.get("LANGFUSE_PUBLIC_KEY") and env.get("LANGFUSE_SECRET_KEY"))

    def row(dest, label, sends, protection, location, light, note):
        return {"id": dest, "destination": label, "mode": policy.get(dest, {}).get("mode"), "sends": sends,
                "protection": protection, "location": location, "light": light, "note": note}

    notes = {"invalid": "PRIVACY_KEY is invalid: questions are BLOCKED.",
             "env": "Fixed privacy key from the server environment.",
             "ephemeral": "No PRIVACY_KEY set: a random key per process is used. Tokens stay consistent inside one question."}
    flows = [
        row("hessian_ai", "AI model (hessian.AI)", "Your question with personal data replaced by tokens, plus public rulebook passages",
            "Pseudonymized, then checked again; anything left blocks the call",
            "hessian.AI, Germany, self-hosted open-weight models (as stated by the team, not verified by this page)",
            "red" if key_state == "invalid" else ("yellow" if key_state == "ephemeral" else "green"), notes.get("ephemeral" if key_state == "ephemeral" else key_state if key_state == "invalid" else "env", "")),
        row("langfuse", "Langfuse (tracing)", "Only listed fields (status, rule, source, expected/actual), pseudonymized",
            "Minimized + pseudonymized + checked; a trace may be public only if every payload was clean",
            "External service" + (f" ({env.get('LANGFUSE_HOST')})" if env.get("LANGFUSE_HOST") else "") + ", used only if keys are set",
            "yellow" if langfuse_on else "green",
            "Keys are set on this server: data leaves to an external service (guarded)." if langfuse_on
            else "No Langfuse keys on this server: nothing is sent."),
        row("seal", "ITSG seal", "Only a hash of the finished report and run IDs", "Hash only (no report text)",
            "Private Docker network, the seal container", "green", "The seal never receives report content."),
        row("logs", "Server logs", "Request line without query string, error types, privacy counts",
            "No personal data (log filter on the ask and UI loggers)", "Container log on the team server", "green",
            "The servers do not log user text. A filter scrubs what is logged anyway; free-text names without a cue word could slip through it."),
        row("reports", "Reports folder", "Review reports and harness results (synthetic data)",
            f"Deleted after {retention_days(env)} days (RETENTION_DAYS); the seal ledger is not touched",
            "Docker volume on the team server", "green",
            "Reviewer names typed into the decision log (review-events.jsonl) are not purged automatically."),
    ]
    return {"policy_version": schleuse.POLICY_VERSION, "retention_days": retention_days(env), "flows": flows,
            "light_meaning": {"green": "protection active and enforced in code (or nothing is sent)",
                              "yellow": "protected, but data leaves to an external place or the setting is weaker than intended",
                              "red": "protection broken: calls are blocked until fixed"}}


def api_privacy_leaktest(cfg, ip, body, query):
    """Latest leak-test result (reports/leaktest-latest.json). Runs privacy/leak_test.py once if there is none."""
    path = cfg.reports_dir / LEAKTEST_FILE
    source = "stored in the reports folder"
    if not path.exists():
        if not cfg.leak_lock.acquire(blocking=False):
            raise ApiError(503, "The leak test is running right now. Please try again in a minute.")
        try:
            if not path.exists():
                cfg.reports_dir.mkdir(exist_ok=True)
                try:
                    subprocess.run([sys.executable, "privacy/leak_test.py", "--json", str(path)], cwd=cfg.root,
                                   capture_output=True, timeout=LEAKTEST_TIMEOUT, env=child_env(), shell=False)
                except subprocess.TimeoutExpired:
                    raise ApiError(504, f"The leak test took longer than {LEAKTEST_TIMEOUT} seconds and was stopped.") from None
                except OSError:
                    raise ApiError(500, "The leak test could not be started.") from None
                source = "run just now"
        finally:
            cfg.leak_lock.release()
    if not path.exists():
        built = cfg.root / "privacy" / "leaktest-build.json"   # copy made when the Docker image was built
        if not built.exists():
            raise ApiError(404, "There is no leak-test result yet.")
        path, source = built, "made when the image was built"
    return {"source": source, "result": read_json_file(path)}


# ---------------------------------------------------------------- health

def part_checker(cfg):
    path = cfg.root / "checker" / "checks.py"
    if not path.exists():
        return {"status": "unavailable", "reason": "checker/checks.py not found"}
    return {"status": "available", "version": f"checks.py {file_hash(path)}"}


def part_retrieval(cfg):
    chunks = cfg.root / "chunks"
    if not chunks.is_dir():
        return {"status": "unavailable", "reason": "chunks/ folder not found"}
    try:
        from retrieval import ask as ask_mod
    except ImportError as exc:
        return {"status": "unavailable", "reason": f"missing Python package ({exc.name})"}
    configured = bool(cfg.env.get("HESSIAN_API_KEY"))
    return {"status": "available" if configured or cfg.ask_fn else "unavailable",
            "version": ask_mod.PROMPT_VERSION, "model": ask_mod.MODEL, "api_key_configured": configured,
            **({} if configured or cfg.ask_fn else {"reason": "HESSIAN_API_KEY is not set on the server"})}


def part_seal(cfg):
    if not (cfg.env.get("SEAL_URL") and cfg.env.get("SEAL_VENDOR_TOKEN") and cfg.env.get("SEAL_ADMIN_TOKEN")):
        return {"status": "unavailable", "reason": "SEAL_URL or a seal token is not set on the server"}
    try:
        runs = seal_call(cfg, "GET", "/runs", "SEAL_ADMIN_TOKEN", timeout=3)
    except SealUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}
    if "runs" not in runs:
        return {"status": "unavailable", "reason": f"the seal reports {runs.get('result', 'a problem')}"}
    return {"status": "available", "version": "no version endpoint", "runs": runs.get("total")}


def part_harness(cfg):
    cases = load_cases(cfg)
    if not cases:
        return {"status": "unavailable", "reason": "data/testcases.json not found"}
    latest = latest_harness(cfg)
    return {"status": "available", "cases": len(cases), "latest_run": latest["file"] if latest else None}


def api_health(cfg, ip, body, query):
    return {"ui_version": UI_VERSION, "time": now_iso(),
            "parts": {"checker": part_checker(cfg), "retrieval": part_retrieval(cfg),
                      "seal": part_seal(cfg), "harness": part_harness(cfg)}}


# ---------------------------------------------------------------- HTTP layer

ROUTES = {
    ("GET", "/api/health"): api_health,
    ("GET", "/api/review/latest"): api_review_latest,
    ("POST", "/api/review/run"): api_review_run,
    ("GET", "/api/testcases"): api_testcases,
    ("GET", "/api/harness/latest"): api_harness_latest,
    ("POST", "/api/harness/run"): api_harness_run,
    ("POST", "/api/ask"): api_ask,
    ("POST", "/api/privacy/preview"): api_privacy_preview,
    ("GET", "/api/privacy/flows"): api_privacy_flows,
    ("GET", "/api/privacy/leaktest"): api_privacy_leaktest,
    ("POST", "/api/seal/demo"): api_seal_demo,
    ("GET", "/api/seal/runs"): api_seal_runs,
    ("POST", "/api/review/decision"): api_decision_post,
    ("GET", "/api/review/decision"): api_decision_get,
}
CASE_PATH = re.compile(r"^/api/testcases/([^/]+)$")


def static_file(cfg, url_path):
    """Map a URL path to a file under ui/ or figures/ — or None. No traversal, no dot files, fixed extensions."""
    rel = unquote(url_path).lstrip("/") or "index.html"
    if "\x00" in rel or "\\" in rel or any(p in ("", ".", "..") or p.startswith(".") for p in rel.split("/")):
        return None
    base = cfg.root / rel.split("/")[0] if rel.split("/")[0] in STATIC_ROOTS else cfg.ui_dir
    target = (cfg.root / rel) if base != cfg.ui_dir else (cfg.ui_dir / rel)
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.suffix.lower() not in STATIC_TYPES:
        return None
    return resolved


class Handler(BaseHTTPRequestHandler):
    server_version = "Team10UI"
    sys_version = ""
    timeout = 15

    def log_message(self, fmt, *args):  # request line without the query string; never headers or bodies
        log.info("%s %s", self.command, self.path.split("?")[0][:100])

    @property
    def cfg(self):
        return self.server.cfg

    def _headers(self, extra=None):
        for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(k, v)

    def _json(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers({"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(data))})
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _read_body(self):
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            return None
        if not raw_len.isdigit():
            raise ApiError(400, "Invalid Content-Length.")
        length = int(raw_len)
        if length > MAX_BODY:
            self.close_connection = True
            try:  # drop (never parse) the oversized body so the client receives our answer, not a reset
                self.connection.settimeout(1)
                left = min(length, 4 * MAX_BODY)
                while left > 0:
                    got = self.rfile.read(min(left, 65536))
                    if not got:
                        break
                    left -= len(got)
            except OSError:
                pass
            raise ApiError(413, f"The request is larger than {MAX_BODY // 1024} KB.")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ApiError(415, "The request must be sent as JSON.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            raise ApiError(400, "The request is not valid JSON.") from None

    def _check_origin(self):
        """POST needs our own header (forces a CORS preflight, which we never grant) and a matching Origin."""
        if self.headers.get("X-Requested-With") != "team10-ui":
            raise ApiError(403, "This request must come from the Team 10 page.")
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != (self.headers.get("Host") or ""):
            raise ApiError(403, "This request came from another site.")

    def _dispatch(self):
        parts = urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        method = "GET" if self.command == "HEAD" else self.command
        try:
            if path.startswith("/api/"):
                handler, kwargs = ROUTES.get((method, path)), {}
                m = CASE_PATH.match(path)
                if handler is None and method == "GET" and m:
                    handler, kwargs = api_testcase_detail, {"case_id": m.group(1)}
                if handler is None:
                    known = any(p == path for (_, p) in ROUTES) or m
                    raise ApiError(405 if known else 404, "Method not allowed." if known else "Unknown API path.")
                body = None
                if method == "POST":
                    self._check_origin()
                    body = self._read_body()
                    if body is None and handler in (api_ask, api_decision_post, api_privacy_preview):
                        raise ApiError(400, "The request body is missing.")
                return self._json(200, handler(self.cfg, self.client_address[0], body, query, **kwargs))
            if method != "GET":
                raise ApiError(405, "Method not allowed.")
            target = static_file(self.cfg, path)
            if target is None:
                raise ApiError(404, "Not found.")
            data = target.read_bytes()
            self.send_response(200)
            self._headers({"Content-Type": STATIC_TYPES[target.suffix.lower()], "Content-Length": str(len(data))})
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except ApiError as exc:
            if exc.status in (413, 400) and self.command == "POST":
                self.close_connection = True
            self._error(exc.status, exc.message)
        except (BrokenPipeError, ConnectionError, TimeoutError):
            pass
        except Exception as exc:  # never a stack trace to the browser
            log.error("internal error: %s", type(exc).__name__)
            try:
                self._error(500, "Something went wrong on the server.")
            except Exception:
                pass

    do_GET = do_HEAD = do_POST = _dispatch

    def _not_allowed(self):
        self.close_connection = True
        self._error(405, "Method not allowed.")

    do_PUT = do_DELETE = do_PATCH = _not_allowed


def make_server(host="127.0.0.1", port=0, cfg=None):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.cfg = cfg or Config()
    return httpd


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_env(ROOT / ".env")
    host = os.environ.get("UI_HOST") or "0.0.0.0"
    try:
        port = int(os.environ.get("UI_PORT") or 8000)
    except ValueError:
        print("UI_PORT must be a number.", file=sys.stderr)
        return 2
    httpd = make_server(host, port)
    start_retention(httpd.cfg)   # delete old reports now and once a day (RETENTION_DAYS, default 7)
    print(f"Team 10 demo on http://{'localhost' if host == '0.0.0.0' else host}:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
