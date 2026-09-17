"""Context assembly and grounded answering.

Every model in this file is shipped complete and is not modified. GroundedAnswerDraft
is what the model returns and contains only fields a model can supply.
GroundedAnswer is what is stored and adds what only code can know.

assemble_context and answer_question are Day 3 work.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ContextEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    chunk_id: str
    tokens: int


class ContextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    entries: list[ContextEntry]
    text: str
    total_tokens: int
    ordering: Literal["ends_first"]
    dropped_for_budget: list[str]
    collapsed_duplicates: dict[str, list[str]]


class AbstentionReason(StrEnum):
    NO_CANDIDATES = "no_candidates"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    EVIDENCE_CONFLICTING = "evidence_conflicting"
    OUTSIDE_SUPPORTED_SCOPE = "outside_supported_scope"


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    positions: list[int]


class GroundedAnswerDraft(BaseModel):
    """What the model returns. Every field here is one the model can supply."""

    model_config = ConfigDict(extra="forbid")

    answered: bool
    claims: list[ClaimDraft] = []
    conflicts: list[ClaimDraft] = []
    abstention_reason: AbstentionReason | None = None
    abstention_note: str | None = None

    @model_validator(mode="after")
    def shape_matches_outcome(self) -> GroundedAnswerDraft:
        if self.answered:
            if not self.claims:
                raise ValueError("answered requires at least one claim")
            if any(not c.positions for c in self.claims):
                raise ValueError("every claim requires at least one position")
        else:
            if self.claims:
                raise ValueError("an abstention carries no claims")
            if self.abstention_reason is None or not self.abstention_note:
                raise ValueError("an abstention requires a reason and a note")
        return self


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    positions: list[int]
    chunk_ids: list[str]


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_id: str
    plan_id: str
    block_id: str
    answered: bool
    claims: list[Claim] = []
    conflicts: list[Claim] = []
    abstention_reason: AbstentionReason | None = None
    abstention_note: str | None = None
    evidence_incomplete: bool
