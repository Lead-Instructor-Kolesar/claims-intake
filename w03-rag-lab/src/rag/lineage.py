"""Lineage. Day 5 work.

Define IngestionRecord here: one record per source document per build, carrying
build_id, source_path, source_sha256, the reader that parsed it, the fields that
parsed to null, the count of chunks it produced, and the ingest commit. Records
are written to runs/ingest/ as JSON Lines.

These columns cannot be added to a build that has already run without them,
which is why they are recorded from the first build rather than when they are
first needed.
"""

from __future__ import annotations
