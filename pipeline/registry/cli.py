"""CLI: ``python -m pipeline.registry <command>`` — commands land with T10-004."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.registry",
        description="Stage A source registry and inbox import (ingestion-pipeline.md §5).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-inbox", help="register files from data/inbox/ into data/sources/")
    sub.add_parser("g0-accept", help="record a human G0 acceptance (reviewer + rationale required)")
    args = parser.parse_args(argv)
    print(
        f"command {args.command!r} is not implemented yet — owned by task T10-004 "
        "(work order required before coding)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
