"""Token counting. Shipped complete.

Assembly needs a count before a call is made, so this cannot wait for a
response to report usage.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=4)
def _encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str | None = None) -> int:
    """Return the token count for `text` under the configured model.

    The count is an estimate for any provider whose tokenizer is not published.
    It is stable across runs, which is what assembly needs from it.
    """
    from rag.config import GENERATION_MODEL

    return len(_encoding(model or GENERATION_MODEL).encode(text))
