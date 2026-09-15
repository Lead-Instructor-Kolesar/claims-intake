from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from promptlab.config import PROJECT_ROOT, Settings
from promptlab.day2 import split_baseline_prompt, write_comparison
from promptlab.usage import CallRecord

PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"


def _record(**overrides: object) -> CallRecord:
    settings = Settings.from_env()
    values: dict[str, object] = {
        "record_id": "00000000-0000-4000-8000-000000000001",
        "run_id": "day2-fixture",
        "timestamp": datetime(2026, 9, 11, 16, 0, tzinfo=UTC),
        "provider": "ollama",
        "model_id": settings.models["mistral"].model_id,
        "task": "summarization",
        "case_id": "S01",
        "prompt_id": "baseline",
        "prompt_version": "v0",
        "attempt": 1,
        "temperature": 0.0,
        "max_output_tokens": 256,
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_input_tokens": None,
        "latency_ms": 100,
        "cost_usd": 0.0,
        "stop_reason": "stop",
        "error_type": None,
        "response_text": "ok",
    }
    values.update(overrides)
    return CallRecord.model_validate(values)


def test_baseline_prompt_splits_instruction_from_document_tags() -> None:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    source = "Card Dispute Intake Procedure."

    system, user_content = split_baseline_prompt(template, source)

    assert "<document>" not in system
    assert "</document>" not in system
    assert "{document_text}" not in system
    assert system.startswith(
        "You are reviewing an internal small-business KYC policy document."
    )
    assert "Return a concise plain-text response." in system
    assert user_content == (
        "<document>\nCard Dispute Intake Procedure.\n</document>"
    )


def test_comparison_markdown_is_generated_from_evidence_records(tmp_path: Path) -> None:
    settings = Settings.from_env()
    mistral_id = settings.models["mistral"].model_id
    qwen_id = settings.models["qwen"].model_id
    evidence = tmp_path / "day2-run.jsonl"
    markdown_path = tmp_path / "day2-comparison.md"

    records = [
        _record(
            record_id="00000000-0000-4000-8000-000000000001",
            model_id=mistral_id,
            case_id="S01",
            input_tokens=10,
            output_tokens=4,
            latency_ms=100,
            error_type=None,
            stop_reason="stop",
        ),
        _record(
            record_id="00000000-0000-4000-8000-000000000002",
            model_id=mistral_id,
            case_id="S02",
            input_tokens=20,
            output_tokens=6,
            latency_ms=300,
            error_type="TruncatedResponseError",
            stop_reason="length",
        ),
        _record(
            record_id="00000000-0000-4000-8000-000000000003",
            model_id=qwen_id,
            case_id="S01",
            input_tokens=8,
            output_tokens=2,
            latency_ms=50,
            error_type=None,
            stop_reason="stop",
        ),
        _record(
            record_id="00000000-0000-4000-8000-000000000004",
            model_id=qwen_id,
            case_id="S02",
            input_tokens=0,
            output_tokens=0,
            latency_ms=40,
            error_type="PermanentProviderError",
            stop_reason=None,
            response_text=None,
        ),
    ]
    evidence.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )

    write_comparison(evidence, markdown_path, settings)
    text = markdown_path.read_text(encoding="utf-8")

    assert "## mistral" in text
    assert f"`{mistral_id}`" in text
    assert "- Attempts: 2" in text
    assert "- Successes: 1" in text
    assert "- Truncations: 1" in text
    assert "- Other errors: 0" in text
    assert "- Input tokens: sum=30, mean=15.00" in text
    assert "- Output tokens: sum=10, mean=5.00" in text
    assert "- Latency (ms): mean=200.00, max=300" in text

    assert "## qwen" in text
    assert f"`{qwen_id}`" in text
    assert "- Other errors: 1" in text
    assert "- Input tokens: sum=8, mean=4.00" in text
    assert "- Output tokens: sum=2, mean=1.00" in text
    assert "- Latency (ms): mean=45.00, max=50" in text

    assert text.count("- cost_usd: 0.0") == 2
    lowered = text.lower()
    assert "0.0 for both" in lowered
    assert "no cost winner" in lowered
    assert "cheaper" not in lowered
    assert "lowest cost" not in lowered
