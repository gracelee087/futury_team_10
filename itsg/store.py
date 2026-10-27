"""JSON store + append-only event log (plan.md: "a simple relational store or
versioned JSON files"; JSON chosen for the 24-hour MVP).

Layout under the store root:

  records.json   {kind: {id: record-dict}}         — current state, rewritten atomically
  events.jsonl   one append-only event per mutation — history, never rewritten

Records are plain dicts (schemas in itsg.records). The event log is the
audit backbone: who/what/when for every change (architecture.md §3 audit).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .timeutil import utc_now

_RECORDS = "records.json"
_EVENTS = "events.jsonl"


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------
    @property
    def records_path(self) -> Path:
        return self.root / _RECORDS

    @property
    def events_path(self) -> Path:
        return self.root / _EVENTS

    # -- records -------------------------------------------------------------
    def _load_records(self) -> dict:
        if not self.records_path.exists():
            return {}
        return json.loads(self.records_path.read_text(encoding="utf-8"))

    def _write_records(self, data: dict) -> None:
        tmp = self.records_path.with_name(self.records_path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.records_path)  # atomic on POSIX: readers never see a half file

    def put(self, kind: str, record: dict) -> dict:
        """Upsert one record under ``kind`` and append an event. Returns the event."""
        if not isinstance(record, dict) or not record.get("id"):
            raise ValueError(f"{kind} record requires an 'id' field")
        data = self._load_records()
        data.setdefault(kind, {})[record["id"]] = record
        self._write_records(data)
        return self._append_event(kind=kind, action="put", record_id=record["id"])

    def get(self, kind: str, record_id: str) -> dict | None:
        return self._load_records().get(kind, {}).get(record_id)

    def all(self, kind: str) -> list[dict]:
        return list(self._load_records().get(kind, {}).values())

    # -- events --------------------------------------------------------------
    def _append_event(self, kind: str, action: str, record_id: str) -> dict:
        event = {
            "seq": len(self.events()) + 1,
            "at": utc_now(),
            "kind": kind,
            "action": action,
            "id": record_id,
        }
        with open(self.events_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def events(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
