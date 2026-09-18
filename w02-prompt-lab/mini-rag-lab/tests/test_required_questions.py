from __future__ import annotations

import json

import pytest

from expense_rag.config import load_settings
from expense_rag.eval_cases import REQUIRED_QUESTIONS, evaluate
from expense_rag.generate import answer_question


def _services_available() -> bool:
    try:
        settings = load_settings()
        from expense_rag.db import connect, count_chunks

        with connect(settings) as conn:
            return count_chunks(conn) == 6
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _services_available(),
    reason="Postgres with ingested policy chunks is not available",
)


def test_required_questions_match_lab_expectations() -> None:
    settings = load_settings()
    report = evaluate(settings, REQUIRED_QUESTIONS)
    failures = [item for item in report["results"] if not item["ok"]]
    assert report["total"] == 6
    assert not failures, json.dumps(failures, indent=2)


def test_retrieval_returns_at_most_three_sorted_distances() -> None:
    settings = load_settings()
    result = answer_question(settings, "How much can I spend on food each day?")
    distances = [item.distance for item in result.retrieved_chunks]
    assert 1 <= len(distances) <= 3
    assert distances == sorted(distances)
    assert all(isinstance(distance, float) for distance in distances)
