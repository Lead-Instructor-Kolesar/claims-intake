from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class VersionCandidate:
    case_id: str
    version: str
    effective_date: date


def select_current_version(
    extractions: list[VersionCandidate], as_of: date
) -> VersionCandidate | None:
    """Return the latest version effective on or before as_of.

    Equality is intentional: a document effective on the review date applies on that date.
    Ambiguous duplicate effective dates have no determined winner and therefore return None.
    """
    eligible = [candidate for candidate in extractions if candidate.effective_date <= as_of]
    if not eligible:
        return None
    latest_date = max(candidate.effective_date for candidate in eligible)
    latest = [candidate for candidate in eligible if candidate.effective_date == latest_date]
    if len(latest) != 1:
        return None
    return latest[0]

