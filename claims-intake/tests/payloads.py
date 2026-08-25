"""Access to the notification payloads in `data/`.

The payload files are the realistic inputs every layer is tested against, and the
classification in `docs/payload-triage.md` is keyed on the identifiers they carry.
Tests ask for a payload by identifier so that a failure names the payload rather
than a position in a list.

Every accessor returns a fresh dictionary. Handing the same dictionary to two
tests would let one of them edit the other's input and make the suite depend on
the order it ran in.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

PAYLOAD_FILES = ("fnol_valid.json", "fnol_invalid.json", "fnol_edge.json")


def _load(filename: str) -> dict[str, dict[str, object]]:
    raw: object = json.loads((DATA_DIR / filename).read_text())
    if not isinstance(raw, list):
        raise TypeError(f"{filename} must be a JSON array")
    loaded: dict[str, dict[str, object]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError(f"{filename} entries must be objects")
        payload_id = item["id"]
        body = item["payload"]
        if not isinstance(payload_id, str) or not isinstance(body, dict):
            raise TypeError("id must be a string and payload must be an object")
        loaded[payload_id] = body
    return loaded


def _registry() -> dict[str, dict[str, object]]:
    """Every payload across the three files, keyed by identifier.

    The identifiers are unique across files, so one lookup serves all three. A
    duplicate would make a test ambiguous about which payload it exercised, so it
    is refused here rather than silently resolved.
    """
    registry: dict[str, dict[str, object]] = {}
    for filename in PAYLOAD_FILES:
        for payload_id, body in _load(filename).items():
            if payload_id in registry:
                raise ValueError(f"payload identifier {payload_id!r} is used twice")
            registry[payload_id] = body
    return registry


_PAYLOADS = _registry()


def payload(payload_id: str) -> dict[str, object]:
    """Return a fresh copy of the payload with this identifier."""
    return dict(_PAYLOADS[payload_id])


def payload_ids(prefix: str) -> tuple[str, ...]:
    """Every identifier beginning with `prefix`, in file order.

    Used where a test is parametrised over a whole class of payloads, so that
    adding one to `data/` puts it under test instead of leaving a silent gap.
    """
    return tuple(payload_id for payload_id in _PAYLOADS if payload_id.startswith(prefix))
