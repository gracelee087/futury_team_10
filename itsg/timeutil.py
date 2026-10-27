"""Shared timestamp helper (UTC, second precision, ISO-8601)."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
