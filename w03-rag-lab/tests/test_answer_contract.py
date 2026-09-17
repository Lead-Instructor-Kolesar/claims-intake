"""Day 3 contract. Exercises the schema shapes and the abstention validator with
no network or database access.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.answer import (
    AbstentionReason,
    ClaimDraft,
    ContextBlock,
    ContextEntry,
    GroundedAnswerDraft,
)


def test_an_answer_requires_at_least_one_claim() -> None:
    with pytest.raises(ValidationError):
        GroundedAnswerDraft(answered=True, claims=[])


def test_every_claim_requires_a_citation() -> None:
    with pytest.raises(ValidationError):
        GroundedAnswerDraft(
            answered=True, claims=[ClaimDraft(statement="x", positions=[])]
        )


def test_an_abstention_carries_a_reason_and_a_note() -> None:
    with pytest.raises(ValidationError):
        GroundedAnswerDraft(answered=False)
    with pytest.raises(ValidationError):
        GroundedAnswerDraft(
            answered=False, abstention_reason=AbstentionReason.NO_CANDIDATES
        )
    ok = GroundedAnswerDraft(
        answered=False,
        abstention_reason=AbstentionReason.EVIDENCE_INSUFFICIENT,
        abstention_note="No entry states a beneficial ownership threshold.",
    )
    assert ok.answered is False


def test_an_abstention_carries_no_claims() -> None:
    with pytest.raises(ValidationError):
        GroundedAnswerDraft(
            answered=False,
            claims=[ClaimDraft(statement="x", positions=[1])],
            abstention_reason=AbstentionReason.EVIDENCE_INSUFFICIENT,
            abstention_note="note",
        )


def test_the_model_facing_draft_has_no_code_populated_fields() -> None:
    fields = set(GroundedAnswerDraft.model_fields)
    assert not fields & {"chunk_ids", "evidence_incomplete", "plan_id", "block_id"}


def test_the_draft_has_no_field_expressing_a_determination() -> None:
    forbidden = {"compliant", "approved", "rejected", "cleared", "escalated", "decision"}
    assert not set(GroundedAnswerDraft.model_fields) & forbidden


def test_a_position_resolves_through_the_block_record() -> None:
    block = ContextBlock(
        block_id="q07-p2",
        entries=[
            ContextEntry(position=1, chunk_id="kyc-ie-0004:v4.2:4.2:0", tokens=96),
            ContextEntry(position=2, chunk_id="kyc-ie-0004:v4.2:6.4:0", tokens=118),
        ],
        text="<evidence>...</evidence>",
        total_tokens=214,
        ordering="ends_first",
        dropped_for_budget=["kyc-ie-0004:v4.2:5.1:0"],
        collapsed_duplicates={},
    )
    by_position = {e.position: e.chunk_id for e in block.entries}
    assert by_position[2] == "kyc-ie-0004:v4.2:6.4:0"
    assert 9 not in by_position


def test_dropped_for_budget_names_identifiers_not_a_count() -> None:
    annotation = ContextBlock.model_fields["dropped_for_budget"].annotation
    assert annotation == list[str]
