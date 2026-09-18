from __future__ import annotations

from expense_rag.chunking import chunk_policy
from expense_rag.config import POLICY_PATH


def test_policy_splits_into_six_structural_chunks() -> None:
    markdown = POLICY_PATH.read_text(encoding="utf-8")
    chunks = chunk_policy(markdown)
    assert len(chunks) == 6
    assert [chunk.section for chunk in chunks] == ["1", "2", "3", "4", "5", "6"]
    assert [chunk.section_title for chunk in chunks] == [
        "Meals",
        "Hotels",
        "Airfare",
        "Ground Transportation",
        "Receipts",
        "Submission Deadline",
    ]


def test_chunk_metadata_and_ids() -> None:
    chunks = chunk_policy(POLICY_PATH.read_text(encoding="utf-8"))
    meals = chunks[0]
    assert meals.chunk_id == "expense-policy:v2.0:section-1"
    assert meals.document == "Employee Expense Policy"
    assert meals.version == "2.0"
    assert meals.text.startswith("Employees may claim up to $65")
    assert "##" not in meals.text
    assert all(chunk.text.strip() for chunk in chunks)


def test_chunks_do_not_split_sentences() -> None:
    chunks = chunk_policy(POLICY_PATH.read_text(encoding="utf-8"))
    for chunk in chunks:
        stripped = chunk.text.strip()
        assert stripped.endswith(".")
        assert not stripped.startswith("##")
