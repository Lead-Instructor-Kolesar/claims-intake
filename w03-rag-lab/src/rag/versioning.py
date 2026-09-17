"""Version currency projection. Day 2 work, revised on Day 5.

This module owns a projection and owns no date logic. The currency decision is
made by promptlab.rules.select_current_version, which already exists and has its
boundary case pinned. Do not write a date comparison in this file.

Day 2 reads distinct document metadata from the chunk rows. Day 5 replaces that
with a query against the document table. The projection and the delegation are
unchanged by that switch.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from rag.corpus import DocumentMeta


def current_doc_ids(metas: Sequence[DocumentMeta], as_of: date) -> set[str]:
    """Project ingest metadata into the shape select_current_version accepts and
    delegate. Day 2 assignment, instruction 4.
    """
    raise NotImplementedError
