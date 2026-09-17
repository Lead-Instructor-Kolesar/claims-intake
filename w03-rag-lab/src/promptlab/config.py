"""Week 2 configuration, carried into Week 3.

One change from the Week 2 end state: SPEND_RECORD_DIRS. Week 2 summed a single
directory. Week 3 embeds the whole corpus at ingest, so the running total has to
span completion records and embedding records. The budget computation iterates
this tuple instead of reading one hard-coded path.

Week 3's own ceiling and rate table are in rag.config. This module keeps Week 2's
values so that Week 2 code carried into Week 3 behaves as it did.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
RUN_DIR = REPO_ROOT / "runs"

MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    "azure_openai": "gpt-5-mini",
}

# US dollars per million tokens. Verify against current provider pricing before
# quoting any cost figure.
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
}

SPEND_CEILING_USD = 25.0
RUN_CAP_USD = 2.0

SPEND_RECORD_DIRS: tuple[Path, ...] = (
    RUN_DIR / "completions",
    RUN_DIR / "embeddings",
)

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_OUTPUT_TOKENS = 2048
