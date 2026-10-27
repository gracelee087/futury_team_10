"""Keyword + metadata search over the Markdown chunks in chunks/.

No vector DB (Members 1 and 3 own embeddings). Scoring is plain TF-IDF on
words, with a boost for titles and for metadata (Abgabegrund, Datenbaustein,
section number) that the question names explicitly.
"""
import math
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

CHUNKS_DIR = Path(__file__).resolve().parent.parent / "chunks"
TOP_K = 5

TITLE_WEIGHT = 3.0
ABGABEGRUND_BOOST = 8.0
DATENBAUSTEIN_BOOST = 8.0
SECTION_BOOST = 20.0

_STOPWORDS = frozenset(
    "der die das den dem des ein eine einen einem einer eines und oder nicht ist sind wird werden "
    "wurde wurden von vom zu zum zur mit bei für auf aus als im in am an es sie er wie was wann "
    "welche welcher welches wenn dass ob auch nur sich nach über bis kann können muss müssen "
    "the a an of to is are and or for in on what which when how".split()
)
_WORD = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_ABGABEGRUND_WINDOW = re.compile(r"abgabegr(?:und|ünde)\w*([^.?!\n]{0,60})", re.IGNORECASE)
_TWO_DIGITS = re.compile(r"(?<!\d)\d{2}(?!\d)")
_DATENBAUSTEIN = re.compile(r"\b(DSLW|DB[A-Z]{2})\b", re.IGNORECASE)
_SECTION = re.compile(r"(?<![\d.])\d+(?:\.\d+)+(?![\d])")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # path below chunks/ without ".md", e.g. "VB/3.1.18"
    doc: str
    version: str
    section: str
    title: str
    page_start: int
    page_end: int
    abgabegrund: tuple
    datenbaustein: tuple
    text: str
    score: float = 0.0

    @property
    def pages(self) -> str:
        if self.page_start == self.page_end:
            return str(self.page_start)
        return f"{self.page_start}-{self.page_end}"


_SUFFIXES = (("ungen", "ung"), ("en", ""), ("er", ""), ("es", ""), ("e", ""), ("n", ""), ("s", ""))  # longest first
_MIN_STEM = 5  # never cut a word down below this many letters
_FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s"})


def _stem(token: str) -> str:
    """Tiny deterministic German normaliser: Vorerkrankungen -> vorerkrankung, Abgabegründe -> abgabegrund.

    Strips one plural/case ending and folds umlauts. Words with digits are left alone, so
    codes such as "88" or "dbsd" are never changed. Applied to chunks and questions alike.
    """
    if not token.isalpha():
        return token
    for suffix, replacement in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) + len(replacement) >= _MIN_STEM:
            token = token[: -len(suffix)] + replacement
            break
    return token.translate(_FOLD)


def _tokens(text: str) -> list:
    return [_stem(t) for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _load_chunk(path: Path, root: Path):
    raw = path.read_text(encoding="utf-8-sig")
    match = _FRONT_MATTER.match(raw)
    if not match:
        return None
    meta = yaml.safe_load(match.group(1)) or {}
    try:
        return Chunk(
            chunk_id=path.relative_to(root).with_suffix("").as_posix(),
            doc=str(meta["doc"]),
            version=str(meta["version"]),
            section=str(meta["section"]),
            title=str(meta.get("title") or ""),
            page_start=int(meta["page_start"]),
            page_end=int(meta["page_end"]),
            abgabegrund=tuple(str(x) for x in (meta.get("abgabegrund") or [])),
            datenbaustein=tuple(str(x).upper() for x in (meta.get("datenbaustein") or [])),
            text=match.group(2).strip(),
        )
    except (KeyError, TypeError, ValueError):
        return None  # skip a chunk with broken metadata instead of crashing the whole search


class ChunkIndex:
    def __init__(self, chunks_dir: Path = CHUNKS_DIR):
        root = Path(chunks_dir)
        self.chunks = []
        for path in sorted(root.glob("*/*.md")):  # chunks/README.md is not a chunk
            chunk = _load_chunk(path, root)
            if chunk:
                self.chunks.append(chunk)
        self._body_tokens = [_tokens(c.text) for c in self.chunks]
        self._title_tokens = [_tokens(c.title) for c in self.chunks]
        doc_freq = {}
        for body, title in zip(self._body_tokens, self._title_tokens):
            for tok in set(body) | set(title):
                doc_freq[tok] = doc_freq.get(tok, 0) + 1
        n = max(len(self.chunks), 1)
        self._idf = {tok: math.log(1 + n / df) for tok, df in doc_freq.items()}

    def by_id(self, chunk_id: str):
        return next((c for c in self.chunks if c.chunk_id == chunk_id), None)

    def search(self, question: str, k: int = TOP_K) -> list:
        sections = set(_SECTION.findall(question))
        # "3.1.18" is a section address, not words: keep its digits out of the word scoring
        q_tokens = set(_tokens(_SECTION.sub(" ", question)))
        codes = _abgabegrund_codes(question)
        bausteine = {m.upper() for m in _DATENBAUSTEIN.findall(question)}

        scored = []
        for chunk, body, title in zip(self.chunks, self._body_tokens, self._title_tokens):
            score = 0.0
            for tok in q_tokens:
                idf = self._idf.get(tok)
                if idf is None:
                    continue
                tf = body.count(tok)
                if tf:
                    score += idf * (1 + math.log(tf))
                if tok in title:
                    score += idf * TITLE_WEIGHT
            if codes & set(chunk.abgabegrund):
                score += ABGABEGRUND_BOOST
            if bausteine & set(chunk.datenbaustein):
                score += DATENBAUSTEIN_BOOST
            if chunk.section in sections:
                score += SECTION_BOOST
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda s: (-s[0], s[1].chunk_id))  # ties: stable by id
        return [_with_score(chunk, score) for score, chunk in scored[:k]]


def _abgabegrund_codes(question: str) -> set:
    codes = set()
    for window in _ABGABEGRUND_WINDOW.findall(question):
        codes.update(_TWO_DIGITS.findall(window))
    return codes


def _with_score(chunk: Chunk, score: float) -> Chunk:
    return Chunk(**{**chunk.__dict__, "score": round(score, 3)})


_default_index = None


def search(question: str, k: int = TOP_K, chunks_dir: Path = None) -> list:
    """Top-k chunks for a question. Loads chunks/ once and caches it."""
    global _default_index
    if chunks_dir is not None:
        return ChunkIndex(chunks_dir).search(question, k)
    if _default_index is None:
        _default_index = ChunkIndex()
    return _default_index.search(question, k)
