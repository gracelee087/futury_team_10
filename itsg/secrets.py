"""Local encrypted secrets store for SÜSIE (T10-018 LLM wiring).

Purpose: keep credentials OUT of source files, fixtures, tests, and logs
(agent-governance.md §6; AGENTS.md privacy rules). The LLM gateway token
lives here, encrypted at rest; ``itsg.llm`` resolves it by name at call
time. The token currently hard-coded in the root ``api.py`` is disposable
(human owner, 2026-10-26) — its removal from that file is the owner's
call; no new plaintext copies are made anywhere.

Storage: ``data/secrets/susie-secrets.json`` (``data/`` is gitignored):
one Fernet token encrypting a JSON dict {name: value}, keyed by a
PBKDF2-HMAC-SHA256-derived 32-byte key (390_000 iterations, random salt).

Passphrase resolution order:
  1. ``SUSIE_SECRETS_PASSPHRASE`` environment variable;
  2. ``data/secrets/.passphrase`` (chmod 600, random, generated at setup) —
     protects against accidental commit/grep/scan, NOT against local root;
  3. interactive getpass (CLI only, never from library calls).

Fail closed: a missing store, wrong passphrase, or tampered file raises —
no code path returns a placeholder credential.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import secrets as _secrets
import stat
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

STORE_FILENAME = "susie-secrets.json"
PASSPHRASE_FILENAME = ".passphrase"
PBKDF2_ITERATIONS = 390_000
ENV_PASSPHRASE = "SUSIE_SECRETS_PASSPHRASE"

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "secrets"


def default_store_path() -> Path:
    root = Path(os.environ.get("SUSIE_SECRETS_DIR", _DEFAULT_ROOT))
    return root / STORE_FILENAME


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _resolve_passphrase(root: Path, prompt: bool) -> str:
    env = os.environ.get(ENV_PASSPHRASE)
    if env:
        return env
    pp_file = root / PASSPHRASE_FILENAME
    if pp_file.exists():
        return pp_file.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(
            f"no passphrase for secrets store (set {ENV_PASSPHRASE} or create "
            f"{pp_file}); refusing to prompt from a library call"
        )
    return getpass.getpass("SÜSIE secrets passphrase: ")


def ensure_passphrase_file(root: Path) -> Path:
    """Create a random passphrase file (chmod 600) if none exists; returns its path."""
    pp_file = root / PASSPHRASE_FILENAME
    if not pp_file.exists():
        root.mkdir(parents=True, exist_ok=True)
        pp_file.write_text(_secrets.token_urlsafe(24) + "\n", encoding="utf-8")
        pp_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 — owner read/write only
    return pp_file


class SecretsStore:
    """Named secrets encrypted at rest (Fernet over a PBKDF2-derived key)."""

    def __init__(self, path: str | Path | None = None, prompt: bool = False):
        self.path = Path(path) if path else default_store_path()
        self.root = self.path.parent
        self._prompt = prompt

    # -- internals -----------------------------------------------------------
    def _fernet(self) -> tuple[Fernet, dict]:
        if not self.path.exists():
            raise ValueError(f"secrets store not found: {self.path}")
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        salt = base64.b64decode(envelope["salt"])
        passphrase = _resolve_passphrase(self.root, self._prompt)
        fernet = Fernet(_derive_key(passphrase, salt))
        payload = json.loads(fernet.decrypt(envelope["token"].encode("ascii")))
        return fernet, payload  # type: ignore[return-value]

    # -- API -----------------------------------------------------------------
    def set(self, name: str, value: str) -> None:
        """Create or update the store, encrypting {name: value} atomically."""
        if not name or not value:
            raise ValueError("secret name and value must be non-empty")
        self.root.mkdir(parents=True, exist_ok=True)
        pp_file = self.root / PASSPHRASE_FILENAME
        if not pp_file.exists():
            ensure_passphrase_file(self.root)
            print(f"generated passphrase file: {pp_file}", file=sys.stderr)
        passphrase = _resolve_passphrase(self.root, self._prompt)
        salt = _secrets.token_bytes(16)
        fernet = Fernet(_derive_key(passphrase, salt))
        payload = {}
        if self.path.exists():
            try:
                _, existing = self._fernet()
                payload = existing
            except (InvalidToken, ValueError):
                raise ValueError(
                    "existing store unreadable with the current passphrase — "
                    "refusing to overwrite (fail closed)"
                )
        payload[name] = value
        envelope = {
            "kdf": "PBKDF2-HMAC-SHA256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "token": fernet.encrypt(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ).decode("ascii"),
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(self.path)

    def get(self, name: str) -> str:
        _, payload = self._fernet()
        if name not in payload:
            raise KeyError(f"secret {name!r} not in store {self.path}")
        return payload[name]

    def has(self, name: str) -> bool:
        try:
            _, payload = self._fernet()
        except (ValueError, InvalidToken):
            return False
        return name in payload

    def names(self) -> list[str]:
        _, payload = self._fernet()
        return sorted(payload)


def _main(argv: list[str]) -> int:
    store = SecretsStore(prompt=True)
    if len(argv) >= 2 and argv[0] == "set":
        name = argv[1]
        value = sys.stdin.read().strip() if "--stdin" in argv else getpass.getpass(
            f"value for {name}: "
        )
        store.set(name, value)
        print(f"stored {name!r} in {store.path} (value never echoed)")
        return 0
    if len(argv) >= 2 and argv[0] == "get":
        print(store.get(argv[1]), end="")
        return 0
    if len(argv) >= 2 and argv[0] == "has":
        print(store.has(argv[1]))
        return 0
    if argv and argv[0] == "names":
        for name in store.names():
            print(name)
        return 0
    print("usage: python3 -m itsg.secrets set NAME [--stdin] | get NAME | has NAME | names",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
