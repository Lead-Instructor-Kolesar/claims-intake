"""Document header parsing.

parse_labeled_header is shipped complete. It reads the labeled header convention
used by the KYC and card dispute families.

The compliance manual family does not use it. That family carries version and
effective date in a document control table on the first page. Extending the
parser to read that convention, and writing parse_document to dispatch between
them, is Day 1 work.

Where a field cannot be read, it is null and the document is still ingested. A
document you cannot fully parse is still a document an analyst may need, and
losing it silently is worse than admitting one field could not be read.
"""

from __future__ import annotations

import re
from datetime import date

_LABELED_HEADER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
_LABEL_LINE = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.*)$")

_NULLS = {"", "none", "null", "n/a", "-"}


def _coerce_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_labeled_header(text: str) -> tuple[dict[str, object], str]:
    """Read a labeled header block and return its fields plus the remaining body.

    Returns an empty mapping and the original text when no labeled header is
    present, which is how a caller detects that a different reader is needed.
    Unreadable values come back as None rather than raising.
    """
    match = _LABELED_HEADER.match(text)
    if match is None:
        return {}, text

    fields: dict[str, object] = {}
    for line in match.group("body").splitlines():
        line_match = _LABEL_LINE.match(line.strip())
        if line_match is None:
            continue
        key = line_match.group("key")
        raw = line_match.group("value").strip()
        if raw.lower() in _NULLS:
            fields[key] = None
        elif key == "effective_date":
            fields[key] = _coerce_date(raw)
        elif key == "entity_types":
            fields[key] = [part.strip() for part in raw.split(",") if part.strip()]
        else:
            fields[key] = raw

    return fields, text[match.end():]
