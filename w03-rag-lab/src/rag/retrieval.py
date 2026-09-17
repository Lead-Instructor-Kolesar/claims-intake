"""Retrieval. FilterSpec, RetrievalStep, and RetrievalPlan are shipped complete
and are not modified.

RetrievedChunk, the Retriever protocol, the two retrievers, the coverage checks,
and plan_and_retrieve are Day 2 work.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_id: str
    as_of: date
    jurisdiction: str | None = None
    entity_type: str | None = None
    include_undated_documents: bool = False


class RetrievalStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    query_text: str
    filters: FilterSpec
    origin: Literal["original", "rewrite", "decomposition", "cross_reference"]


class RetrievalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    question: str
    steps: list[RetrievalStep]
    passes_used: int
    stop_reason: Literal[
        "coverage_satisfied", "pass_limit", "step_limit", "empty_after_filter"
    ]
