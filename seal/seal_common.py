"""Shared helpers for the seal service: canonical JSON, hashes and MACs. Standard library only."""
import hashlib
import hmac
import json
import re

RUN_ID_RE = re.compile(r"^RUN-[0-9a-f]{24}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ZERO_HASH = "0" * 64
RECEIPT_FIELDS = ("run_id", "report_sha256", "issued_at", "submitted_at", "seq")


def canonical(obj) -> str:
    """The one JSON form that is hashed and MACed: sorted keys, no spaces, real UTF-8 characters."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def report_hash(report) -> str:
    return sha256_hex(canonical(report))


def make_mac(secret: bytes, kind: str, fields: dict) -> str:
    """HMAC-SHA256 over the canonical fields. `kind` keeps receipt MACs and ledger MACs apart."""
    return hmac.new(secret, canonical({"kind": kind, **fields}).encode("utf-8"), hashlib.sha256).hexdigest()


def receipt_mac(secret: bytes, receipt: dict) -> str:
    return make_mac(secret, "receipt", {k: receipt[k] for k in RECEIPT_FIELDS})


def same(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))
