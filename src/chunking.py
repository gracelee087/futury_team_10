"""Header-based chunking of the ITSG EEL specification PDFs into Markdown.

ADOPTED IMPLEMENTATION (T10-031): authored by Team 10 teammates on `main`
(snapshot futury_team_10-main.zip, 2026-10-26), audited and adopted verbatim
by the backend session — see src/PROVENANCE.md for the audit evidence
(0 words lost across all six documents when re-run against this repo's
corpus; byte-identical chunk regeneration; 83/83 VB cross-references).

PyMuPDF reads every text span with its position and font size. Rows are rebuilt
from spans, running headers/footers are cut by y-position, and chunks are split
at headings:
  * numbered headings ("2.1.2 ...", "13.3 ...") that also appear in the PDF's
    table of contents (whitelist against false positives), and
  * VB only: level-3/4 headings whose number is drawn but not extractable as
    text. They are recognised by their x-position (125 / 133 pt) and numbered
    in order under their parent. Cross-references like `3.12.5 „Title“` in the
    body are used to validate that numbering.

Usage:  python src/chunking.py            (writes ./chunks)
Env:    DATA_DIR  folder with the PDFs (default: ../futury_overview/ITSG/ITSG)
"""
import collections
import json
import os
import re
import shutil
from pathlib import Path

import fitz  # PyMuPDF
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT.parent / "futury_overview" / "ITSG" / "ITSG"))
OUT = ROOT / "chunks"

# Rundschreiben footer, cut by its text: landscape pages have it mid-page, form pages have content below it
RS_FOOTER = (r"^Gemeinsames Rundschreiben vom [\d./]+ in der Fassung vom|Seite \d+ von \d+$|^SGB XIV$"
             r"|^Verletztengeld nach § 45 SGB VII und zum Krankengeld der Sozialen Entschädigung")

# body_start: first page after TOC / change history. top/bottom: y-range of body text.
DOCS = {
    "GG_EEL": dict(
        file="GG_EEL_V13.1_06.05.2025.pdf",
        title="Gemeinsame Grundsätze DTA EEL", version="13.1",
        body_start=3, top=75, bottom=740, parent_level=0),
    "VB": dict(
        file="2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf",
        title="Verfahrensbeschreibung DTA EEL", version="13.4",
        body_start=15, top=50, bottom=700, parent_level=2, hidden_x={3: (121, 129), 4: (130, 137)}),
    "Beispiel": dict(
        file="2026_03_10_Endfassung_Beispielpapier_DTA_EEL_Version_13.3_gueltig_ab_01.01.2027.pdf",
        title="Beispielpapier DTA EEL", version="13.3",
        body_start=8, top=70, bottom=800, parent_level=1),  # footer is size < 7, table rows reach y≈765
    # Gemeinsame Rundschreiben (GKV-Spitzenverband): Anl1 Kinderkrankengeld, Anl2 Mutterschaft, Anl3 Krankengeld
    "Anl1": dict(
        file="2025_12_10_NS_FLB_TOP_01_24c24i45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_EEL_Anl1.pdf",
        title="Gemeinsames Rundschreiben Kinderkrankengeld (§ 45 SGB V, § 45 Abs. 4 SGB VII, § 47 Abs. 10 SGB XIV)",
        version="10.12.2025", body_start=15, top=60, bottom=750, parent_level=2, rundschreiben=True, footer=RS_FOOTER),
    "Anl2": dict(
        file="2025_12_10_NS_FLB_TOP_01_24c24i45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_EEL_Anl2.pdf",
        title="Gemeinsames Rundschreiben Leistungen bei Schwangerschaft und Mutterschaft",
        version="10.12.2025", body_start=19, top=60, bottom=770, parent_level=2, rundschreiben=True, footer=RS_FOOTER),
    "Anl3": dict(
        file="2024_12_11_NS_FLB_TOP_02_24c24i4444b45SGBV45SGBVII47SGBXIV_Aktualisierung_der_GR_zu_Entgeltersatzleistungen_Anl3.pdf",
        title="Gemeinsames Rundschreiben Krankengeld, Verletztengeld, Krankengeld der Sozialen Entschädigung",
        version="11.12.2024", body_start=22, top=50, bottom=800, parent_level=2, rundschreiben=True, footer=RS_FOOTER),
}

NUM_HEAD = re.compile(r"^(\d+(?:\.\d+)*)\.?\s*([A-ZÄÖÜ(§].*)$")  # „quoted“ = cross-reference, not a heading
LEADER = re.compile(r"\.{4,}")
CODE = re.compile(r"(?:Abgabegrund|ABGABEGRUND)\D{0,4}(\d{2})")
FIELD = re.compile(r"(?<![A-Za-z0-9-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+(?!\w)(?!-\s*$)")  # skip names cut at a line end
BLOCK = re.compile(r"\b(DS[A-Z]{2}|DB[A-Z]{2})\b")
KEEP_HYPHEN = {"und", "oder", "bzw", "sowie"}


def key(text):
    return re.sub(r"[^0-9a-zäöüß]", "", text.lower())


def clean(text):
    text = re.sub(r"\s*­\s*", " – ", text.strip()) if " ­" in text else text.replace("­", "")
    return " ".join(text.split())


def rows_of(page):
    """Rebuild visual rows from spans: (y, x, size, text, cells=[[x, text], ...])."""
    spans = [s for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])
             for s in line["spans"] if s["text"].strip()]
    groups = []
    for s in sorted(spans, key=lambda s: s["bbox"][1]):
        if groups and s["bbox"][1] - groups[-1][0]["bbox"][1] <= 3:  # bullets sit ~1pt off their text
            groups[-1].append(s)
        else:
            groups.append([s])
    rows = []
    for ss in groups:
        ss.sort(key=lambda s: s["bbox"][0])
        cells = [[ss[0]["bbox"][0], ss[0]["text"]]]
        for prev, s in zip(ss, ss[1:]):
            gap = s["bbox"][0] - prev["bbox"][2]
            if gap > 12:
                cells.append([s["bbox"][0], s["text"]])
            elif gap > 1.5 and not cells[-1][1].endswith(" ") and not s["text"].startswith(" "):
                cells[-1][1] += " " + s["text"]
            else:
                cells[-1][1] += s["text"]
        cells = [[x, clean(t)] for x, t in cells if clean(t)]
        bullet = len(cells) > 1 and cells[0][1] == "•"
        text = ("- " if bullet else "") + " | ".join(t for _, t in cells[bullet:])
        rows.append(dict(y=round(ss[0]["bbox"][1]), x=ss[0]["bbox"][0], size=max(s["size"] for s in ss),
                         text=text, cells=cells[bullet:]))
    return rows


def join_word(a, b, vocab):
    """Join a cell ending in '-' with its continuation; keep the hyphen if it is a real separator."""
    if re.match(r"[a-zäöüß]", b):
        return a + b if b.split()[0].strip(",.") in KEEP_HYPHEN else a[:-1] + b
    if re.search(r"[A-Z0-9]-$", a) and re.match(r"[A-Z0-9]", b):  # field names, e.g. TEIL-NACHWEIS-AU- / BEGINN
        last = re.findall(r"[A-Z0-9-]+-$", a)[-1]
        word = re.match(r"[A-Z0-9-]+", b).group().rstrip("-")
        keep, drop = last + word, last[:-1] + word
        if any(v == keep or v.startswith(keep + "-") for v in vocab):
            return a + b
        if any(v == drop or v.startswith(drop + "-") for v in vocab):
            return a[:-1] + b
        segments = {seg for v in vocab for seg in v.split("-")}
        return a + b if last.rstrip("-").split("-")[-1] in segments else a[:-1] + b
    return a + b


def merge_table_rows(rows, vocab):
    """A table cell that wraps continues on the next row at the same x: glue it back."""
    out = []
    for r in rows:
        r = dict(r, cells=[list(c) for c in r["cells"]])
        prev = out[-1] if out else None
        if prev and len(prev["cells"]) > 1:
            for c in list(r["cells"]):
                # the column that contains c: last prev cell starting left of it
                p = next((p for p in reversed(prev["cells"]) if p[0] <= c[0] + 6), None)
                if p and re.search(r"\w-$", p[1]) and re.match(r"[A-Za-zÄÖÜäöüß„\"“]", c[1]):
                    p[1] = join_word(p[1], c[1], vocab)
                    r["cells"].remove(c)
            prev["text"] = ("- " if prev["text"].startswith("- ") else "") + " | ".join(t for _, t in prev["cells"])
            if not r["cells"]:
                continue
            r["text"] = " | ".join(t for _, t in r["cells"])
        out.append(r)
    return out


def in_body(r, cfg):
    """Inside the body area; small print counts as footer/footnote only at the page bottom
    (Beispielpapier has small-print calculations mid-page)."""
    if cfg.get("footer"):
        return cfg["top"] <= r["y"] <= cfg["bottom"] and not re.search(cfg["footer"], r["text"])
    return cfg["top"] <= r["y"] <= cfg["bottom"] and not (r["size"] < 7 and r["y"] > 745)


def read_toc(doc, cfg):
    toc = {}
    for pno in range(1, cfg["body_start"]):
        for r in rows_of(doc[pno - 1]):
            if r["size"] < 7:  # footnotes, e.g. GG "1 Das Bundesministerium ..."
                continue
            m = NUM_HEAD.match(LEADER.split(r["text"].replace(" | ", " ", 1))[0].strip())
            if m:
                toc.setdefault(m.group(1), key(m.group(2)))
    return toc


def is_toc_row(t):
    """Leader dots, a trailing page number, or an all-caps entry/continuation ("3.1.1 | VERSICHERTE | 28")."""
    return bool(LEADER.search(t) or re.search(r"\s\d{1,3}$", t) or re.search(r"[A-ZÄÖÜ]{3}", t) and not re.search(r"[a-zäöü]", t))  # ß has no capital form here


def split_mini_toc(rows):
    """Rundschreiben chapters open with their own TOC (Anl3 ch. 12 even repeats the whole TOC).
    It is the leading run of TOC rows, allowing up to 3 wrapped lines ("Beispiel 154 – ...") in between."""
    if sum(bool(LEADER.search(r["text"])) for r in rows) < 3:
        return rows, []
    last, gap = -1, 0
    for i, r in enumerate(rows):
        if is_toc_row(r["text"]):
            last, gap = i, 0
        elif (gap := gap + 1) > 3:
            break
    return rows[last + 1:], rows[:last + 1]


def join_lines(lines):
    out = []
    for line in lines:
        if out and re.search(r"[a-zäöüß]-$", out[-1]) and re.match(r"[a-zäöüß]", line) \
                and line.split()[0].strip(",.") not in KEEP_HYPHEN and " | " not in line:
            out[-1] = out[-1][:-1] + line
        elif out and re.search(r"\w-$", out[-1]) and re.match(r"[A-ZÄÖÜ„\"“]", line) \
                and " | " not in out[-1] + line:  # "Zeitraum-Ende-" / "AU-„nn“": real hyphen, same word
            out[-1] = out[-1] + line
        else:
            out.append(line)
    return out


def chunk_doc(name, cfg):
    doc = fitz.open(DATA_DIR / cfg["file"])
    toc = read_toc(doc, cfg)
    hidden = cfg.get("hidden_x", {})
    chunks, removed = [], collections.Counter()
    cur = dict(section="0", title="Vorbemerkung", level=0, rows=[], rowdicts=[], pages=[])
    stack = {}          # level -> section number of the current heading
    counter = {}        # parent section -> running number for hidden headings
    last_hidden = None  # (x, y, page) of the previous hidden heading row

    def start(section, title, level, pno):
        nonlocal cur
        if cur["rows"] or cur["level"]:
            chunks.append(cur)
        cur = dict(section=section, title=title, level=level, rows=[], rowdicts=[], pages=[pno])
        stack[level] = section
        for lv in [l for l in stack if l > level]:
            del stack[lv]

    for pno in range(cfg["body_start"], doc.page_count + 1):
        # VB draws hidden heading numbers as small images (~24x8 pt) on the heading row
        number_imgs = [i["bbox"][1] for i in doc[pno - 1].get_image_info() if i["bbox"][3] - i["bbox"][1] < 12]
        for r in rows_of(doc[pno - 1]):
            if not in_body(r, cfg):
                removed[re.sub(r"\d+", "#", r["text"])] += 1
                continue
            m = NUM_HEAD.match(r["text"].replace(" | ", " ", 1))  # "2.1 | Title": wide gap after number
            # Rundschreiben: chapter-internal mini TOC ("3.1.1 | VERSICHERTE | 28", all caps or leader dots) is not a heading
            if m and cfg.get("rundschreiben") and (LEADER.search(r["text"]) or not re.search(r"[a-zäöü]", m.group(2))):
                m = None
            in_toc = m and m.group(1) in toc and key(m.group(2))[:6] == toc[m.group(1)][:6]
            # not in TOC (e.g. VB level 4): accept only as the next number under the current section
            nxt = m and "." in m.group(1) and len(r["text"]) < 130 and \
                stack.get(m.group(1).count(".")) == m.group(1).rsplit(".", 1)[0] and \
                int(m.group(1).rsplit(".", 1)[1]) == counter.get(m.group(1).rsplit(".", 1)[0], 0) + 1
            # Rundschreiben: chapter headings are large (11.7-13.7 pt); a chapter overview table repeats "2 | Title | ..."
            h1_ok = not cfg.get("rundschreiben") or (m and "." in m.group(1)) or r["size"] >= 11
            if m and h1_ok and (r["x"] <= 100 or r["size"] >= 13) and (in_toc or nxt):
                sec = m.group(1)
                if nxt:
                    counter[sec.rsplit(".", 1)[0]] += 1
                start(sec, m.group(2), sec.count(".") + 1, pno)
                cur["raw"] = r["text"]
                counter[sec] = 0
                last_hidden = None
                continue
            lvl = next((lv for lv, (a, b) in hidden.items() if a <= r["x"] <= b), None)
            has_num = any(abs(iy - r["y"]) <= 6 for iy in number_imgs)
            wrapped = last_hidden and last_hidden[0] == lvl and last_hidden[2] == pno and 0 < r["y"] - last_hidden[1] <= 17
            if lvl and (has_num or wrapped) and len(r["text"]) < 120 and " | " not in r["text"] and stack.get(lvl - 1):
                if wrapped and not has_num:
                    cur["title"] += " " + r["text"]          # wrapped heading line
                    cur["raw"] += " " + r["text"]
                else:
                    parent = stack[lvl - 1]
                    counter[parent] = counter.get(parent, 0) + 1
                    sec = f"{parent}.{counter[parent]}"
                    start(sec, r["text"], lvl, pno)
                    cur["raw"] = r["text"]
                    counter[sec] = 0
                last_hidden = (lvl, r["y"], pno)
                continue
            last_hidden = None
            cur["rows"].append(r["text"])
            cur["rowdicts"].append(r)
            if pno not in cur["pages"]:
                cur["pages"].append(pno)
    chunks.append(cur)

    for c in chunks:
        c["toc_rows"] = []
        if cfg.get("rundschreiben") and c["level"] == 1:
            c["rowdicts"], c["toc_rows"] = split_mini_toc(c["rowdicts"])
            c["rows"] = [r["text"] for r in c["rowdicts"]]
            removed["[chapter TOC row]"] += len(c["toc_rows"])
    by_sec = {c["section"]: c for c in chunks}
    # complete UPPER-CASE field names (not cut at a line end) decide hyphens in wrapped table cells
    vocab = {v for c in chunks for r in c["rowdicts"] for _, t in r["cells"] for v in FIELD.findall(t)}
    for c in chunks:
        c["title"] = re.sub(r"(\w)- (\w+)", lambda m: m.group(0) if m.group(2) in KEEP_HYPHEN
                            else m.group(1) + m.group(2), c["title"]).strip()
        c["text"] = "\n".join(join_lines([r["text"] for r in merge_table_rows(c["rowdicts"], vocab)]))
        # parent = ancestor at parent_level (GG: whole document)
        parts = c["section"].split(".")
        lvl = cfg["parent_level"]
        c["parent"] = "document" if lvl == 0 else ".".join(parts[:lvl]) if len(parts) > lvl else None
        head = f"{c['title']} {by_sec.get(c['parent'], {}).get('title', '')}"
        c["abgabegrund"] = sorted(set(CODE.findall(head)))
        c["datenbaustein"] = sorted(set(BLOCK.findall(c["title"]) or BLOCK.findall(head)))
    return doc, toc, chunks, removed


def to_markdown(name, cfg, c):
    meta = dict(doc=name, doc_title=cfg["title"], version=cfg["version"], source_file=cfg["file"],
                section=c["section"], title=c["title"], level=c["level"], parent=c["parent"],
                page_start=min(c["pages"]), page_end=max(c["pages"]),
                abgabegrund=c["abgabegrund"], datenbaustein=c["datenbaustein"])
    body, table = [], []
    for line in c["text"].split("\n"):
        if " | " in line:
            table.append(line)
            continue
        if table:
            body += ["```text", *table, "```"]
            table = []
        body.append(line)
    if table:
        body += ["```text", *table, "```"]
    head = "#" * min(c["level"] + 1, 6)
    md = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n"
    md += f"{head} {c['section']} {c['title']}\n\n" + "\n".join(body) + "\n"
    return meta, md


def check(name, cfg, doc, toc, chunks):
    """Independent checks: words, TOC coverage, page coverage, VB cross-references."""
    words = collections.Counter()
    for pno in range(cfg["body_start"], doc.page_count + 1):
        for r in rows_of(doc[pno - 1]):
            if in_body(r, cfg):
                words.update(key(w) for w in r["text"].split() if key(w))
    got = collections.Counter()
    for c in chunks:
        got.update(key(w) for w in f"{c.get('raw', '')} {' '.join(c['rows'])}".split() if key(w))
        got.update(key(w) for r in c["toc_rows"] for w in r["text"].split() if key(w))  # removed on purpose
    lost = words - got
    body_secs = {c["section"] for c in chunks}
    missing_toc = sorted((s for s in toc if s not in body_secs), key=lambda s: [int(p) for p in s.split(".")])
    pages = set(p for c in chunks for p in c["pages"])
    res = dict(chunks=len(chunks), words_pdf=sum(words.values()), words_lost=sum(lost.values()),
               toc_entries=len(toc), toc_missing=missing_toc,
               pages_body=doc.page_count - cfg["body_start"] + 1,
               pages_uncovered=sorted(set(range(cfg["body_start"], doc.page_count + 1)) - pages),
               empty_chunks=[c["section"] for c in chunks if not c["text"].strip() and c["level"] > 0],
               replacement_chars=sum(c["text"].count("�") for c in chunks),
               toc_rows_removed=sum(len(c["toc_rows"]) for c in chunks),
               dup_sections=[s for s, n in collections.Counter(c["section"] for c in chunks).items() if n > 1])
    if cfg.get("hidden_x"):
        full = " ".join(" ".join(c["rows"]) for c in chunks)
        refs = dict(re.findall(r"(\d+\.\d+\.\d+(?:\.\d+)?) „([^“]{3,90})“", full))
        titles = {c["section"]: key(c["title"]) for c in chunks}
        bad = [(n, t) for n, t in refs.items() if key(t)[:12] != titles.get(n, "")[:12]]
        res.update(crossrefs=len(refs), crossrefs_ok=len(refs) - len(bad), crossref_mismatch=bad)
    return res


def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir():  # empty the folder, keep it (Windows locks an open cwd)
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    report, index, removed_all = {}, [], {}
    jsonl_lines = []
    for name, cfg in DOCS.items():
        doc, toc, chunks, removed = chunk_doc(name, cfg)
        doc_dir = (OUT / name).resolve()
        doc_dir.mkdir()
        for c in chunks:
            meta, md = to_markdown(name, cfg, c)
            # section numbers come from parsed PDF text; strip anything path-like before it becomes a filename
            fname = re.sub(r"[^0-9A-Za-z._-]", "_", str(c["section"])) + ".md"
            target = doc_dir / fname
            if not target.resolve().is_relative_to(doc_dir):  # containment: never escape the chunks dir
                raise ValueError(f"chunk filename escapes output dir: {fname!r}")
            target.write_text(md, encoding="utf-8")
            jsonl_lines.append(json.dumps({**meta, "text": c["text"], "path": f"{name}/{fname}"}, ensure_ascii=False) + "\n")
            index.append((name, c["section"], c["title"], meta["page_start"], meta["page_end"], f"{name}/{fname}"))
        report[name] = check(name, cfg, doc, toc, chunks)
        removed_all[name] = removed.most_common(12)
    (OUT / "chunks.jsonl").write_text("".join(jsonl_lines), encoding="utf-8")
    write_index(index)
    (OUT / "REPORT.json").write_text(json.dumps(dict(checks=report, removed_rows=removed_all), ensure_ascii=False, indent=1), encoding="utf-8")
    for name, r in report.items():
        print(name, {k: v for k, v in r.items() if not isinstance(v, list) or len(v) < 8})


def write_index(index):
    lines = ["# Chunk index", "", "| Doc | Section | Title | Pages |", "|---|---|---|---|"]
    for name, sec, title, a, b, path in index:
        pages = f"{a}" if a == b else f"{a}–{b}"
        lines.append(f"| {name} | [{sec}]({path}) | {title.replace('|', '/')} | {pages} |")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
