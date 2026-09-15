"""Offline tests for the day-3 runner checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from promptlab.day3 import CaseOutcome, citation_failures, split_prompt
from promptlab.records import OutputRecord
from promptlab.schemas import PolicyExtraction, SummarizationOutput

CASE = {
    "id": "S01",
    "task": "summarization",
    "source": (
        "1. Document Control\nTitle: Card Dispute Intake Procedure. Version: 1.0.\n"
        "2. Purpose\nStandardize intake.\n"
        "3. Required Steps\nRecord the merchant and amount.\n"
        "4. Exceptions\nEscalate fraud."
    ),
}


def _outcome(case_id: str, output: dict[str, Any]) -> CaseOutcome:
    record = OutputRecord(
        run_id="test-run",
        task="summarization",
        case_id=case_id,
        model_name="mistral",
        model_id="mistral:7b",
        prompt_version="v1",
        succeeded=True,
        repairs=0,
        output=output,
        error=None,
    )
    return CaseOutcome(record=record, first_error=None)


def test_citation_failures_flag_bare_numbers_and_accept_headings() -> None:
    heading_citation = {
        "document_status": "valid",
        "title": {"value": "v", "status": "present", "citation": "1. Document Control"},
        "version": {"value": None, "status": "absent", "citation": None},
        "effective_date": {"value": None, "status": "absent", "citation": None},
        "purpose": {"value": "p", "status": "present", "citation": "2. Purpose"},
        "required_steps": {"value": None, "status": "absent", "citation": None},
        "exceptions": {"value": None, "status": "absent", "citation": None},
    }
    bare_number = {
        "document_status": "valid",
        "title": {"value": "v", "status": "present", "citation": "1"},
        "version": {"value": None, "status": "absent", "citation": None},
        "effective_date": {"value": None, "status": "absent", "citation": None},
        "purpose": {"value": "p", "status": "present", "citation": "2"},
        "required_steps": {"value": None, "status": "absent", "citation": None},
        "exceptions": {"value": None, "status": "absent", "citation": None},
    }

    assert citation_failures([_outcome("S01", heading_citation)], [CASE], SummarizationOutput) == []
    failures = citation_failures([_outcome("S01", bare_number)], [CASE], SummarizationOutput)
    assert len(failures) == 2
    assert all("S01 " in failure for failure in failures)


def test_citation_check_generalizes_to_extraction_schema() -> None:
    extraction_case = {
        "id": "E01",
        "task": "extraction",
        "source": CASE["source"],
    }
    output = {
        "document_status": "valid",
        "policy_name": {"value": "p", "status": "present", "citation": "Document Control"},
        "version": {"value": None, "status": "absent", "citation": None},
        "effective_date": {"value": None, "status": "absent", "citation": None},
        "jurisdictions": {"value": None, "status": "absent", "citation": None},
        "beneficial_ownership_threshold": {
            "value": None,
            "status": "absent",
            "citation": None,
        },
        "review_frequency": {"value": None, "status": "absent", "citation": None},
        "required_documents": {"value": None, "status": "absent", "citation": None},
    }

    assert citation_failures([_outcome("E01", output)], [extraction_case], PolicyExtraction) == []


def test_split_prompt_keeps_sections_after_the_document(tmp_path: Path) -> None:
    template = (
        "Task\n\nDo the thing.\n\nInput\n\n<document>\n{document_text}\n</document>\n\n"
        "Examples\n\nTwo examples here.\n\nWhen the task cannot be completed\n\nSay so."
    )
    system, user_content = split_prompt(template, "SOURCE TEXT", "SCHEMA TEXT")

    assert "<document>" not in system
    assert "SOURCE TEXT" in user_content
    assert "SCHEMA TEXT" not in system.split("<document>")[0]
    assert "Examples" in user_content
    assert "When the task cannot be completed" in user_content
    assert user_content.startswith("<document>")
