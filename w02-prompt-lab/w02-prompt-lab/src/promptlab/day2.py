"""Day 2: run the baseline prompt against both configured local models."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from statistics import median
from typing import Any, Literal

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings

PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
TASK: Literal["summarization"] = "summarization"
MAX_OUTPUT_TOKENS = 1024
DOCUMENT_OPEN = "<document>"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_prompt_template() -> str:
    candidates = (
        PROJECT_ROOT / "src" / "promptlab" / "prompts" / "baseline.v0.md",
        PROJECT_ROOT / "prompts" / "baseline.v0.md",
        PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md",
    )
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("baseline.v0.md")


def split_prompt(template: str, document_text: str) -> tuple[str, str]:
    if DOCUMENT_OPEN in template:
        system = template.split(DOCUMENT_OPEN, maxsplit=1)[0].strip()
    else:
        system = template.replace("{document_text}", "").strip()
    return system, document_text


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid.uuid4())
    cases = load_cases(PROJECT_ROOT / "cases" / "summarization.jsonl")
    template = load_prompt_template()
    temperature = 0.0

    for model in settings.models.values():
        adapter = OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
        for case in cases:
            system, user_content = split_prompt(template, str(case["source"]))
            request = CompletionRequest(
                task=TASK,
                case_id=str(case["id"]),
                prompt_id=PROMPT_ID,
                prompt_version=PROMPT_VERSION,
                system=system,
                user_content=user_content,
                temperature=temperature,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            adapter.complete(request, run_id)

    write_day2_docs(run_id)
    print(f"run_id={run_id}")


def write_day2_docs(run_id: str) -> None:
    source = Path("runs") / f"{run_id}.jsonl"
    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    dest = docs_dir / "day2-run.jsonl"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (docs_dir / "day2-comparison.md").write_text(build_comparison(dest), encoding="utf-8")


def build_comparison(run_path: Path) -> str:
    records = [
        json.loads(line)
        for line in run_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_model: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_model.setdefault(str(record["model_id"]), []).append(record)

    lines = [
        "# Day 2 local model comparison",
        "",
        "Both models ran through Ollama at the default thinking setting with a "
        "shared 1024-token ceiling. Local provider/API charge is 0.0; "
        "this note does not invent a cloud price.",
        "",
    ]
    observations: list[str] = []
    for model_id, model_records in by_model.items():
        case_ids = {str(record["case_id"]) for record in model_records}
        successes = 0
        for case_id in case_ids:
            case_records = [record for record in model_records if record["case_id"] == case_id]
            last = max(case_records, key=lambda record: int(record["attempt"]))
            if last.get("error_type") is None:
                successes += 1
        latencies = [int(record["latency_ms"]) for record in model_records]
        input_tokens = sum(int(record["input_tokens"]) for record in model_records)
        output_tokens = sum(int(record["output_tokens"]) for record in model_records)
        median_latency = int(median(latencies)) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        lines.extend(
            [
                f"## {model_id}",
                f"- Successful cases: {successes} / {len(case_ids)}",
                f"- Input token total: {input_tokens}",
                f"- Output token total: {output_tokens}",
                f"- Median latency_ms: {median_latency}",
                f"- Max latency_ms: {max_latency}",
                "",
            ]
        )
        error_counts: dict[str, int] = {}
        for record in model_records:
            key = str(record.get("error_type") or "")
            if key:
                error_counts[key] = error_counts.get(key, 0) + 1
        if error_counts:
            error_note = "errors " + ", ".join(
                f"{name}={count}" for name, count in sorted(error_counts.items())
            )
        else:
            error_note = "no recorded errors"
        observations.append(
            f"{model_id} completed {successes}/{len(case_ids)} cases ({error_note}) "
            f"with {input_tokens} input tokens, {output_tokens} output tokens, "
            f"median latency {median_latency} ms and max latency {max_latency} ms."
        )
    lines.append("## Observation")
    lines.append(" ".join(observations))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
