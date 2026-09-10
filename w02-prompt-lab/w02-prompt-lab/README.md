# Week 2 Prompt Lab

This repository contains the Week 2 local-model prompt engineering lab.

For this version of the lab, models run locally through **Ollama** rather than through Anthropic or Azure OpenAI. Day 1 uses **Mistral**. **Qwen** is also installed for later model-comparison work.

## Architecture

The Python code runs inside the devcontainer. Ollama runs on the host Mac.

```text
Python in devcontainer
        |
        v
http://host.docker.internal:11434
        |
        v
Ollama on macOS
        |
        +-- mistral:7b
        |
        +-- qwen3:8b
```

## Before You Start

Make sure you have:

- Docker Desktop
- VS Code
- the VS Code Dev Containers extension
- Ollama

Start Docker Desktop and Ollama before opening the lab.

On the **host Mac**, pull the two local models:

```bash
ollama pull mistral:7b
ollama pull qwen3:8b
```

Verify that Ollama is running:

```bash
curl http://localhost:11434/api/tags
```

You should see the installed models in the response.

## Open the Repository in the Devcontainer

1. Open `w02-prompt-lab` in VS Code.
2. Run **Dev Containers: Reopen in Container** from the Command Palette.
3. Wait for the container setup to finish.
4. From the terminal inside the devcontainer, run:

```bash
uv sync --frozen
```

Then verify that the devcontainer can reach Ollama running on the Mac:

```bash
curl http://host.docker.internal:11434/api/tags
```

If that command cannot reach Ollama, stop and resolve the environment issue before beginning the assignment.

## Day 1

The Day 1 assignment is here:

```text
assignments/W02_Day1_Assignment_LOCAL.md
```

Day 1 uses **Mistral through Ollama** to instrument a real model call.

The starter material includes:

```text
cases/extraction.jsonl
scripts/raw_call_example.py
src/promptlab/config.py
src/promptlab/errors.py
src/promptlab/usage.py
src/promptlab/prompts/baseline.v0.md
tests/test_usage_contract.py
```

`usage.py` is intentionally incomplete. You will implement it as part of the assignment.

## Verify the Local Model Call

Before writing your Day 1 implementation, run the supplied example:

```bash
uv run python scripts/raw_call_example.py
```

A successful run should print:

- model response text
- input token count
- output token count
- stop reason

This proves that Python inside the devcontainer can make a real call to the local Mistral model.

## Day 1 Student Work

You will implement or create:

```text
src/promptlab/usage.py
src/promptlab/day1.py
docs/day1-run.jsonl
docs/day1-observations.md
```

Follow the assignment for the exact contract and acceptance criteria.

## Quality Checks

Run these from the repository root inside the devcontainer:

```bash
uv run pytest tests/test_usage_contract.py
uv run ruff check src/promptlab/usage.py src/promptlab/day1.py
uv run mypy src/promptlab/usage.py src/promptlab/day1.py
```

The contract test does not make a network call.

## Local Cost

Ollama runs the models locally, so this lab records a provider/API charge of:

```text
$0.00
```

You will still record token counts and latency. Those measurements are real and are used to understand how workload changes with document size.

Do not invent a cloud-model price for Mistral or Qwen in this local lab.

## Important Repository Rules

- Do not hardcode model identifiers in your Day 1 call site; read them from configuration.
- Do not commit `.env`.
- Do not commit the entire `runs/` directory.
- Do not modify supplied contract tests to make your implementation pass.
- Keep run records append-only.
- Use timezone-aware UTC timestamps.
- Day 1 uses Mistral only; Qwen is reserved for later model-comparison work.

## Repository Layout

```text
w02-prompt-lab/
├── assignments/
│   └── W02_Day1_Assignment_LOCAL.md
├── cases/
│   ├── extraction.jsonl
│   ├── summarization.jsonl
│   └── triage.jsonl
├── docs/
├── reports/
├── scripts/
│   └── raw_call_example.py
├── src/
│   └── promptlab/
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── usage.py
│       └── prompts/
│           └── baseline.v0.md
├── tests/
│   └── test_usage_contract.py
├── pyproject.toml
└── uv.lock
```

Start with the Day 1 assignment and the supplied raw Ollama call example.
