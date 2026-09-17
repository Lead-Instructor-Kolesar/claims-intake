"""Determined answers. Week 2 reference implementation.

Version currency is a rule over dates. It is not a judgment, so it is not asked
of a model, and it is not a similarity question, so it is not asked of a
retriever. There is one implementation of it and it is here.

Week 3 reaches this through a projection in rag.versioning. It does not
reimplement the comparison.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable


@runtime_checkable
class VersionCandidate(Protocol):
    """The shape this rule decides over.

    Week 2 supplies extracted fields. Week 3 supplies parsed ingest metadata.
    Both project into these four attributes, which is what lets one rule serve
    both without a second implementation.
    """

    doc_id: str
    version: str
    effective_date: date | None
    superseded_by: str | None


def select_current_version(
    extractions: Sequence[VersionCandidate],
    as_of: date,
) -> dict[str, str]:
    """Return the version of each document in force at `as_of`.

    A revision is current when it is effective on or before `as_of` and has not
    been superseded by a revision that is itself effective on or before `as_of`.

    Both halves matter. Testing only `superseded_by is None` returns nothing
    whenever a future revision has been published, which is ordinary in policy
    management because organizations publish ahead of effective dates. Ignoring
    supersession returns a withdrawn document.

    A candidate whose effective_date is None cannot be placed in the chain and is
    not selected. That is a fact about the source, not a defect in this rule, and
    the caller is responsible for reporting how many were excluded.

    The boundary case is pinned by test: a revision effective exactly on `as_of`
    is in force on that date.
    """
    by_doc: dict[str, list[VersionCandidate]] = {}
    for candidate in extractions:
        by_doc.setdefault(candidate.doc_id, []).append(candidate)

    current: dict[str, str] = {}
    for doc_id, candidates in by_doc.items():
        in_force = {
            c.version
            for c in candidates
            if c.effective_date is not None and c.effective_date <= as_of
        }
        if not in_force:
            continue

        withdrawn: set[str] = set()
        for c in candidates:
            if c.version not in in_force or c.superseded_by is None:
                continue
            successor = next(
                (s for s in candidates if s.version == c.superseded_by), None
            )
            if (
                successor is not None
                and successor.effective_date is not None
                and successor.effective_date <= as_of
            ):
                withdrawn.add(c.version)

        surviving = in_force - withdrawn
        if not surviving:
            continue

        def effective_of(version: str, group: Sequence[VersionCandidate]) -> date:
            match = next(c for c in group if c.version == version)
            assert match.effective_date is not None
            return match.effective_date

        current[doc_id] = max(
            sorted(surviving), key=lambda v: effective_of(v, candidates)
        )

    return current
