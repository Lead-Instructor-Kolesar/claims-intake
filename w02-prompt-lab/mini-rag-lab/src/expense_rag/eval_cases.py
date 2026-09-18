from __future__ import annotations

import json
from typing import Any

from expense_rag.config import PROJECT_ROOT, Settings
from expense_rag.generate import REFUSAL, answer_question

REQUIRED_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "meals",
        "question": "How much can I spend on food each day?",
        "expected_section": "1",
        "expected_section_title": "Meals",
        "answer_must_include": ["65"],
        "answer_any_of": [],
        "requires_citation": True,
    },
    {
        "id": "airfare",
        "question": "Can I book first-class airfare?",
        "expected_section": "3",
        "expected_section_title": "Airfare",
        "answer_must_include": ["economy"],
        "answer_any_of": [],
        "requires_citation": True,
    },
    {
        "id": "hotels",
        "question": "My hotel costs $250. What do I need?",
        "expected_section": "2",
        "expected_section_title": "Hotels",
        "answer_must_include": ["manager"],
        "answer_any_of": [],
        "requires_citation": True,
    },
    {
        "id": "receipts",
        "question": "Do I need a receipt for a $20 taxi?",
        "expected_section": "5",
        "expected_section_title": "Receipts",
        "answer_must_include": ["receipt"],
        "answer_any_of": ["no", "not required", "do not need", "don't need"],
        "requires_citation": True,
    },
    {
        "id": "ground",
        "question": "Can I claim a limousine upgrade?",
        "expected_section": "4",
        "expected_section_title": "Ground Transportation",
        "answer_must_include": [],
        "answer_any_of": ["not reimbursable", "cannot", "can't", "no"],
        "requires_citation": True,
    },
    {
        "id": "gym",
        "question": "Does the company reimburse gym memberships?",
        "expected_section": None,
        "expected_section_title": None,
        "answer_must_include": ["does not answer"],
        "answer_any_of": [],
        "requires_citation": False,
    },
]


def _section_numbers(result) -> list[str]:
    return [item.chunk.section for item in result.retrieved_chunks]


def evaluate(settings: Settings, cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        response = answer_question(settings, case["question"])
        payload = response.to_response()
        retrieved_sections = _section_numbers(response)
        distances = [item.distance for item in response.retrieved_chunks]
        checks: dict[str, bool] = {
            "at_most_three_chunks": len(response.retrieved_chunks) <= 3,
            "distances_are_numbers": all(isinstance(d, float) for d in distances),
            "distances_ascending": distances == sorted(distances),
        }
        answer_l = payload["answer"].lower()
        if case["requires_citation"]:
            checks["expected_section_retrieved"] = (
                case["expected_section"] in retrieved_sections
            )
            checks["has_citation"] = payload["citation"] is not None
            if payload["citation"]:
                expected_label = (
                    f"{case['expected_section']}. {case['expected_section_title']}"
                )
                checks["citation_section"] = payload["citation"]["section"] == expected_label
            else:
                checks["citation_section"] = False
            checks["not_refusal"] = REFUSAL.lower() not in answer_l
        else:
            checks["has_no_citation"] = payload["citation"] is None
            checks["is_refusal"] = REFUSAL.lower() in answer_l

        for snippet in case["answer_must_include"]:
            checks[f"mentions:{snippet}"] = snippet.lower() in answer_l
        any_of = case.get("answer_any_of") or []
        if any_of:
            checks["mentions_any"] = any(snippet.lower() in answer_l for snippet in any_of)

        ok = all(checks.values())
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "ok": ok,
                "checks": checks,
                "response": payload,
            }
        )

    report = {
        "passed": sum(1 for item in results if item["ok"]),
        "total": len(results),
        "results": results,
    }
    output_path = PROJECT_ROOT / "outputs" / "required-questions.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
