from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptlab.config import PII_PATTERNS, PROJECT_ROOT
from promptlab.schemas import TriageOutput
from promptlab.scoring import SCORER_VERSION, _boundary_holds

DOCS_RUN = PROJECT_ROOT / "docs" / "day5-run.jsonl"
DOCS_SCORES = PROJECT_ROOT / "docs" / "day5-scores.jsonl"


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        pytest.skip(f"missing Day 5 evidence: {path}")
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            assert isinstance(value, dict)
            rows.append(value)
    return rows


def test_day5_evidence_shared_run_and_coverage() -> None:
    run_rows = _load_jsonl(DOCS_RUN)
    score_rows = _load_jsonl(DOCS_SCORES)
    outputs = [row for row in run_rows if "succeeded" in row]
    assert outputs, "day5-run.jsonl must include OutputRecord rows"
    run_ids = {str(row["run_id"]) for row in outputs}
    assert len(run_ids) == 1
    assert run_ids == {str(row["run_id"]) for row in score_rows}

    for task in ("triage", "summarization", "extraction"):
        for model in ("mistral", "qwen"):
            case_ids = {
                str(row["case_id"])
                for row in outputs
                if row["task"] == task and row["model_name"] == model
            }
            assert len(case_ids) == 12, f"{task}/{model} expected 12 cases, got {case_ids}"


def test_day5_evidence_boundary_and_no_pii() -> None:
    outputs = [row for row in _load_jsonl(DOCS_RUN) if "succeeded" in row]
    triage = [
        row
        for row in outputs
        if row["task"] == "triage" and row.get("succeeded") and row.get("output")
    ]
    assert triage
    models = {str(row["model_name"]) for row in triage}
    assert models == {"mistral", "qwen"}

    for row in triage:
        payload = row["output"]
        assert isinstance(payload, dict)
        parsed = TriageOutput.model_validate(payload)
        assert _boundary_holds(parsed)

    for row in outputs:
        if not row.get("succeeded") or not row.get("output"):
            continue
        payload = row["output"]
        assert isinstance(payload, dict)
        blobs = [
            str(payload[key])
            for key in ("draft_reply", "rationale", "analysis")
            if isinstance(payload.get(key), str)
        ]
        free_text = "\n".join(blobs)
        assert not any(pattern.search(free_text) for pattern in PII_PATTERNS)


def test_day5_evidence_scorer_version() -> None:
    scores = _load_jsonl(DOCS_SCORES)
    assert scores
    assert {str(row["scorer_version"]) for row in scores} == {SCORER_VERSION}
