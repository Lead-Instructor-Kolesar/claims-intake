from datetime import date

from promptlab.rules import VersionCandidate, select_current_version


def candidate(case_id: str, version: str, effective: str) -> VersionCandidate:
    return VersionCandidate(
        case_id=case_id,
        version=version,
        effective_date=date.fromisoformat(effective),
    )


def test_effective_date_equal_to_review_date_is_current() -> None:
    selected = select_current_version(
        [
            candidate("old", "1.0", "2025-01-01"),
            candidate("equal", "2.0", "2025-06-01"),
        ],
        date(2025, 6, 1),
    )
    assert selected is not None
    assert selected.case_id == "equal"


def test_future_version_is_not_selected() -> None:
    selected = select_current_version(
        [
            candidate("current", "1.0", "2025-01-01"),
            candidate("future", "2.0", "2026-01-01"),
        ],
        date(2025, 6, 1),
    )
    assert selected is not None
    assert selected.case_id == "current"


def test_no_eligible_version_returns_none() -> None:
    selected = select_current_version(
        [candidate("future", "2.0", "2026-01-01")],
        date(2025, 6, 1),
    )
    assert selected is None


def test_equal_effective_dates_are_ambiguous() -> None:
    selected = select_current_version(
        [
            candidate("a", "1.0", "2025-01-01"),
            candidate("b", "2.0", "2025-01-01"),
        ],
        date(2025, 6, 1),
    )
    assert selected is None
