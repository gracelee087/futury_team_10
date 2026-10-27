"""Deterministic ingestion pipeline for the ITSG review assistant.

Stages (see ingestion-pipeline.md; tasks T10-004/T10-005/T10-006):

  A registry  -- pipeline.registry   (inbox -> data/sources, G0 candidate default)
  B segmenter -- pipeline.segmenter  (tagged PDF/DOCX -> canonical segments + retrieval chunks)
  C index     -- pipeline.index      (SQLite FTS5 over G0-accepted versions; rebuildable cache)

Governing principle (ingestion-pipeline.md §3): ``data/sources/`` is truth;
``data/index/`` is a disposable cache, rebuildable byte-equivalently at any
time. Nothing derived is ever edited by hand.
"""

__version__ = "0.1.0"
