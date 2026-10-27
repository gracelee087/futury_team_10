# Source Ingestion, Segmentation, and RAG Index — Proposed Design

**Status:** Proposal. Produced during a design brainstorm on 2026-10-26 (agent: ZCode / GLM-5.3Flash; human owner: Team 10 product facilitator; reviewer: MSc integration lead). Nothing in this document is implemented or accepted yet. Recommendation labels: **[PROPOSED]** = recommended default pending review; **[OPEN]** = team decision required before implementation.

## 1. Relationship to the architecture

This design concretizes three components from [architecture.md](architecture.md):

- the `REG → SEG` edge in the §2 flow (source registry → segmentation and citation locator);
- the state machine prefix in §9: `INGESTED → SOURCE_CHECKED → SEGMENTED` (later states are out of scope here);
- the §5 rules that hybrid search is a navigation aid, embeddings are keyed by source-version/segment ID, and they are rebuilt or invalidated when a segment changes.

It also implements the human gates: the source gate (G0) decides which versions enter retrieval, and the segmenter stays inside the deterministic-work rule of `agent-governance.md` §1.6 and the Segmenter role contract of `agent-governance.md` §4 (exact text, page/heading/offset locators, extraction warnings, no paraphrase or silent repair).

## 2. Evidence from the corpus survey (2026-10-26)

All PDFs under `ITSG Files/` were inspected with PyMuPDF 1.27 (read-only analysis on branch `amourification/pdf-chunking`). These measurements are the verification baseline for T10-005.

| Document | Pages | Text layer | PDF outline | Tag-tree headings |
|---|---|---|---|---|
| `Laws/GG_EEL_V13.1_06.05.2025.pdf` | 16 | Yes | No | H1×10, H2×10, H3×13 |
| `Rules details/2026_03_10_..._Verfahrensbeschreibung_DTA_EEL_Version_13.4_...pdf` | 168 | Yes | No | H1×5, H2×23, H3×175, H4×18 |
| `Example Case/2026_03_10_..._Beispielpapier_DTA_EEL_Version_13.3_...pdf` | 161 | Yes | No | H1×24, H2×42, H3×24, H4×65 |
| `Laws/2025_12_10_..._Anl1.pdf` | 162 | Yes | 181 bookmarks | H1×16, H2×56, H3×64, H4×36, H5×7 |
| `Laws/2025_12_10_..._Anl2.pdf` | 140 | Yes | 146 bookmarks | H1–H6 full |
| `Laws/2024_12_11_..._Anl3.pdf` | 406 | Yes | No | H1×18, H2×82, H3×84, H4×78, H5×80, H6×154 |
| `Futury-Hackathon-2026-Englisch.pdf` | 13 | Yes | 13 bookmarks | n/a (PowerPoint export) |

Additional survey findings that constrain the design:

- Every file has a full text layer. **No OCR is needed anywhere in the corpus.**
- Every core document is a tagged PDF (`/Marked true` + StructTreeRoot) exported from Microsoft Word, with real H1–H6 heading roles. The hierarchy is machine-readable today.
- Several documents contain machine-readable tables of contents (TOCI tags: 27 in GG_EEL, 204 in Verfahrensbeschreibung) usable as a cross-check list.
- Known quirks: heading numbers can be split onto their own text line ("3.1" / title on the next line, Verfahrensbeschreibung pp. 36–52); headings can wrap across lines; Anl3 carries 154 H6 tags, which suggests style noise to be verified; the big documents contain 176–260 tables each.
- `GG_EEL_V13.1_06.05.2025.pdf` exists twice (`Laws/` and `Rules Input part 1/`) with identical bytes — the registry must deduplicate by checksum.
- Two DOCX files (heading styles readable natively) and one non-document data file (`TEEL0-Test1-DBVO`, ISO-8859 record dump) round out the corpus; the DBVO file is parsed as data, not segmented as a document.

### Tool conclusion

VLM-based parsing is unnecessary for this corpus, and the general-purpose converters were evaluated and set aside:

- **MarkItDown** extracts PDF text without structure (pdfminer path) — unsuitable for heading-based chunking; acceptable only for the DOCX files.
- **Marker / Docling** infer headings with ML layout models and normalize text (dehyphenation, whitespace repair). That conflicts with the Segmenter contract ("must not paraphrase or silently repair source text"), is probabilistic where deterministic extraction is available, and adds multi-GB model dependencies. They remain fallbacks for untagged PDFs and for specialized table extraction if later needed.

### Content deep-dive (2026-10-26, evening — chat-authorized read-only recon)

Follow-up pass over the same files (PyMuPDF text extraction; DOCX via raw `word/document.xml`; no corpus files modified). It records what each document *contains*, beyond the structural survey above:

| Document | Content finding |
|---|---|
| `Example Case/…Beispielpapier_DTA_EEL_Version_13.3…pdf` (161 pp., effective 01.01.2027) | Catalog of ~62 worked examples ("Sachverhalt" blocks) grouped by Abgabegrund (01 Krankengeld, 02 Kinderkrankengeld, 03 Mutterschaftsgeld, …). Each example pairs a concrete input scenario (amounts, dates, employment data) with either (a) expected DTA EEL records at field level — DSLW/DBAL/DBAE/DBVO blocks, e.g. `BRUTTO-1 = 00200000`, `NETTO-1 = 00135384`, `EAZ-BEGINN-1 = 20XX0401` — or (b) an explicit negative result ("Es ist keine Meldung im DTA EEL abzugeben, weil …"). "Abwandlungen" sections derive edge-case variants (Kurzarbeit 50/100 %, private insurance, multiple employments, Seeleute, shortened calculation periods, Vorerkrankung) with per-field explanations. Years are anonymized as `20XX`; a version changelog records per-example edits. |
| `Laws/…Anl1`, `…Anl2`, `…Anl3` | These are **Gemeinsame Rundschreiben** (joint circulars of GKV-Spitzenverband, the insurance umbrella associations, and DGUV), not statutes: Anl1 = Krankengeld bei Erkrankung des Kindes (§ 45 SGB V, § 45 Abs. 4 SGB VII, § 47 Abs. 10 SGB XIV), Fassung 10.12.2025; Anl2 = Leistungen bei Schwangerschaft und Mutterschaft, Fassung 10.12.2025; Anl3 = Krankengeld nach § 44 SGB V u. a., Fassung 11.12.2024. Normative rule text (70 %, Kalendertagsatz, Höchstbetrag) plus many prose "Beispiel" clarifications. A regex scan for €-amounts (`…,\d{2} €`) matched **zero** pages — numeric ground truth lives in the Beispielpapier, not the Rundschreiben. |
| `test case/Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx` | Official multi-step integration test script with concrete 2025/2026 AU periods: Krankenkasse rejection (Kennzeichen „4 – AU liegt nicht vor", Abgabegrund 61), DBVO correction, employer storno (Abgabegrund 88), resubmission (Abgabegrund 01), with a per-step ID table (DSID, DSID-UR, REF-ID, AZVU). |
| `Rules details/DTA-EEL-Beispiel_Vorerkrankung.docx` | Deterministic trigger rule, citable to Verfahrensbeschreibung DTA EEL Punkt 3.12: Vorerkrankungsanfrage (Abgabegrund 41) iff at least one bescheinigte Vorerkrankung within 6 months before the current AU **and** cumulative AU times ≥ 30 days within 12 months. |
| `TEEL0-Test1-DBVO` | Fixed-width DTA record dump (VOSZAGEEL/DSKOLEIST/DSLW/DBAP/DBID/DBVO blocks; test person "Mia Testfrau"; sender ITSG GmbH). Its AU dates match the test-constellation DOCX — a ready wire-format parser fixture. |

Implications for the pipeline:

1. **Expected values exist officially.** The Beispielpapier supplies authoritative, versioned, field-level expected records. Test-case generation and the comparator can be grounded in cited official examples instead of invented fixtures. This affects plan.md's "no authoritative expected value" risk and §9 #4: the demo slice should use Beispielpapier examples plus the test-constellation DOCX pair as its fixture set.
2. **Source roles are identifiable** and map to registry `source_type`: Rundschreiben = normative rules; Verfahrensbeschreibung/GG_EEL = process/technical specification; Beispielpapier = official examples (test evidence); test-constellation DOCX = test instruction; TEEL0 = sample data. The registry must preserve these roles because authority differs per role (architecture §4 source handling order).
3. **A derivable deterministic function exists in-corpus**: the 30-days/12-months Vorerkrankungsanfrage trigger with an official citation — the smallest end-to-end demonstration of "law → versioned deterministic function → validated against official examples".
4. **Boundary:** Beispielpapier expected records describe what the **payroll program must transmit** (Entgeltbescheinigung side). The Krankenkasse-side benefit-amount calculation rules sit in the Rundschreiben as normative text with no official numeric expected values in this corpus. Demo claims must respect that line.

## 3. Governing principle

**`data/sources/` is truth; `data/index/` is a disposable cache.** Originals are immutable, segments are deterministically derived from originals, and the index is deterministically derived from segments. It must be safe to delete `data/index/` at any time and rebuild it byte-equivalently. Nothing derived is ever edited by hand.

## 4. Directory layout [PROPOSED]

```text
data/
  inbox/                          # drop zone / fetch target, status=unprocessed
  sources/
    SRC-001/
      source.json                 # identity: title, issuing_body, source_type, official_uri
      SRCV-001-A/                 # one folder per VERSION; never overwritten
        original.pdf              # immutable original
        manifest.json             # checksum, retrieved_at, uri, dates, G0 status, reviewer
        segments.jsonl            # derived, deterministic (stage B output)
        extraction_report.json    # warnings, heading-count reconciliation (stage B output)
  index/
    fts/                          # rebuildable keyword index (stage C output)
    vectors/                      # rebuildable, optional, later
```

Rules: folders are per **version**, never per title; a new edition of a source creates a new SRCV folder and records `supersedes`; intake paths that present identical checksums link to one SRCV instead of duplicating.

## 5. Stage A — intake and registry (proposed task T10-004)

- Files are dropped into `data/inbox/` or fetched by a helper. **Fetching is not accepting:** a fetch fills provenance fields (`official_uri_or_origin`, `retrieved_at`) automatically but every version enters with G0 status `candidate`; only a human review moves it to `accepted` (architecture §7 gate G0). The index builder silently skips non-accepted versions — fail closed.
- `manifest.json` carries the architecture §4 source fields (`source_id`, title, issuing_body, source_type, official_uri_or_origin, retrieved_at, published_or_issued_at, edition_or_version, valid_from, valid_to, language, checksum, supersedes, status, reviewer, notes).
- Filenames carry version hints (`V13.1`, `gueltig_ab_01.01.2027`); these are captured as **candidate** metadata, never as verified facts. Unknown fields stay empty rather than guessed.
- Publication/version date is kept separate from effective date, per architecture §4.

## 6. Stage B — segmentation (proposed task T10-005)

Two-level chunking, because heading sections in this corpus range from one paragraph to ~14 pages (Verfahrensbeschreibung §3.1 spans pp. 36–50):

1. **Canonical Segments** — one per heading (H1–H6 read from the PDF tag tree, corroborated by font weight and the hierarchical numbering pattern `^\d+(\.\d+)*`). These are the citation targets and the `Segment` graph nodes of architecture §5. They are never split or overlapped.
2. **Retrieval chunks** — paragraph-based windows within a section, each carrying the full heading path and page range. Paragraph boundaries are used instead of token windows so German legal sentences are not cut.

Extraction method: deterministic, local, zero tokens — PyMuPDF reads the structure tags in document order and pairs them with per-page line extraction (`get_text("dict")`), merging known quirks (split heading lines, wrapped headings, dot-leader TOC lines filtered out). DOCX files are segmented from Word heading styles via `python-docx`. The hackathon deck is chunked from its outline or excluded from RAG (it is challenge context, not law).

Purity rules:

- Stored segment text is exact source text — no normalization, no dehyphenation. Breadcrumbs such as `GG_EEL V13.1 > 2 Mitteilungsverfahren > 2.1.3 …` are prepended **at embed/query time**, never stored into the text.
- Quirks and low-confidence findings (Anl3 H6 noise, tables, split lines) become per-segment `extraction_warnings` and may mark segments `needs_review` so uncertainty stays visible downstream.
- Tables stay inside their section chunk for v1; structured table extraction is a later, specialized step. **[OPEN]** whether table fidelity matters for the demo.
- Segment IDs must be stable for a given source version so requirements can cite them across runs.

Segment record sketch (JSON, aligned with the §5 citation shape):

```json
{
  "segment_id": "SEG-...",
  "source_version_id": "SRCV-...",
  "heading_level": 3,
  "heading_path": ["2", "2.1", "2.1.3"],
  "title": "Anforderung anrechenbare Vorerkrankungen",
  "page_start": 7, "page_end": 7,
  "text": "...exact source text...",
  "chunk_type": "heading_section | paragraph | table",
  "extraction_warnings": [],
  "status": "candidate | needs_review"
}
```

## 7. Stage C — index building (proposed task T10-006)

- **[PROPOSED]** MVP index is SQLite FTS5 (keyword). Vector search is explicitly deferred — `plan.md`'s scope-cut order removes vector search before automatic PDF parsing, so vectors must not sit on the critical path. German retrieval quality from FTS5 alone is adequate for the demo. **[OPEN]** if/when vectors are added: local multilingual model (e.g. multilingual-e5, bge-m3), embeddings keyed by `source_version_id` + `segment_id` and invalidated when that segment changes (architecture §5).
- Every index row carries `source_version_id`, `segment_id`, heading path, and page range, so every retrieval result can show the exact German passage beside its metadata.
- Each build writes an audit record (tool version, input checksums, counts, warnings), matching the audit-envelope pattern of `agent-governance.md` §3.
- Retrieval serves only G0-accepted source versions.

## 8. Verification hooks (acceptance criteria for T10-004–T10-006)

1. **Round-trip purity:** every chunk's text is a verbatim substring of the stored original. Mechanically checkable; directly proves the Segmenter contract.
2. **Heading reconciliation:** detected heading counts per level per document must match the §2 baseline (mismatches go into `extraction_report.json` as warnings, never silently dropped).
3. **TOC cross-check:** detected section titles are compared against the machine-readable TOCI entries (e.g. 27 in GG_EEL, 204 in Verfahrensbeschreibung).
4. **Gate filtering:** with a version marked `candidate`, the built index must contain none of its rows; after G0 acceptance and rebuild, the rows appear.
5. **Dedupe:** registering the two GG_EEL copies yields one SRCV with two recorded intake paths.
6. **Rebuild determinism:** deleting `data/index/` and rebuilding yields equivalent search results.
7. **Human spot-check:** a sample of segments per document is reviewed by a human before the design is marked accepted (requirement-gate discipline).

## 9. Decisions and open questions

| # | Question | Options | Current lean |
|---|---|---|---|
| 1 | Index stack for the MVP | FTS5 only / + local vectors / full vector DB | FTS5 first, vectors deferred [PROPOSED] |
| 2 | Chunk storage format | JSONL canonical / folder-per-section MD / DB only | JSONL canonical; optional MD export as a read-only review view [PROPOSED] |
| 3 | Table handling for v1 | keep inside section chunk / structured extraction | keep inside section chunk [PROPOSED] |
| 4 | Demo corpus scope | one source version / full corpus | full corpus indexed as credibility stress test (Anl3, 406 pp., is the stress case); demo slice needs only one excerpt [PROPOSED] |
| 5 | Auto-fetch from gov sites during the hackathon | inbox drop only / fetch helper / auto-crawl | fetch helper into `inbox/` at most; auto-crawl stays a "later" item per architecture §10 [PROPOSED] |
| 6 | Embedding model | multilingual-e5 / bge-m3 / none | defer until vectors are decided [OPEN] |
| 7 | Human G0 owner for the real ITSG documents | — | not yet named [OPEN — same as cp-003 open question] |

## 10. Proposed task split

Tasks are registered on `.leapfrog/board.md` (T10-003 covers this document; T10-004–T10-006 are `READY` and require an issued work order per `agent-governance.md` §6 before any code changes):

- **T10-004 — Registry + inbox import:** manifest schemas, checksum dedupe, inbox move, G0 status field. State mapping: `INGESTED → SOURCE_CHECKED`.
- **T10-005 — Segmenter:** tagged-PDF extractor (§2 method), DOCX heading styles, two-level chunker, extraction report. State mapping: `SEGMENTED`.
- **T10-006 — Index builder + verification harness:** FTS5 build, round-trip verifier, reconciliation checks, rebuild determinism check.

Each task is independently demo-able, has mechanical verification hooks (§8), and T10-005 does not block on T10-004 beyond the shared SRCV identifier.

## Source basis

- Read-only corpus survey of `ITSG Files/` with PyMuPDF 1.27 on 2026-10-26 (branch `amourification/pdf-chunking`); measurements in §2 are reproducible by re-running the survey.
- [architecture.md](architecture.md) §2, §4, §5, §7, §9, §10; [agent-governance.md](agent-governance.md) §1.6, §3, §4, §5 (gates), §6; [plan.md](plan.md) scope-cut order.
