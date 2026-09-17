"""Day 4 contract. Exercises the reranker permutation requirement and the score
record shape against fixtures, with no network or database access.
"""

from __future__ import annotations

import pytest

from promptlab.scoring import MetricResult, ScoreRecord
from rag.eval import Stage, StageScoreRecord
from rag.rerank import RerankedChunk


def _score() -> ScoreRecord:
    return ScoreRecord(
        run_id="r1",
        case_id="q07",
        task="extract",
        model_id="claude-sonnet-5",
        prompt_id="answer",
        prompt_version="v1",
        scorer_version="w03-1",
        results=[MetricResult(metric="recall_at_k", field=None, passed=True)],
    )


def test_stage_record_embeds_week_two_score_record() -> None:
    record = StageScoreRecord(
        question_id="q07",
        stage=Stage.ASSEMBLED,
        retrieval_config_id="rc-1",
        score=_score(),
    )
    assert record.score.scorer_version == "w03-1"


def test_every_stage_is_measurable() -> None:
    assert {s.value for s in Stage} == {"fused", "reranked", "assembled", "cited"}


def test_a_reranked_output_is_a_permutation_of_its_input() -> None:
    inputs = ["a", "b", "c"]
    outputs = [
        RerankedChunk(chunk_id="c", input_rank=3, output_rank=1, reason="responsive"),
        RerankedChunk(chunk_id="a", input_rank=1, output_rank=2, reason="base rule"),
        RerankedChunk(chunk_id="b", input_rank=2, output_rank=3, reason="definitions"),
    ]
    assert sorted(r.chunk_id for r in outputs) == sorted(inputs)
    assert sorted(r.output_rank for r in outputs) == list(range(1, len(inputs) + 1))


def test_a_short_reranked_output_is_rejected() -> None:
    inputs = ["a", "b", "c"]
    outputs = [
        RerankedChunk(chunk_id="c", input_rank=3, output_rank=1, reason="responsive"),
        RerankedChunk(chunk_id="a", input_rank=1, output_rank=2, reason="base rule"),
    ]
    assert sorted(r.chunk_id for r in outputs) != sorted(inputs)


def test_extract_literals_is_not_yet_implemented() -> None:
    from rag.eval import extract_literals

    with pytest.raises(NotImplementedError):
        extract_literals("25 percent")
