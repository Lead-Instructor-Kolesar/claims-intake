"""Deterministic document-currency tests. No model is consulted."""

from datetime import date

from promptlab.rules import VersionCandidate, select_current_version


def test_selects_latest_effective_on_or_before_as_of() -> None:
    candidates = [
        VersionCandidate("E01", "1.0", date(2024, 1, 1)),
        VersionCandidate("E02", "2.0", date(2025, 4, 1)),
        VersionCandidate("E03", "3.0", date(2026, 1, 1)),
    ]

    selected = select_current_version(candidates, date(2025, 6, 1))

    assert selected is not None
    assert selected.case_id == "E02"


def test_equal_effective_date_has_no_winner() -> None:
    candidates = [
        VersionCandidate("A", "1.0", date(2025, 6, 1)),
        VersionCandidate("B", "1.1", date(2025, 6, 1)),
    ]

    assert select_current_version(candidates, date(2025, 6, 1)) is None


def test_effective_on_as_of_applies() -> None:
    candidates = [VersionCandidate("S02", "2.0", date(2025, 6, 1))]

    selected = select_current_version(candidates, date(2025, 6, 1))

    assert selected is not None
    assert selected.case_id == "S02"


def test_no_eligible_version_returns_none() -> None:
    candidates = [VersionCandidate("F", "9.0", date(2026, 1, 1))]

    assert select_current_version(candidates, date(2025, 6, 1)) is None
