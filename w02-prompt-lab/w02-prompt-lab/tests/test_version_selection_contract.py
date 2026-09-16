from datetime import date
from typing import Any

from promptlab.records import OutputRecord
from promptlab.scoring import (
    candidate_from_output,
    load_gold,
    score_version_selection,
)

GOLD = {
    "E01": {
        "id": "E01",
        "task": "extraction",
        "version_group": "small-business-periodic-kyc",
        "expected_current_case_id": "E02",
        "as_of": "2025-06-01",
    },
    "E02": {
        "id": "E02",
        "task": "extraction",
        "version_group": "small-business-periodic-kyc",
        "expected_current_case_id": "E02",
        "as_of": "2025-06-01",
    },
    "E03": {
        "id": "E03",
        "task": "extraction",
        "expected_status": "valid",
    },
}


def present(value: str) -> dict[str, Any]:
    return {"value": value, "status": "present", "citation": None}


def absent() -> dict[str, Any]:
    return {"value": None, "status": "absent", "citation": None}


def extraction_output(version: str | None, effective: str | None) -> dict[str, Any]:
    return {
        "document_status": "valid",
        "version": present(version) if version is not None else absent(),
        "effective_date": present(effective) if effective is not None else absent(),
    }


def output_record(
    case_id: str,
    output: dict[str, Any] | None,
    *,
    model_id: str = "mistral:7b",
    model_name: str = "mistral",
) -> OutputRecord:
    return OutputRecord(
        run_id="run-1",
        task="extraction",
        case_id=case_id,
        model_name=model_name,
        model_id=model_id,
        prompt_id="extract",
        prompt_version="v2",
        succeeded=output is not None,
        repairs=0,
        output=output,
    )


def test_candidate_requires_present_iso_date() -> None:
    assert candidate_from_output("E02", extraction_output("2.0", "2025-01-01")) is not None
    assert candidate_from_output("E02", extraction_output("2.0", None)) is None
    assert candidate_from_output("E02", extraction_output(None, "2025-01-01")) is None
    assert candidate_from_output("E02", extraction_output("2.0", "January 1, 2025")) is None
    assert candidate_from_output("E02", None) is None


def test_candidate_strips_and_parses_iso_date() -> None:
    candidate = candidate_from_output("E02", extraction_output(" 2.0 ", " 2025-01-01 "))
    assert candidate is not None
    assert candidate.version == "2.0"
    assert candidate.effective_date == date(2025, 1, 1)


def test_rule_selects_gold_current_document() -> None:
    scores = score_version_selection(
        output_records=[
            output_record("E01", extraction_output("1.0", "2024-01-01")),
            output_record("E02", extraction_output("2.0", "2025-01-01")),
            output_record("E03", extraction_output("1.5", "2025-02-01")),
        ],
        gold=GOLD,
    )
    assert len(scores) == 1
    score = scores[0]
    assert score.metric == "version_selection"
    assert score.case_id == "E02"
    assert (score.numerator, score.denominator) == (1, 1)
    assert "selected=E02" in (score.detail or "")


def test_missing_current_extraction_fails_selection() -> None:
    scores = score_version_selection(
        output_records=[
            output_record("E01", extraction_output("1.0", "2024-01-01")),
            output_record("E02", extraction_output("2.0", None)),
        ],
        gold=GOLD,
    )
    assert scores[0].numerator == 0
    assert "selected=E01" in (scores[0].detail or "")


def test_equal_effective_dates_are_undetermined() -> None:
    scores = score_version_selection(
        output_records=[
            output_record("E01", extraction_output("1.0", "2025-01-01")),
            output_record("E02", extraction_output("2.0", "2025-01-01")),
        ],
        gold=GOLD,
    )
    assert scores[0].numerator == 0
    assert "selected=None" in (scores[0].detail or "")


def test_each_model_gets_its_own_version_score() -> None:
    scores = score_version_selection(
        output_records=[
            output_record("E01", extraction_output("1.0", "2024-01-01")),
            output_record("E02", extraction_output("2.0", "2025-01-01")),
            output_record(
                "E01",
                extraction_output("1.0", "2024-01-01"),
                model_id="qwen3:8b",
                model_name="qwen",
            ),
            output_record(
                "E02",
                extraction_output("2.0", "2026-01-01"),
                model_id="qwen3:8b",
                model_name="qwen",
            ),
        ],
        gold=GOLD,
    )
    by_model = {score.model_id: score for score in scores}
    assert by_model["mistral:7b"].numerator == 1
    assert by_model["qwen3:8b"].numerator == 0


def test_instructor_extraction_gold_selects_e02() -> None:
    gold = load_gold("extraction")
    scores = score_version_selection(
        output_records=[
            output_record("E01", extraction_output("1.0", "2024-01-01")),
            output_record("E02", extraction_output("2.0", "2025-01-01")),
        ],
        gold=gold,
    )
    assert len(scores) == 1
    assert scores[0].numerator == 1
    assert "small-business-periodic-kyc" in (scores[0].detail or "")
