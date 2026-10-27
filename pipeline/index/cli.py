"""CLI: ``python -m pipeline.index <command>`` — commands land with T10-006."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.index",
        description="Stage C FTS5 index builder and verification harness (ingestion-pipeline.md §7).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="build data/index/fts from accepted source versions")
    sub.add_parser("search", help="keyword search restricted to G0-accepted versions")
    sub.add_parser("verify", help="run the ingestion-pipeline.md §8 verification hooks")
    args = parser.parse_args(argv)
    print(
        f"command {args.command!r} is not implemented yet — owned by task T10-006 "
        "(work order required before coding)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
