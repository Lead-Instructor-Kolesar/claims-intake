"""The Week 2 surface Week 3 imports.

src/promptlab/ is carried from Week 2 in place and is not modified this week.
This file pins the exact surface Week 3 depends on, so that reconciling this
reference implementation against the build an instructor already has produces a
specific list of differences rather than a vague sense that something moved.

If a test here fails against a different promptlab build, that is the
reconciliation list.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from promptlab import config, prompts, rules, schemas, scoring, structured
from promptlab.schemas import Evidence, FieldStatus


class _Candidate:
    def __init__(
        self, doc_id: str, version: str, effective: date | None, superseded: str | None
    ) -> None:
        self.doc_id = doc_id
        self.version = version
        self.effective_date = effective
        self.superseded_by = superseded


def test_evidence_rejects_present_without_a_citation() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Evidence[str](status=FieldStatus.PRESENT, value="v4.2")


def test_evidence_accepts_present_with_a_citation() -> None:
    ok = Evidence[str](status=FieldStatus.PRESENT, value="v4.2", section="1.1")
    assert ok.section == "1.1"


def test_score_record_fields_are_unchanged() -> None:
    assert set(scoring.ScoreRecord.model_fields) == {
        "run_id", "case_id", "task", "model_id", "prompt_id", "prompt_version",
        "scorer_version", "results",
    }


def test_metric_signature_takes_two_models_and_returns_results() -> None:
    assert scoring.Metric is not None


def test_prompt_registry_escapes_the_closing_marker() -> None:
    template = prompts.PromptTemplate(
        prompt_id="answer", version="v1", system="s",
        user_template="{document_text}", template_hash="h",
    )
    rendered = prompts.render_user(template, {}, f"before{prompts.MARKER_CLOSE}after")
    assert prompts.MARKER_CLOSE not in rendered


def test_complete_structured_caps_repairs_at_one_by_default() -> None:
    signature = inspect.signature(structured.complete_structured)
    assert signature.parameters["max_repairs"].default == 1


def test_schema_description_is_the_only_output_contract() -> None:
    text = schemas.schema_description(schemas.PolicyExtraction)
    assert "document_version" in text


def test_spend_record_dirs_spans_completions_and_embeddings() -> None:
    names = {d.name for d in config.SPEND_RECORD_DIRS}
    assert names == {"completions", "embeddings"}


def test_a_revision_effective_on_the_review_date_is_in_force() -> None:
    as_of = date(2025, 11, 1)
    current = rules.select_current_version(
        [_Candidate("d", "v4.2", date(2025, 11, 1), None)], as_of
    )
    assert current == {"d": "v4.2"}


def test_a_superseded_revision_is_withdrawn() -> None:
    current = rules.select_current_version(
        [
            _Candidate("d", "v3.1", date(2024, 6, 1), "v4.2"),
            _Candidate("d", "v4.2", date(2025, 11, 1), None),
        ],
        date(2026, 3, 15),
    )
    assert current == {"d": "v4.2"}


def test_a_future_revision_does_not_withdraw_the_policy_in_force() -> None:
    current = rules.select_current_version(
        [
            _Candidate("d", "v3.1", date(2024, 6, 1), "v4.2"),
            _Candidate("d", "v4.2", date(2025, 11, 1), "v4.3"),
            _Candidate("d", "v4.3", date(2026, 7, 1), None),
        ],
        date(2026, 3, 15),
    )
    assert current == {"d": "v4.2"}


def test_an_undated_revision_is_not_selected() -> None:
    current = rules.select_current_version([_Candidate("d", "v1.4", None, None)],
                                           date(2026, 3, 15))
    assert current == {}
