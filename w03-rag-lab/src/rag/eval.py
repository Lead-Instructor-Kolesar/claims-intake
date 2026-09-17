"""Evaluation. Stage and StageScoreRecord are shipped complete and are not modified.

StageScoreRecord embeds Week 2's ScoreRecord rather than replacing it, so a Week 2
record and a Week 3 record validate against the same model and can be joined.

extract_literals and every metric are Day 4 work.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from promptlab.scoring import ScoreRecord


class Stage(StrEnum):
    FUSED = "fused"
    RERANKED = "reranked"
    ASSEMBLED = "assembled"
    CITED = "cited"


class StageScoreRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    stage: Stage
    retrieval_config_id: str
    score: ScoreRecord


def extract_literals(text: str) -> set[str]:
    """Return the numbers, percentages, dates, durations, section references, and
    defined terms in `text`, using LITERAL_PATTERNS and DEFINED_TERMS.

    Day 4 assignment, instruction 5.
    """
    raise NotImplementedError
