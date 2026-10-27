"""Langfuse link for SÜSIE: the chat can show what Langfuse holds, and every chat turn is traced.

  summary()          datasets (item counts) + harness scores, read from Langfuse; cached 60 s
  item_url(case_id)  link to the case's dataset item in team10-dbvo-v1 (same ids as data/testcases.json)
  trace_chat(...)    one trace per chat turn (user message + SÜSIE reply), through the privacy guard

Keys come from the environment only (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST); no key → every
function returns None and the app works as before. Network or API errors never reach the user (fail-soft).
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request

DATASETS = (("team10-dbvo-v1", "Krankengeld / Vorerkrankung (41)", "Sick leave / prior illness (41)"),
            ("team10-stories-v1", "Story-Fälle (41)", "Story cases (41)"),
            ("team10-maternity-v1", "Mutterschaftsgeld (03)", "Maternity benefit (03)"))
CASE_DATASET = "team10-dbvo-v1"
CACHE_S = 60
_cache: dict = {}


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def host() -> str:
    return (os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
            or "https://cloud.langfuse.com").rstrip("/")


def _client():
    from langfuse import get_client
    return get_client()


def _metrics(query: dict) -> list:
    """GET /api/public/v2/metrics (the legacy trace/score list endpoints answer 410 for this project)."""
    auth = base64.b64encode(f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()).decode()
    url = host() + "/api/public/v2/metrics?query=" + urllib.parse.quote(json.dumps(query))
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + auth})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["data"]


def summary() -> dict | None:
    """{"datasets": [{name, label, items, url}], "scores": {name: {true, false}}, "host"}; None if unavailable."""
    if not enabled():
        return None
    if _cache.get("at", 0) > time.time() - CACHE_S:
        return _cache["summary"]
    try:
        lf = _client()
        datasets = []
        for name, label, label_en in DATASETS:
            try:
                d = lf.get_dataset(name)
            except Exception:  # noqa: BLE001 — a missing dataset is shown as missing, not as an error
                datasets.append({"name": name, "label": label, "label_en": label_en, "items": None, "url": None})
                continue
            datasets.append({"name": name, "label": label, "label_en": label_en, "items": len(d.items),
                             "url": f"{host()}/project/{d.project_id}/datasets/{d.id}"})
            _cache.setdefault("ids", {})[name] = (d.project_id, d.id)
        rows = _metrics({"view": "scores-boolean", "fromTimestamp": "2026-10-01T00:00:00Z",
                         "toTimestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600)),
                         "metrics": [{"measure": "count", "aggregation": "count"}],
                         "dimensions": [{"field": "name"}, {"field": "booleanValue"}]})
        scores: dict = {}
        for r in rows:
            scores.setdefault(r["name"], {"true": 0, "false": 0})["true" if r["booleanValue"] else "false"] = r["count_count"]
        out = {"datasets": datasets, "scores": scores, "host": host()}
    except Exception:  # noqa: BLE001 — Langfuse down or offline: the chat says so instead of failing
        return None
    _cache.update(at=time.time(), summary=out)
    return out


def item_url(case_id: str) -> str | None:
    """Link to the case's dataset item; needs summary() to have read the dataset ids."""
    ids = _cache.get("ids", {}).get(CASE_DATASET)
    if not ids and summary() is None:
        return None
    ids = _cache.get("ids", {}).get(CASE_DATASET)
    if not ids:
        return None
    project_id, dataset_id = ids
    item = urllib.parse.quote(f"{CASE_DATASET}-{case_id}")
    return f"{host()}/project/{project_id}/datasets/{dataset_id}/items/{item}"


def trace_chat(session_id: str, message: str, utterance: str, command: str = "") -> None:
    """One Langfuse trace per chat turn. Text goes through the privacy guard (policy "langfuse": pseudonymized,
    200 characters at most); a suspected personal-data hit is withheld, never sent."""
    if not enabled():
        return
    try:
        from privacy.langfuse_guard import LangfuseGuard
        guard = LangfuseGuard()
        lf = _client()
        with lf.start_as_current_span(**guard.kwargs(name="susie-chat", input={"messages": [message]},
                                                     output={"result": utterance})) as span:
            span.update_trace(**guard.kwargs(name="susie-chat", session_id=f"SUSIE-{session_id or 'anon'}",
                                             tags=["Team10", "susie", "chat"],
                                             metadata={"kind": command or "model"}))
    except Exception:  # noqa: BLE001 — tracing must never break the chat
        return
