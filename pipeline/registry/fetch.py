"""Fetch helper — deferred by the §9 #5 provisional default (no auto-crawl).

Network policy for any future implementation (fail closed; repo security
constraint): only http/https schemes; validate the host before any request
by resolving it and rejecting loopback, private, link-local, multicast,
reserved, and unspecified addresses. Anything fetched lands in
``data/inbox/`` with G0 status ``candidate`` — fetch is not accept
(ingestion-pipeline.md §5).
"""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")


def validate_http_url(url: str) -> str:
    """Return the URL unchanged if it passes the fetch policy, else raise ValueError."""
    parts = urlparse(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"only http/https URLs are allowed, got scheme {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise ValueError("URL has no host")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(f"cannot resolve host {host!r}") from exc
    for info in addr_infos:
        address = ipaddress.ip_address(info[4][0])
        blocked = (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        if blocked:
            raise ValueError(f"host {host!r} resolves to a blocked address ({address})")
    return url


def fetch_to_inbox(url: str, inbox: Path) -> Path:
    """Fetch a document into the inbox as a new candidate. STUB — decided by T10-004."""
    validate_http_url(url)
    raise NotImplementedError("T10-004: fetch helper (policy-validated entry point)")
