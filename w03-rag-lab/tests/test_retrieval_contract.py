"""Day 2 contract. Exercises the protocol and the fusion boundary against a stub
retriever, with no database access.
"""

from __future__ import annotations

import re
from datetime import date

from rag.config import RRF_CONSTANT
from rag.fusion import reciprocal_rank_fusion
from rag.retrieval import FilterSpec, RetrievalPlan, RetrievalStep


def _spec() -> FilterSpec:
    return FilterSpec(build_id="b1", as_of=date(2026, 3, 15), jurisdiction="IE")


def test_filter_spec_rejects_unknown_fields() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FilterSpec.model_validate(
            {"build_id": "b1", "as_of": "2026-03-15", "as_of_date": "2026-03-15"}
        )


def test_filter_spec_defaults_exclude_undated_documents() -> None:
    assert _spec().include_undated_documents is False


def test_fusion_rewards_agreement_between_retrievers() -> None:
    fused = reciprocal_rank_fusion(
        {"dense": ["a", "b", "c"], "lexical": ["c", "d"]}, RRF_CONSTANT
    )
    assert fused[0][0] == "c"


def test_fusion_breaks_ties_deterministically() -> None:
    first = reciprocal_rank_fusion({"dense": ["b", "a"]}, RRF_CONSTANT)
    second = reciprocal_rank_fusion({"dense": ["b", "a"]}, RRF_CONSTANT)
    assert first == second
    tied = reciprocal_rank_fusion({"dense": ["b"], "lexical": ["a"]}, RRF_CONSTANT)
    assert [chunk_id for chunk_id, _ in tied] == ["a", "b"]


def test_fusion_handles_an_empty_lexical_result() -> None:
    fused = reciprocal_rank_fusion({"dense": ["a", "b"], "lexical": []}, RRF_CONSTANT)
    assert [chunk_id for chunk_id, _ in fused] == ["a", "b"]


def test_plan_records_a_stop_reason_on_every_path() -> None:
    plan = RetrievalPlan(
        plan_id="p1",
        question="q",
        steps=[
            RetrievalStep(
                step_id="s1", query_text="required documentation", filters=_spec(),
                origin="rewrite",
            )
        ],
        passes_used=1,
        stop_reason="pass_limit",
    )
    assert plan.stop_reason == "pass_limit"


def test_query_text_carries_no_facts_from_the_filter() -> None:
    """Facts live on the FilterSpec, never in generated query text.

    Match on word boundaries. A jurisdiction code of IE occurs as a substring of
    ordinary English words such as review, so a naive containment check reports a
    violation on a query that carries no fact at all.
    """
    spec = _spec()
    clean = RetrievalStep(
        step_id="s1",
        query_text="required documentation for a periodic review",
        filters=spec,
        origin="rewrite",
    )
    dirty = RetrievalStep(
        step_id="s2",
        query_text="required documentation in IE for a partnership",
        filters=spec,
        origin="rewrite",
    )
    assert spec.jurisdiction is not None
    pattern = re.compile(rf"\b{re.escape(spec.jurisdiction)}\b", re.IGNORECASE)
    assert pattern.search(clean.query_text) is None
    assert pattern.search(dirty.query_text) is not None
