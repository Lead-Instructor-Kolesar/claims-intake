"""Spend enforcement. Shipped complete.

The running total spans completion records and embedding records, because
ingestion embeds the whole corpus and a rebuild does it again. The ceiling is
checked before a call is made, not reported after.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag.config import RUN_CAP_USD, SPEND_CEILING_USD, SPEND_RECORD_DIRS


class BudgetExceededError(RuntimeError):
    """Raised before a call that would cross a ceiling."""


def _records(directories: tuple[Path, ...]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if line.strip():
                    out.append(json.loads(line))
    return out


def total_spend_usd(directories: tuple[Path, ...] = SPEND_RECORD_DIRS) -> float:
    """Sum cost_usd across every record directory."""
    return sum(float(r.get("cost_usd", 0.0) or 0.0) for r in _records(directories))


def run_spend_usd(run_id: str, directories: tuple[Path, ...] = SPEND_RECORD_DIRS) -> float:
    """Sum cost_usd for one run across every record directory."""
    return sum(
        float(r.get("cost_usd", 0.0) or 0.0)
        for r in _records(directories)
        if r.get("run_id") == run_id
    )


def check_budget(run_id: str, projected_usd: float = 0.0) -> None:
    """Raise if the next call would cross the run cap or the weekly ceiling."""
    run_total = run_spend_usd(run_id) + projected_usd
    if run_total > RUN_CAP_USD:
        raise BudgetExceededError(
            f"run {run_id} would reach {run_total:.4f} USD against a cap of "
            f"{RUN_CAP_USD:.2f}"
        )
    week_total = total_spend_usd() + projected_usd
    if week_total > SPEND_CEILING_USD:
        raise BudgetExceededError(
            f"week would reach {week_total:.4f} USD against a ceiling of "
            f"{SPEND_CEILING_USD:.2f}"
        )
