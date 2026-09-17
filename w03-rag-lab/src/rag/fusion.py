"""Reciprocal rank fusion. Shipped complete.

Scores from two retrievers are not comparable and ranks are, so fusion operates
on positions only. There is no normalization step and no blending weight, which
is what makes this behave the same way after an embedding model change.

Ties are broken by chunk_id so that two runs over one build produce identical
orderings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[str]],
    constant: int,
) -> list[tuple[str, float]]:
    """Fuse ranked chunk_id lists into one ordering.

    `ranked_lists` maps a retriever name to that retriever's chunk_id values in
    rank order, best first. Returns (chunk_id, score) descending by score, then
    ascending by chunk_id.
    """
    scores: dict[str, float] = {}
    for chunk_ids in ranked_lists.values():
        for position, chunk_id in enumerate(chunk_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
