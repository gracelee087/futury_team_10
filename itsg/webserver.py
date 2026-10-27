"""SÜSIE local web bridge (T10-031) — serves the static frontend and a small
JSON API over the ``itsg`` store (T10-018 demo slice).

Human directive 2026-10-26: "full wiring of the backend". This module adds NO
dependency (stdlib ``http.server``) and holds no business logic of its own:
chat turns are delegated to ``itsg.chat`` (which enforces cite-or-abstain and
the action whitelist in code), action execution to ``itsg.actions`` (fail-
closed confirmation tokens). Fail-closed honesty is preserved end to end —
the frontend falls back to clearly-labelled synthetic data when this
server is not reachable.

Endpoints (127.0.0.1 only by default):
  GET  /            → frontend/index.html (static files below --frontend)
  GET  /api/health  → {"ok": true, "store": <path>, "events": <n>}
  GET|POST /api/report/pdf → the formal report document (application/pdf; T10-036)
                      rendered by itsg.report_pdf from the store's report artifact
                      (deterministic content; POST body {"live": true} additionally
                      drafts the marked AI summary via the gateway GLM model —
                      on any gateway failure the PDF is returned without the
                      summary and with an honest note; the failure is recorded
                      as an agent_run in the store, never fabricated)
  GET  /api/state   → typed UI payload assembled from the store records
                      (now plus "stories" from data/story_cases.json,
                      "reviews" from reports/RPT-*.json and "harness" from
                      the newest reports/harness-*.json — all fail-soft)
  GET  /api/chat/history?session_id=… → {"ok": true, "turns": [...]} the
                      session's chat_turn records ordered by id (missing or
                      blank session_id → 400)
  POST /api/run     → body {"live": bool} re-runs itsg.demo into the store
                      (offline by default; live needs the secrets store and
                      performs real gateway calls — the demo driver itself
                      stays fail-closed: missing credentials become recorded
                      error runs, never fabricated output)
  POST /api/review/run → body {} (or {"scope": ...}, ignored) runs the repo's
                      own deterministic offline run_review.py as a subprocess
                      (lock-serialized, 120 s timeout) and returns the fresh
                      RPT-* report as a "review" entry; failure → {"ok": false}
  POST /api/chat    → body {"session_id", "message", "reviewer": ""} runs one
                      SÜSIE chat turn (app-state context, corpus hits via the
                      --index FTS file, session history) and persists one
                      chat_turn record per side (user + susie) into the
                      append-only event log. Gateway failures stay HTTP 200
                      with "degraded": true — the degraded reply is data,
                      never an error, and is audited like any other turn.
  POST /api/action  → body {"session_id", "action_id", "params",
                      "confirm_token", "reviewer"} executes a whitelisted
                      action via itsg.actions.execute; PermissionError → 403,
                      ValueError (unknown action) → 400.

Security: bind address defaults to 127.0.0.1; static paths are resolved
inside the frontend root (traversal refused); the API speaks JSON only and
serves no credentials — the LLM token never leaves the server side (the
``agent_run`` audit envelope carries model/prompt metadata only).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import actions, chat, langfuse_link, retrieval
from .store import Store
from .timeutil import utc_now

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND = ROOT / "frontend"
DEFAULT_STORE = ROOT / "data" / "demo"
DEFAULT_INDEX = ROOT / "data" / "index" / "fts.sqlite"

# Test seam: when None, ``chat.turn`` uses its default real gateway (token via
# itsg.llm.resolve_token); tests inject a fake here and clear it in tearDown.
CHAT_GATEWAY = None

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

_run_lock = threading.Lock()
_review_lock = threading.Lock()
_chat_lock = threading.Lock()  # serializes history read + CHAT-<n> allocation

_CHAT_ID = re.compile(r"^CHAT-(\d+)$")

REVIEW_FINDINGS_CAP = 50
REVIEW_HISTORY_LIMIT = 10
REVIEW_RUN_TIMEOUT_S = 120

# Regulations browser (T10-045): the indexed chunk corpus under chunks/ plus the
# original PDFs. Chunk paths and PDF lookups are containment-checked against
# these fixed roots; no request input ever escapes them.
CHUNKS_DIR = ROOT / "chunks"
CHUNK_INDEX_PATH = CHUNKS_DIR / "chunks.jsonl"
PDF_BASES = (ROOT / "ITSG Files",)
REGULATIONS_QUERY_CAP = 200
REGULATIONS_LIMIT_CAP = 50

_reg_chunk_cache: list[dict] | None = None
_pdf_file_cache: dict[str, Path | None] | None = None


def _reg_chunks() -> list[dict]:
    """The chunk index (cached): one flat list of chunk metadata + text."""
    global _reg_chunk_cache
    if _reg_chunk_cache is None:
        chunks: list[dict] = []
        try:
            with open(CHUNK_INDEX_PATH, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        if isinstance(entry, dict):
                            chunks.append(entry)
        except Exception:
            pass
        _reg_chunk_cache = chunks
    return _reg_chunk_cache


def _pdf_index() -> dict[str, Path | None]:
    """Allowlist of original PDFs: source filename → resolved path (cached)."""
    global _pdf_file_cache
    if _pdf_file_cache is None:
        index: dict[str, Path | None] = {}
        for base in PDF_BASES:
            if base.is_dir():
                for candidate in base.rglob("*.pdf"):
                    index.setdefault(candidate.name, candidate.resolve())
        _pdf_file_cache = index
    return _pdf_file_cache


def regulations_overview() -> dict:
    """Documents available in the indexed corpus, for the UI browser."""
    chunks = _reg_chunks()
    if not chunks:
        return {"ok": False, "error": "chunk index empty or unreadable", "docs": []}
    docs: dict[str, dict] = {}
    for entry in chunks:
        doc_id = str(entry.get("doc") or "?")
        doc = docs.setdefault(doc_id, {
            "doc": doc_id,
            "title": entry.get("doc_title") or doc_id,
            "version": str(entry.get("version") or ""),
            "source_file": entry.get("source_file") or "",
            "chunks": 0,
        })
        doc["chunks"] += 1
    pdfs = _pdf_index()
    for doc in docs.values():
        doc["pdf_available"] = bool(doc["source_file"] and doc["source_file"] in pdfs)
    return {"ok": True, "total_chunks": len(chunks),
            "docs": sorted(docs.values(), key=lambda d: d["doc"])}


def regulations_search(q: str, doc: str = "", limit: int = 30) -> dict:
    """Keyword search over the chunk corpus (title/section hits rank first).

    ``q="*"`` is the browse mode: every chunk of the selected document passes
    unscored, so the UI can list a document's sections in order.
    """
    q = (q or "").strip()[:REGULATIONS_QUERY_CAP]
    if not q:
        return {"ok": False, "error": "query required", "results": []}
    limit = max(1, min(int(limit or 30), REGULATIONS_LIMIT_CAP if q != "*" else 500))
    browse = q == "*"
    terms = [] if browse else [t for t in q.lower().split() if len(t) >= 2]
    if not terms and not browse:
        return {"ok": False, "error": "query too short", "results": []}
    results = []
    for entry in _reg_chunks():
        if doc and str(entry.get("doc") or "") != doc:
            continue
        title = str(entry.get("title") or "")
        section = str(entry.get("section") or "")
        text = str(entry.get("text") or "")
        hay = f"{title} {section} {text}".lower()
        score = 0
        for term in terms:
            if term in title.lower():
                score += 8
            if term == section.lower() or section.lower().startswith(term):
                score += 20
            score += min(hay.count(term), 10)
        if score or browse:
            at = hay.find(terms[0]) if terms else -1
            snippet_at = max(0, (at if at >= 0 else 0) - 60)
            snippet = text[max(0, snippet_at):snippet_at + 260].replace("\n", " ").strip()
            results.append({
                "path": entry.get("path"), "doc": entry.get("doc"),
                "doc_title": entry.get("doc_title"), "section": section,
                "title": title, "pages": f"{entry.get('page_start')}–{entry.get('page_end')}"
                if entry.get("page_start") else "",
                "score": score, "snippet": snippet,
            })
    # browse mode: document order (numeric-aware path sort); search: score first
    if browse:
        results.sort(key=lambda r: _natkey(str(r["path"] or "")))
    else:
        results.sort(key=lambda r: (-r["score"], _natkey(str(r["path"] or ""))))
    return {"ok": True, "query": q, "count": len(results),
            "results": results[:limit]}


def _natkey(path: str) -> tuple:
    """Numeric-aware sort key so §2.10 sorts after §2.9."""
    import re as _re
    return tuple(int(p) if p.isdigit() else p for p in _re.split(r"(\d+)", path))


def regulation_chunk(path: str) -> dict:
    """One chunk's markdown text; the path is containment-checked under chunks/."""
    rel = str(path or "").strip().lstrip("/")
    if not rel or ".." in rel or "\x00" in rel or not rel.endswith(".md"):
        return {"ok": False, "error": "invalid chunk path"}
    target = (CHUNKS_DIR / rel).resolve()
    try:
        target.relative_to(CHUNKS_DIR.resolve())
    except ValueError:
        return {"ok": False, "error": "invalid chunk path"}
    if not target.is_file():
        return {"ok": False, "error": "chunk not found"}
    meta = next((c for c in _reg_chunks() if c.get("path") == rel), {})
    try:
        text = target.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"chunk unreadable: {exc}"}
    return {"ok": True, "path": rel, "text": text,
            "doc": meta.get("doc"), "doc_title": meta.get("doc_title"),
            "version": meta.get("version"), "section": meta.get("section"),
            "title": meta.get("title"),
            "pages": f"{meta.get('page_start')}–{meta.get('page_end')}"
            if meta.get("page_start") else "",
            "source_file": meta.get("source_file")}


def regulation_pdf(doc: str) -> Path | None:
    """The original PDF for a corpus document, from the allowlist only."""
    source_file = next((str(d.get("source_file") or "") for d in regulations_overview()["docs"]
                        if d.get("doc") == str(doc or "")), "")
    if not source_file:
        return None
    pdf = _pdf_index().get(source_file)
    if pdf and pdf.is_file() and pdf.suffix.lower() == ".pdf":
        return pdf
    return None


def load_story_cases(path: Path | None = None) -> dict:
    """Summarise data/story_cases.json for the UI; fail-soft — a missing or
    unreadable file yields {"ok": false, "error": ..., "cases": []} and never
    breaks the whole /api/state payload."""
    path = Path(path) if path else Path(SUSIEHandler.story_cases_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"story cases unreadable: {exc}", "cases": []}
    if not isinstance(raw, list):
        return {"ok": False, "error": "story cases file must be a JSON array", "cases": []}
    by_story: dict[str, int] = {}
    categories: list[dict] = []
    seen: dict[tuple, dict] = {}
    cases = []
    for case in raw:
        if not isinstance(case, dict):
            continue
        story = case.get("story")
        by_story[str(story)] = by_story.get(str(story), 0) + 1
        key = (story, case.get("category"))
        if key not in seen:
            seen[key] = {"story": story, "category": case.get("category"),
                         "count": 0, "must_flag": case.get("must_flag")}
            categories.append(seen[key])
        seen[key]["count"] += 1
        scenario = case.get("scenario") or {}
        if not isinstance(scenario, dict):
            scenario = {}
        prior = scenario.get("prior") or []
        if not isinstance(prior, list):
            prior = []
        cases.append({
            "id": case.get("id"),
            "story": story,
            "category": case.get("category"),
            "must_flag": case.get("must_flag"),
            "scenario_summary": {
                "current": {
                    "start": scenario.get("current_start"),
                    "end": scenario.get("current_end"),
                    "cert": scenario.get("current_cert"),
                    "insurance": scenario.get("insurance"),
                    "reason": scenario.get("current_reason"),
                },
                "prior_count": len(prior),
                "prior_certified": sum(1 for p in prior
                                       if isinstance(p, dict) and p.get("cert", True)),
                "today": scenario.get("today"),
            },
            "expected": case.get("expected"),
            "observed_kind": case.get("observed_kind"),
        })
    return {"ok": True, "count": len(cases), "by_story": by_story,
            "categories": categories, "cases": cases}


def _review_entry(path: Path, report: dict) -> dict:
    """Project one RPT-*.json report onto the API's flat review shape."""
    report = report if isinstance(report, dict) else {}
    meta = report.get("report") or {}
    robustness = report.get("robustness") or {}
    return {
        "id": meta.get("id"),
        "file": Path(path).name,
        "created_at": meta.get("created_at"),
        "overall_status": meta.get("overall_status"),
        "counts": meta.get("counts", {}),
        "test_case_id": (report.get("test_case") or {}).get("id"),
        "findings": (report.get("findings") or [])[:REVIEW_FINDINGS_CAP],
        "robustness": {"result": robustness.get("result"),
                       "reason": robustness.get("reason")},
        "review": report.get("review"),
        "trace_url": report.get("trace_url"),
    }


def load_reviews(limit: int = REVIEW_HISTORY_LIMIT) -> list[dict]:
    """Newest-first review history from reports/RPT-*.json (filenames embed a
    timestamp); missing dir → []. Unreadable single files are skipped."""
    try:
        files = sorted(Path(SUSIEHandler.reports_path).glob("RPT-*.json"), reverse=True)
    except Exception:
        return []
    reviews = []
    for file in files:
        if not file.is_file():
            continue
        try:
            report = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        reviews.append(_review_entry(file, report))
        if len(reviews) >= limit:
            break
    return reviews


def load_harness() -> dict | None:
    """The newest reports/harness-*.json projected for the UI; missing → None."""
    try:
        files = [p for p in Path(SUSIEHandler.reports_path).glob("harness-*.json") if p.is_file()]
    except Exception:
        return None
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except Exception:
        return None
    summary = data.get("summary") or {}
    return {
        "run_id": summary.get("run_id"),
        "file": newest.name,
        "created_at": datetime.fromtimestamp(newest.stat().st_mtime).isoformat(timespec="seconds"),
        "cases": summary.get("cases"),
        "correct": summary.get("correct"),
        "false_alarms": summary.get("false_alarms"),
        "clean_cases": summary.get("clean_cases"),
        "detected": summary.get("detected"),
        "must_flag_cases": summary.get("must_flag_cases"),
        "by_category": summary.get("by_category", {}),
        "results": [{"id": r.get("id"), "group": r.get("group"),
                     "category": r.get("category"), "must_flag": r.get("must_flag"),
                     "flagged": r.get("flagged"), "ok": r.get("ok"),
                     "outcome": r.get("outcome")}
                    for r in data.get("results") or [] if isinstance(r, dict)],
    }


def run_review_once() -> dict:
    """Run the repo's own deterministic offline run_review.py (serialized,
    bounded) and return the fresh report as a review entry."""
    script = Path(SUSIEHandler.review_script_path)
    reports_dir = Path(SUSIEHandler.reports_path)
    started = time.time()
    with _review_lock:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=REVIEW_RUN_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(f"run_review.py failed (rc={proc.returncode}): "
                           f"{(proc.stderr or proc.stdout or '')[-500:]}")
    fresh = [p for p in reports_dir.glob("RPT-*.json")
             if p.is_file() and p.stat().st_mtime > started]
    if not fresh:
        raise RuntimeError("run_review.py produced no new RPT-*.json report")
    newest = max(fresh, key=lambda p: p.stat().st_mtime)
    return _review_entry(newest, json.loads(newest.read_text(encoding="utf-8")))


def load_seal(store_root: Path) -> dict | None:
    """Seal receipt info for the report artifact, if a --seal demo run left one."""
    receipt_path = store_root / "report.artifact.json.receipt.json"
    if not receipt_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception:
        return {"present": True, "run_id": "", "seq": None}
    if not isinstance(receipt, dict):
        return {"present": True, "run_id": "", "seq": None}
    return {"present": True, "run_id": str(receipt.get("run_id", "")),
            "seq": receipt.get("seq")}


def privacy_status() -> dict:
    """Honest Datenschutz-Schleuse status for the UI badge (T10-043).

    Reports configuration and wiring, never key material and never scan values:
    everything here is derivable from the imported module and the environment.
    """
    try:
        import privacy.schleuse as schleuse   # respects the sys.modules None sentinel (tests)
    except ImportError:
        return {"ok": False, "active": False,
                "reason": "privacy module not importable — external calls are refused (fail closed)"}
    destinations = {name: {"mode": cfg.get("mode", ""), "allowed": bool(cfg.get("allowed"))}
                    for name, cfg in sorted(schleuse.POLICY.items())}
    key_configured = bool(os.environ.get(schleuse.KEY_ENV))
    return {
        "ok": True,
        "active": True,
        "policy_version": schleuse.POLICY_VERSION,
        "key_configured": key_configured,
        # Without PRIVACY_KEY the airlock derives an ephemeral run key (privacy/schleuse.py
        # get_key): tokens are still stable within one run, none persist across restarts.
        "key_mode": "persistent (PRIVACY_KEY)" if key_configured else "ephemeral per run",
        "destinations": destinations,
        "wired": {
            "susie_chat_gateway": "pseudonymize + final gate, fail closed (itsg/chat.py)",
            "langfuse_tracing": "minimize + pseudonymize + check_clean (privacy/langfuse_guard.py)",
        },
        "categories": list(schleuse.CATEGORIES),
    }


def build_state(store_root: Path) -> dict:
    """Assemble the UI payload from the store; empty store → empty draft state."""
    store = Store(store_root)
    records = store._load_records()  # noqa: SLF001 — single-process bridge
    findings = records.get("finding", {})
    test_cases = records.get("test_case", {})
    executions = {e.get("test_case_id"): e for e in records.get("execution", {}).values()}
    cases = []
    for finding in findings.values():
        tc = test_cases.get(finding.get("links", [""])[0], {})
        execution = executions.get(tc.get("id"), {})
        expected = tc.get("expected") or {}
        observed = execution.get("observed")
        cases.append({
            "id": tc.get("id") or finding.get("id"),
            "criterion_id": tc.get("criterion_id", ""),
            "case_type": tc.get("case_type", "normal"),
            "status": finding.get("status", "NOT_EVALUATED"),
            "reason": finding.get("reason", ""),
            "expected": expected,
            "observed": observed,
            "expected_basis": tc.get("expected_basis", ""),
            "inputs": tc.get("inputs", {}),
            "evidence_ref": execution.get("evidence_ref", ""),
            "execution_id": execution.get("id", ""),
            "run_at": execution.get("run_at", ""),
            "software": {
                "vendor": execution.get("vendor", ""),
                "version": execution.get("software_version", ""),
            },
        })
    order = {"PASS": 0, "MISMATCH": 1, "NOT_EVALUATED": 2}
    cases.sort(key=lambda c: (order.get(c["status"], 3), c["id"] or ""))
    report = records.get("report", {})
    report_record = next(iter(report.values()), None)
    source = next(iter(records.get("source", {}).values()), None)
    template = next(iter(records.get("template", {}).values()), None)
    criteria = list(records.get("criterion", {}).values())
    requirements = list(records.get("requirement", {}).values())
    gates = list(records.get("gate", {}).values())
    state = {
        "ok": True,
        "backend": {
            "store": str(store_root),
            "events": len(store.events()),
            "gates": len(gates),
            "agent_runs": len(records.get("agent_run", {})),
        },
        "source": source,
        "template": template,
        "criteria": criteria,
        "requirements": requirements,
        "cases": cases,
        "report": {
            "id": report_record.get("id") if report_record else None,
            "conformance": (report_record or {}).get("conformance", []),
            "compliance_claim": (report_record or {}).get("compliance_claim", False),
            "template_warning": (template or {}).get("notes", ""),
        },
    }
    # Additive, fail-soft overlays: a missing story/harness/reports file must
    # never break the rest of /api/state.
    try:
        state["stories"] = load_story_cases()
    except Exception as exc:  # belt and braces — loader is already fail-soft
        state["stories"] = {"ok": False, "error": str(exc), "cases": []}
    try:
        state["reviews"] = load_reviews()
    except Exception:
        state["reviews"] = []
    try:
        state["harness"] = load_harness()
    except Exception:
        state["harness"] = None
    try:
        state["seal"] = load_seal(store_root)
    except Exception:
        state["seal"] = None
    return state


def run_demo_into(store_root: Path, live: bool, fresh: bool = False) -> dict:
    """Re-run the demo driver into the store (serialized; offline unless asked).

    ``fresh`` deletes the store first — that silently destroys a fed corpus
    (T10-045 footgun), so the API only wipes on the explicit opt-in flag.
    """
    # The website runs on Team 10's 30 cases only: (re)load data/eaz_cases.json and compare them.
    from . import eaz_import

    with _run_lock:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            eaz_import.run_import(Path(store_root), eaz_import.ROOT / "data" / "eaz_cases.json")
    return build_state(store_root)


_pdf_lock = threading.Lock()

# Live seal demo state (T10-042): the throwaway in-process receipt office is
# kept alive between the "seal" and "tamper-demo" calls so the TAMPERED
# verification runs against the SAME office and ledger as the receipt.
_seal_office: dict | None = None
_seal_demo_lock = threading.Lock()


def run_seal_action(store_root: Path, action: str) -> dict:
    """Live seal demo (owner directive: the seal USP must be visible on stage).

    ``seal``         — receipt for the report artifact from a throwaway
                       in-process ITSG receipt office (HMAC, hash-chained
                       ledger in the store); the receipt file lands next to
                       the artifact so /api/state surfaces it.
    ``verify``       — re-verify the stored artifact against the receipt.
    ``tamper-demo``  — flip one byte in a TEMP COPY and verify that against
                       the receipt → TAMPERED. The store original is never
                       modified; the demo is honest about that.

    Any failure raises; the endpoint maps it to a JSON error — a failed seal
    is evidence information, never fabricated success.
    """
    global _seal_office
    import tempfile

    from . import report_pdf

    seal_dir = ROOT / "seal"
    if not (seal_dir / "server.py").is_file():
        raise RuntimeError("seal service not present in this checkout")
    if str(seal_dir) not in sys.path:
        sys.path.insert(0, str(seal_dir))
    import secrets as _pysecrets
    import threading as _threading

    import client as seal_client
    import server as seal_server
    import verify as seal_verify

    artifact = report_pdf.find_artifact(store_root)
    state_file = store_root / "seal-current-run"

    def _start_office() -> dict:
        own_server = seal_server.make_server(
            {"SEAL_SECRET": _pysecrets.token_hex(32),
             "SEAL_VENDOR_TOKEN": _pysecrets.token_hex(16),
             "SEAL_ADMIN_TOKEN": _pysecrets.token_hex(16),
             "SEAL_LEDGER": str(store_root / "seal-ledger.jsonl")},
            "127.0.0.1", 0)
        _threading.Thread(target=own_server.serve_forever,
                          kwargs={"poll_interval": 0.05}, daemon=True).start()
        return {"url": f"http://127.0.0.1:{own_server.server_address[1]}",
                "vendor": own_server.app.vendor_token,
                "admin": own_server.app.admin_token}

    with _seal_demo_lock:
        if _seal_office is None:
            _seal_office = _start_office()

        if action == "seal":
          for _attempt in (1, 2):
            try:
                run = seal_client.start_run(_seal_office["url"], _seal_office["vendor"],
                                            state_file=state_file)
                res = seal_client.submit(artifact, run_id=run["run_id"], url=_seal_office["url"],
                                         token=_seal_office["vendor"], state_file=state_file)
                check = seal_verify.verify_files(artifact, res["receipt_file"],
                                                 url=_seal_office["url"], token=_seal_office["admin"])
                out = {"action": "seal", "result": check["result"], "reason": check.get("reason", ""),
                        "run_id": run["run_id"], "receipt_seq": res["receipt"].get("seq"),
                        "receipt_file": res["receipt_file"], "artifact": artifact.name}
                if _attempt == 2:
                    out["note"] = ("Das frühere Siegel-Konto stammte aus einem anderen Demo-Lauf "
                                   "(andere Schlüssel) und wurde archiviert — neuer Ledger, "
                                   "erste Quittung dieser Sitzung.")
                return out
            except Exception as exc:
                # Re-sealing the same artifact is a replay by design — the
                # honest answer is to verify the EXISTING receipt instead.
                if "already submitted" in str(exc).lower() or "replay" in str(exc).lower():
                    receipt_file = artifact.with_name(artifact.name + ".receipt.json")
                    if receipt_file.is_file():
                        check = seal_verify.verify_files(
                            artifact, receipt_file, url=_seal_office["url"],
                            token=_seal_office["admin"])
                        return {"action": "seal", "result": check["result"],
                                "reason": check.get("reason", ""), "already_sealed": True,
                                "note": "Dieser Bericht ist bereits versiegelt — die vorhandene "
                                        "Quittung wurde geprüft (erneutes Siegeln desselben "
                                        "Berichts wäre ein Replay und wird vom Dienst korrekt "
                                        "abgelehnt).",
                                "artifact": artifact.name}
                # A ledger from an earlier demo run (different HMAC keys) is
                # refused by the service — fail-closed is correct. Archive it
                # honestly and retry ONCE with a fresh office + ledger.
                if (_attempt == 1 and ("damaged" in str(exc).lower()
                                       or "invalid mac" in str(exc).lower())):
                    ledger = store_root / "seal-ledger.jsonl"
                    if ledger.is_file():
                        ledger.rename(store_root / f"seal-ledger-archived-{utc_now().replace(':', '')}.jsonl")
                    _seal_office = _start_office()
                    continue
                raise
        if action == "verify":
            receipt_file = artifact.with_name(artifact.name + ".receipt.json")
            if not receipt_file.is_file():
                raise RuntimeError("no receipt yet — seal the artifact first")
            check = seal_verify.verify_files(artifact, receipt_file,
                                             url=_seal_office["url"], token=_seal_office["admin"])
            return {"action": "verify", "result": check["result"], "reason": check.get("reason", "")}
        if action == "tamper-demo":
            receipt_file = artifact.with_name(artifact.name + ".receipt.json")
            if not receipt_file.is_file():
                raise RuntimeError("no receipt yet — seal the artifact first")
            with tempfile.TemporaryDirectory() as tmp:
                tampered = Path(tmp) / ("TAMPERED-" + artifact.name)
                data = bytearray(artifact.read_bytes())
                marker = data.find(b"20XX0101")
                if marker < 0:
                    marker = max(0, len(data) // 2)
                data[marker] = (data[marker] + 1) % 256  # flip exactly one byte
                tampered.write_bytes(bytes(data))
                check = seal_verify.verify_files(tampered, receipt_file,
                                                 url=_seal_office["url"], token=_seal_office["admin"])
            return {"action": "tamper-demo", "result": check["result"],
                    "reason": check.get("reason", ""),
                    "note": "an einer Kopie simuliert — das Original im Store bleibt unverändert"}
    raise ValueError(f"unknown seal action: {action!r}")


def build_report_pdf(store_root: Path, live: bool = False,
                     client_name: str | None = None, lang: str = "de") -> bytes:
    """Render the formal report PDF (T10-036) and return its bytes.

    Deterministic content, honest degradation: ``live`` only adds the marked
    AI summary; a gateway failure records an error agent_run in the store and
    the PDF is still returned — with an explicit note instead of a summary.
    """
    import tempfile

    from . import report_pdf

    artifact = report_pdf.find_artifact(store_root)
    summary = None
    summary_note = None
    if live:
        data = json.loads(artifact.read_text(encoding="utf-8"))
        with _pdf_lock:
            run = report_pdf.draft_summary_live(
                data, data.get("results") or [],
                task_id=f"REPORT-{data.get('report_id', 'UNKNOWN')}")
        if run.status == "candidate" and run.result.get("summary_de"):
            summary = run.result["summary_de"]
        else:
            summary_note = ("Keine KI-Zusammenfassung: Gateway/Anmeldedaten nicht verfügbar "
                            f"(Fehler protokolliert: {run.result.get('error', 'unbekannt')}).")
        run_dict = run.to_dict()
        Store(store_root).put("agent_run", {"id": run_dict["run_id"], **run_dict})
    with _pdf_lock:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "formal-report.pdf"
            report_pdf.generate_report_pdf(artifact, out, client_name=client_name,
                                           summary=summary, summary_note=summary_note, lang=lang)
            return out.read_bytes()


def _chat_number(record: dict) -> int:
    """Numeric suffix of a CHAT-<n> record id (0 for anything else)."""
    match = _CHAT_ID.match(str(record.get("id", "")))
    return int(match.group(1)) if match else 0


def chat_history(store_root: Path, session_id: str) -> list[dict]:
    """One session's chat_turn records, ordered by id (CHAT-1, CHAT-2, …)."""
    records = [r for r in Store(store_root).all("chat_turn")
               if r.get("session_id") == session_id]
    records.sort(key=lambda r: (_chat_number(r), str(r.get("id", ""))))
    return records


def run_chat_turn(store_root: Path, index_path: Path, message: str,
                  session_id: str, lang: str = "") -> dict:
    """One SÜSIE chat turn against the store: assemble the app-state context,
    corpus hits (``retrieval.corpus_search`` over the --index file) and the
    session history, call ``chat.turn`` (gateway via the ``CHAT_GATEWAY``
    seam — None uses the real default), and persist one ``chat_turn`` record
    per side (user, susie) so the append-only event log carries the full
    audit. Gateway failures never raise out of ``chat.turn``: the degraded
    reply is returned and recorded like any other (HTTP 200, degraded: true).
    """
    with _chat_lock:
        state_context = build_state(store_root)
        corpus_hits = retrieval.corpus_search(store_root, Path(index_path), message)
        history = [
            {"role": r.get("role"),
             "content": r.get("utterance") or r.get("message") or ""}
            for r in chat_history(store_root, session_id)
        ]
        reply = chat.turn(message, state_context, corpus_hits, history,
                          gateway=CHAT_GATEWAY, session_id=session_id, lang=lang)
        store = Store(store_root)
        next_id = 1 + max((_chat_number(r) for r in store.all("chat_turn")),
                          default=0)
        store.put("chat_turn", {"id": f"CHAT-{next_id}", "session_id": session_id,
                                "role": "user", "message": message, "at": utc_now()})
        store.put("chat_turn", {"id": f"CHAT-{next_id + 1}", "session_id": session_id,
                                "role": "susie", "utterance": reply.utterance,
                                "at": utc_now(), "agent_run": reply.agent_run})
    # Langfuse: one trace per chat turn through the privacy guard; no key or no network → nothing happens
    langfuse_link.trace_chat(session_id, message, reply.utterance,
                             (reply.agent_run or {}).get("result", {}).get("deterministic_command", ""))
    return {
        "ok": True,
        "utterance": reply.utterance,
        "citations": reply.citations,
        "action": reply.action,
        "confirm_token": (reply.action or {}).get("confirm_token"),
        "needs_confirmation": reply.needs_confirmation,
        "disclaimer": reply.disclaimer,
        "degraded": reply.degraded,
        "agent_run": reply.agent_run,
    }


class SUSIEHandler(BaseHTTPRequestHandler):
    frontend_root = DEFAULT_FRONTEND
    store_root = DEFAULT_STORE
    index_path = DEFAULT_INDEX
    # Module-fixed data/report locations (no request input ever reaches these
    # paths); tests may point them at temp fixtures.
    story_cases_path = ROOT / "data" / "story_cases.json"
    reports_path = ROOT / "reports"
    review_script_path = ROOT / "run_review.py"
    server_version = "SUSIE-bridge/0.1"

    # -- helpers -------------------------------------------------------------
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, url_path: str) -> None:
        rel = url_path.lstrip("/") or "index.html"
        target = (self.frontend_root / rel).resolve()
        try:
            target.relative_to(self.frontend_root.resolve())
        except ValueError:
            self._send_json({"ok": False, "error": "forbidden"}, status=403)
            return
        if not target.is_file():
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # no-store for static files: a stale stylesheet/javascript mid-demo is
        # worse than re-fetching a few KB from localhost
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -- verbs ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            store = Store(self.store_root)
            self._send_json({"ok": True, "store": str(self.store_root),
                             "events": len(store.events())})
        elif path == "/api/state":
            try:
                self._send_json(build_state(self.store_root))
            except Exception as exc:  # bridge must never leak a broken store as data
                self._send_json({"ok": False, "error": f"store unreadable: {exc}"}, status=500)
        elif path == "/api/chat/history":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            session_id = (query.get("session_id") or [""])[0]
            if not session_id.strip():
                self._send_json({"ok": False, "error": "session_id required"}, status=400)
                return
            self._send_json({"ok": True,
                             "turns": chat_history(self.store_root, session_id)})
        elif path == "/api/privacy":
            self._send_json(privacy_status())
        elif path == "/api/regulations":
            self._send_json(regulations_overview())
        elif path == "/api/regulations/search":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            self._send_json(regulations_search(
                (query.get("q") or [""])[0],
                doc=(query.get("doc") or [""])[0],
                limit=int((query.get("limit") or ["30"])[0] or 30)))
        elif path == "/api/regulations/chunk":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            self._send_json(regulation_chunk((query.get("path") or [""])[0]))
        elif path == "/api/regulations/pdf":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            pdf = regulation_pdf((query.get("doc") or [""])[0])
            if pdf is None:
                self._send_json({"ok": False, "error": "pdf not available for this document"},
                                status=404)
                return
            body = pdf.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition",
                             f'inline; filename="{pdf.name}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/report/pdf":
            query = urllib.parse.parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            self._report_pdf({"lang": (query.get("lang") or ["de"])[0]})
        else:
            self._static(path)

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path not in ("/api/run", "/api/review/run", "/api/chat", "/api/action",
                        "/api/report/pdf", "/api/report/seal"):
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"ok": False, "error": f"bad request: {exc}"}, status=400)
            return
        if path == "/api/run":
            live = bool(body.get("live", False))
            # T10-045 footgun guard: the demo re-run used to wipe the store
            # unconditionally (fresh=True), silently destroying a fed corpus.
            # A wipe now requires the explicit opt-in flag; default is additive.
            fresh = bool(body.get("fresh", False))
            try:
                self._send_json(run_demo_into(self.store_root, live=live, fresh=fresh))
            except Exception as exc:
                self._send_json({"ok": False, "error": f"run failed: {exc}"}, status=500)
            return
        if path == "/api/chat":
            self._api_chat(body)
            return
        if path == "/api/report/pdf":
            self._report_pdf(body)
            return
        if path == "/api/report/seal":
            action = body.get("action", "")
            if action not in ("seal", "verify", "tamper-demo"):
                self._send_json({"ok": False,
                                 "error": "action must be seal | verify | tamper-demo"}, status=400)
                return
            try:
                self._send_json({"ok": True,
                                 **run_seal_action(self.store_root, action)})
            except Exception as exc:
                self._send_json({"ok": False, "error": f"seal failed: {exc}"}, status=500)
            return
        # /api/review/run — body is ignored beyond validity ({"scope": ...} is
        # accepted and discarded); only the repo's own run_review.py runs.
        if path == "/api/review/run":
            try:
                self._send_json({"ok": True, "review": run_review_once()})
            except Exception as exc:
                self._send_json({"ok": False, "error": f"review run failed: {exc}"}, status=500)
            return
        # /api/action — the confirm token is single use and consumed even when
        # execution fails afterwards (actions.execute semantics): never assume
        # a token survives an error response.
        action_id = body.get("action_id", "")
        params = body.get("params", {})
        if not isinstance(action_id, str) or not action_id or not isinstance(params, dict):
            self._send_json({"ok": False,
                             "error": "action requires an action_id and a params object"},
                            status=400)
            return
        try:
            result = actions.execute(action_id, params, body.get("confirm_token"),
                                     self.store_root, str(body.get("reviewer", "")),
                                     session_id=str(body.get("session_id", "")))
        except PermissionError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=403)
            return
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        except Exception as exc:
            self._send_json({"ok": False, "error": f"action failed: {exc}"}, status=500)
            return
        self._send_json({"ok": True, "result": result})

    def _report_pdf(self, body: dict) -> None:
        """GET/POST /api/report/pdf — formal report document as application/pdf.

        Any failure becomes JSON (400/500), never a half-written PDF; the
        PDF itself carries the honesty labels (machine-generated footer,
        hash, compliance notice) from itsg.report_pdf.
        """
        client_name = body.get("client_name")
        if client_name is not None and not isinstance(client_name, str):
            self._send_json({"ok": False, "error": "client_name must be a string"}, status=400)
            return
        try:
            pdf = build_report_pdf(self.store_root, live=bool(body.get("live", False)),
                                   client_name=client_name,
                                   lang="en" if body.get("lang") == "en" else "de")
        except Exception as exc:
            self._send_json({"ok": False, "error": f"report pdf failed: {exc}"}, status=500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(pdf)))
        self.send_header("Content-Disposition",
                         'attachment; filename="susie-formalreport.pdf"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(pdf)

    def _api_chat(self, body: dict) -> None:
        """POST /api/chat — one SÜSIE turn; degraded gateway output is still
        HTTP 200 data (chat.turn never raises on transport failure)."""
        session_id = body.get("session_id", "")
        message = body.get("message", "")
        if (not isinstance(session_id, str) or not isinstance(message, str)
                or not message.strip()):
            self._send_json({"ok": False,
                             "error": "chat requires a non-empty message string"},
                            status=400)
            return
        try:
            lang = body.get("lang") if body.get("lang") in ("de", "en") else ""
            self._send_json(run_chat_turn(self.store_root, Path(self.index_path),
                                          message, session_id, lang))
        except Exception as exc:
            self._send_json({"ok": False, "error": f"chat failed: {exc}"}, status=500)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        if path := (args[0] if args else ""):
            if "/api/" in str(path):
                sys.stderr.write(f"[susie-bridge] {self.address_string()} {format % args}\n")


def serve(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itsg.webserver", description="SÜSIE local web bridge")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--frontend", default=str(DEFAULT_FRONTEND))
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    args = parser.parse_args(argv)

    SUSIEHandler.frontend_root = Path(args.frontend).resolve()
    SUSIEHandler.store_root = Path(args.store).resolve()
    SUSIEHandler.index_path = Path(args.index)
    httpd = ThreadingHTTPServer((args.host, args.port), SUSIEHandler)
    print(f"SÜSIE bridge: http://{args.host}:{args.port}/ · frontend={SUSIEHandler.frontend_root} "
          f"· store={SUSIEHandler.store_root} · index={SUSIEHandler.index_path} (Ctrl+C stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
