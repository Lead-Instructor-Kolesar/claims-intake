from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from promptlab import day3
from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.records import OutputRecord
from promptlab.schemas import EvidenceField, SummarizationOutput
from promptlab.usage import CallRecord


def test_extract_v1_has_required_sections_in_order() -> None:
    text = day3.EXTRACT_V1_PATH.read_text(encoding="utf-8")
    positions = [text.index(heading) for heading in day3.REQUIRED_PROMPT_SECTIONS]
    assert positions == sorted(positions)
    assert "<document>" in text
    assert "not instruction" in text.lower()
    assert "citation" in text.lower()


def test_extract_v2_adds_examples_from_examples_dir_only() -> None:
    text = day3.EXTRACT_V2_PATH.read_text(encoding="utf-8")
    section_order = [
        *day3.REQUIRED_PROMPT_SECTIONS[:3],
        "Examples",
        *day3.REQUIRED_PROMPT_SECTIONS[3:],
    ]
    positions = [text.index(heading) for heading in section_order]
    assert positions == sorted(positions)
    assert "Northglass" in text
    assert "Redhaven" in text
    assert "E01" not in text
    assert "S01" not in text


def test_section_headings_finds_numbered_and_markdown_headings() -> None:
    source = (
        "1. Document Control\n"
        "Body text.\n"
        "2. Purpose\n"
        "## Article A - Scope\n"
        "More body.\n"
    )
    headings = day3.section_headings(source)
    assert "1. Document Control" in headings
    assert "2. Purpose" in headings
    assert "Article A - Scope" in headings


def test_citation_existence_failures_counts_bad_present_citations() -> None:
    source = "1. Document Control\nTitle: X\n2. Purpose\nDoes a thing.\n"
    output = SummarizationOutput(
        document_status="valid",
        title=EvidenceField(value="X", status="present", citation="1. Document Control"),
        version=EvidenceField(value=None, status="absent", citation=None),
        effective_date=EvidenceField(value=None, status="absent", citation=None),
        purpose=EvidenceField(value="Does a thing.", status="present", citation="Wrong Heading"),
        required_steps=EvidenceField(value="step", status="present", citation=None),
        exceptions=EvidenceField(value=None, status="absent", citation=None),
    )
    assert day3.citation_existence_failures(output, source) == 2


def test_example_leakage_detects_markers() -> None:
    clean = {
        "policy_name": {
            "value": "KYC",
            "status": "present",
            "citation": "1. Document Control",
        }
    }
    dirty = {
        "policy_name": {
            "value": "Northglass Merchant",
            "status": "present",
            "citation": "Article A",
        }
    }
    assert day3.has_example_leakage(clean) is False
    assert day3.has_example_leakage(dirty) is True


def test_repair_rate_counts_cases_with_repairs() -> None:
    records = [
        _output("summarization", "S01", repairs=0),
        _output("summarization", "S02", repairs=1),
        _output("summarization", "S03", repairs=0),
        _output("extraction", "E01", repairs=1),
        _output("extraction", "E02", repairs=1),
    ]
    assert day3.repair_rate(records, "summarization") == pytest.approx(1 / 3)
    assert day3.repair_rate(records, "extraction") == pytest.approx(1.0)


def test_render_prompt_injects_schema_and_splits_document() -> None:
    template = (
        "Task\n\n"
        "schema:\n{schema_description}\n\n"
        "Input\n\n"
        "<document>\n{document_text}\n</document>\n"
    )
    system, user_content = day3.render_prompt(template, "DOC-BODY", SummarizationOutput)
    assert "document_status" in system
    assert "{schema_description}" not in system
    assert user_content.startswith("<document>")
    assert "DOC-BODY" in user_content
    assert "DOC-BODY" not in system


def test_counting_adapter_tracks_calls_and_records() -> None:
    class Inner:
        provider = "ollama"
        model_id = "fixture-model"

        def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
            return CompletionResult(
                succeeded=True,
                text='{"value":"x"}',
                error_type=None,
                records=[
                    CallRecord(
                        record_id="r1",
                        run_id=run_id,
                        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                        provider="ollama",
                        model_id=self.model_id,
                        task=request.task,
                        case_id=request.case_id,
                        prompt_id=request.prompt_id,
                        prompt_version=request.prompt_version,
                        attempt=1,
                        temperature=request.temperature,
                        max_output_tokens=request.max_output_tokens,
                        input_tokens=1,
                        output_tokens=1,
                        cached_input_tokens=None,
                        latency_ms=1,
                        cost_usd=0.0,
                        stop_reason="stop",
                        error_type=None,
                        response_text='{"value":"x"}',
                    )
                ],
            )

    wrapped = day3.CountingAdapter(Inner())
    request = CompletionRequest(
        task="summarization",
        case_id="S00",
        prompt_id="summarize",
        prompt_version="v1",
        system="",
        user_content="hi",
        temperature=0.0,
        max_output_tokens=16,
    )
    wrapped.complete(request, "run-1")
    assert wrapped.calls == 1
    assert len(wrapped.records) == 1


def test_prompt_paths_exist() -> None:
    assert day3.SUMMARIZE_PATH.is_file()
    assert day3.EXTRACT_V1_PATH.is_file()
    assert day3.EXTRACT_V2_PATH.is_file()
    assert Path(day3.SUMMARIZATION_CASES_PATH).is_file()
    assert Path(day3.EXTRACTION_CASES_PATH).is_file()


def _output(task: str, case_id: str, *, repairs: int) -> OutputRecord:
    return OutputRecord(
        run_id="run",
        task=task,  # type: ignore[arg-type]
        case_id=case_id,
        model_name="mistral",
        model_id="mistral:7b",
        prompt_version="v1",
        succeeded=True,
        repairs=repairs,
        output={},
        error=None,
    )
