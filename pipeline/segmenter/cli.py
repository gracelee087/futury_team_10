"""CLI: ``python -m pipeline.segmenter <command>`` — commands land with T10-005."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.segmenter",
        description="Stage B deterministic segmenter (ingestion-pipeline.md §6).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("segment", help="segment a registered source version into canonical + retrieval chunks")
    args = parser.parse_args(argv)
    print(
        f"command {args.command!r} is not implemented yet — owned by task T10-005 "
        "(work order required before coding)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
