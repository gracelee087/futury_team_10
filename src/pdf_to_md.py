"""Convert one whole specification PDF into a single Markdown file (no chunking).

ADOPTED IMPLEMENTATION (T10-031): authored by Team 10 teammates on `main`
(snapshot futury_team_10-main.zip, 2026-10-26), audited and adopted verbatim —
see src/PROVENANCE.md.

Reuses the cleaning and heading logic of chunking.py. The front pages (table of
contents, change history) are kept as plain text; the body follows with
Markdown headings and the source page range under each heading.

Usage:  python src/pdf_to_md.py VB [OUT_DIR]   (writes OUT_DIR/<pdf name>.md, default ./md)
"""
import re
import sys
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunking as ch  # noqa: E402

OUT = ch.ROOT / "md"


def convert(name, out=OUT):
    if name not in ch.DOCS:
        raise KeyError(f"unknown document: {name!r}")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = ch.DOCS[name]
    doc = fitz.open(ch.DATA_DIR / cfg["file"])
    lines = [f"# {cfg['title']} (Version {cfg['version']})", "",
             f"Source: `{cfg['file']}` ({doc.page_count} pages)", ""]

    lines += [f"## Inhaltsverzeichnis und Änderungsübersicht (S. 1–{cfg['body_start'] - 1})", ""]
    for pno in range(1, cfg["body_start"]):
        rows = [r["text"] for r in ch.rows_of(doc[pno - 1]) if ch.in_body(r, cfg)]
        if rows:
            lines += [f"*S. {pno}*", ""] + [ch.LEADER.sub(" … ", t) for t in rows] + [""]

    _, _, chunks, _ = ch.chunk_doc(name, cfg)
    for c in chunks:
        _, md = ch.to_markdown(name, cfg, c)
        body = md.split("---\n", 2)[2].strip().split("\n")  # drop YAML front matter
        pages = f"S. {min(c['pages'])}" + (f"–{max(c['pages'])}" if max(c["pages"]) > min(c["pages"]) else "")
        heading = re.sub(r"^#+", "#" * max(2, min(c["level"] + 1, 6)), body[0])  # chapter = ##
        lines += [heading, "", f"*{pages}*", ""] + body[1:] + [""]
    out.mkdir(parents=True, exist_ok=True)
    path = out / (cfg["file"].rsplit(".", 1)[0] + ".md")
    if not path.resolve().is_relative_to(out):  # containment: never escape the output dir
        raise ValueError(f"output filename escapes output dir: {path!r}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "VB"
    print(convert(name, Path(sys.argv[2]) if len(sys.argv) > 2 else OUT))
