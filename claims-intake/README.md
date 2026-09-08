# Claims Intake Service

A service that accepts a first notice of loss, validates it against the policy
master and the rule table in `docs/api-contract.md`, and either records a
notification and issues a claim reference or refuses the submission with a
specific reason.

**Current state.** Day 2 is in place: request/policy/recorded models and an
in-memory notification repository. Day 3 (rule evaluation) and Day 4 (HTTP
error envelope) are still stubs. Completing this README for a person who has
never seen the repo is part of the Day 4 lab; this file is enough to run what
exists today.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/models.py` | Shape of the request, policy, and recorded notification. |
| `src/claims/repository.py` | In-memory store and claim-reference issuance. |
| `src/claims/service.py` | Rule evaluation. Day 3. V-1 only so far. |
| `src/claims/api/routes.py` | HTTP surface. Day 4. FastAPI app, no routes yet. |
| `src/claims/policy_client.py` | Stub policy master over `data/policies.json`. Ships complete. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests exercise HTTP. |

## Working in this repository

You are inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspace/claims-intake/claims-intake
```

Dependencies live in `.venv`. If `uv` is not on `PATH`:

```
export PATH="/root/.local/bin:$PATH"
```

Or activate the venv and call the tools directly:

```
source .venv/bin/activate
pytest
ruff check .
mypy
```

With `uv` available:

```
uv run pytest
uv run ruff check .
uv run mypy
```

`mypy` is configured `strict = true` in `pyproject.toml`. A clean run means the
annotations currently match the code.

Coverage (needs `pytest-cov` in the venv):

```
pytest --cov=src/claims --cov-report=term-missing
```

`.venv` has no `pip` binary. Install extra tools with `uv pip install …`, not
`.venv/bin/pip`.

## HTTP / Swagger

The FastAPI app exists but exposes no endpoints yet. After Day 4 wires
`POST /notifications`, start it with:

```
uv run uvicorn claims.api.routes:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI will be at `http://localhost:8000/docs`. Until that route exists,
`/docs` is an empty API.

## Data

Everything in `data/` is synthetic and was authored for this program. It contains
no real client data and no named clients.

| File | What it is |
| --- | --- |
| `data/policies.json` | Stub policy master. |
| `data/fnol_valid.json` | Payloads that should parse as `NotificationRequest`. |
| `data/fnol_invalid.json` | Well-formed payloads that should fail a rule. |
| `data/fnol_edge.json` | Boundary cases. EDGE-08, EDGE-11, EDGE-12 fail at the model. |
