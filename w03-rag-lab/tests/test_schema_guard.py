"""The migration literal and the pinned dimension are one value in two places.

The article that teaches the store requires the vector column length to be
rendered from EMBEDDING_DIMENSION rather than typed by hand. The migration ships
with a literal so that it reads as SQL, so this guard is what keeps the two from
drifting apart silently.
"""

from __future__ import annotations

import re

from rag.config import EMBEDDING_DIMENSION, REPO_ROOT


def test_migration_vector_length_matches_the_pinned_dimension() -> None:
    sql = (REPO_ROOT / "migrations" / "001_chunk.sql").read_text()
    match = re.search(r"vector\((\d+)\)", sql)
    assert match is not None
    assert int(match.group(1)) == EMBEDDING_DIMENSION


def test_the_day_five_migration_is_staged_away_from_day_one() -> None:
    day5 = REPO_ROOT / "migrations" / "day5" / "003_document.sql"
    assert day5.exists()
    assert "chunk_document_fk" in day5.read_text()
    for path in (REPO_ROOT / "migrations").glob("*.sql"):
        assert "chunk_document_fk" not in path.read_text()


def test_the_pinned_provider_and_model_agree() -> None:
    """Switching provider is two lines in config. This catches changing one."""
    from promptlab.config import MODELS
    from rag.config import GENERATION_MODEL, GENERATION_PROVIDER

    assert GENERATION_PROVIDER in MODELS
    assert MODELS[GENERATION_PROVIDER] == GENERATION_MODEL


def test_the_pinned_model_has_a_rate() -> None:
    from rag.config import EMBEDDING_MODEL, GENERATION_MODEL, PRICING_USD_PER_MTOK

    assert GENERATION_MODEL in PRICING_USD_PER_MTOK
    assert EMBEDDING_MODEL in PRICING_USD_PER_MTOK
