"""Scoring. Week 2 reference implementation.

Every metric takes the parsed output and the gold object and returns one result
per field it examined. The signature is deliberately narrow. A metric that needs
the raw response text, the token counts, or a second model call is not a metric
of the kind this harness measures.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MetricResult(BaseModel):
    metric: str
    field: str | None
    passed: bool
    detail: str | None = None


class ScoreRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    case_id: str
    task: Literal["triage", "summarize", "extract"]
    model_id: str
    prompt_id: str
    prompt_version: str
    scorer_version: str
    results: list[MetricResult]


Metric = Callable[[BaseModel, BaseModel], list[MetricResult]]
