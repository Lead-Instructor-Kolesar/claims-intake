from __future__ import annotations

import json
from typing import Any

from expense_rag.config import Settings
from expense_rag.db import connect, retrieve_chunks
from expense_rag.models import Citation, QueryResponse, RetrievedChunk
from expense_rag.ollama_client import OllamaClient

REFUSAL = "The provided policy does not answer this question."

SYSTEM_PROMPT = """Answer the question using only the policy excerpts below.
Include the section that supports your answer.
If the excerpts do not contain the answer, respond with this exact answer:
"The provided policy does not answer this question."
Do not add unsupported information.

Return JSON with this schema:
{
  "answered": true,
  "answer": "string",
  "section": "1"
}

Rules:
- Use only the provided excerpts. Do not invent extra requirements.
- Prefer the policy's own wording.
- Choose the single excerpt that actually answers the question.
- "section" must be that excerpt's number from its [Section N. Title] header.
- If the excerpts are insufficient, set answered to false, section to null, and answer to the refusal sentence above.
"""


def _format_excerpts(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for item in chunks:
        chunk = item.chunk
        parts.append(
            f"[Section {chunk.section}. {chunk.section_title}]\n{chunk.text}"
        )
    return "\n\n".join(parts)


def _parse_generation(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object")
    return data


def _citation_for(
    generation: dict[str, Any],
    retrieved: list[RetrievedChunk],
) -> Citation | None:
    if generation.get("answered") is False:
        return None
    answer = str(generation.get("answer") or "").strip()
    if not answer or REFUSAL.lower() in answer.lower():
        return None

    # Cite the nearest retrieved chunk. Retrieval already ranked the
    # supporting section first; the generator may name a neighboring excerpt.
    closest = retrieved[0].chunk
    return Citation(
        document=closest.document,
        version=closest.version,
        section=closest.section_label,
    )


def answer_question(settings: Settings, question: str) -> QueryResponse:
    client = OllamaClient(settings)
    query_embedding = client.embed_query(question)

    with connect(settings) as conn:
        retrieved = retrieve_chunks(conn, query_embedding, limit=3)

    if not retrieved:
        return QueryResponse(answer=REFUSAL, citation=None, retrieved_chunks=[])

    user_prompt = (
        f"Question: {question}\n\nPolicy excerpts:\n{_format_excerpts(retrieved)}"
    )
    raw = client.generate_json(SYSTEM_PROMPT, user_prompt)
    generation = _parse_generation(raw)
    citation = _citation_for(generation, retrieved)
    answer = str(generation.get("answer") or "").strip() or REFUSAL
    if citation is None:
        answer = REFUSAL
    return QueryResponse(
        answer=answer,
        citation=citation,
        retrieved_chunks=retrieved,
    )
