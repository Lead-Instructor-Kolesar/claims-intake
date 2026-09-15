"""Day 2 runner tests. These do not make a live model call."""

from __future__ import annotations

import json
from pathlib import Path

from promptlab.config import PROJECT_ROOT
from promptlab.day2 import build_comparison, load_cases, split_prompt


def test_load_cases_reads_all_twelve_summarization_ids() -> None:
    cases = load_cases(PROJECT_ROOT / "cases" / "summarization.jsonl")
    assert [case["id"] for case in cases] == [
        "S01",
        "S02",
        "S03",
        "S04",
        "S05",
        "S06",
        "S07",
        "S08",
        "S09",
        "S10",
        "S11",
        "S12",
    ]
    assert all(case["task"] == "summarization" for case in cases)


def test_split_prompt_puts_instructions_in_system_and_source_in_user() -> None:
    template = "Instructions go here.\n\n<document>\n{document_text}\n</document>\n"
    system, user_content = split_prompt(template, "CASE SOURCE")
    assert "Instructions go here." in system
    assert "{document_text}" not in system
    assert user_content == "CASE SOURCE"


def test_build_comparison_reports_counts_tokens_and_latency(tmp_path: Path) -> None:
    records = [
        {
            "model_id": "mistral:7b",
            "case_id": "S01",
            "attempt": 1,
            "error_type": None,
            "input_tokens": 10,
            "output_tokens": 4,
            "latency_ms": 100,
        },
        {
            "model_id": "mistral:7b",
            "case_id": "S02",
            "attempt": 1,
            "error_type": None,
            "input_tokens": 20,
            "output_tokens": 6,
            "latency_ms": 300,
        },
        {
            "model_id": "qwen3:8b",
            "case_id": "S01",
            "attempt": 1,
            "error_type": None,
            "input_tokens": 12,
            "output_tokens": 5,
            "latency_ms": 200,
        },
    ]
    path = tmp_path / "day2-run.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    markdown = build_comparison(path)
    assert "Successful cases: 2 / 2" in markdown
    assert "Successful cases: 1 / 1" in markdown
    assert "Input token total: 30" in markdown
    assert "Output token total: 10" in markdown
    assert "Median latency_ms: 200" in markdown
    assert "Max latency_ms: 300" in markdown
    assert "cloud price" in markdown.lower() or "0.0" in markdown
