# Claims Intake Service

A service that accepts a first notice of loss, validates it against the policy
master and the rule table in `docs/api-contract.md`, and either records a
notification and issues a claim reference or refuses the submission with a
specific reason.

This README is incomplete. Completing it is part of the Day 4 lab, and the
standard it is graded against is that a person who has never seen this repository
can follow it to a running service.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Your Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests exercise HTTP. |

## Working in this repository

You are inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspaces/claims-intake
```

Dependencies are installed when the container is created. There is no install
step in any assignment this week. If a tool you need is missing, that is a defect
in the image specification and should be reported rather than worked around.

```
uv run pytest
uv run ruff check .
uv run mypy
```

## Data

Everything in `data/` is synthetic and was authored for this program. It contains
no real client data and no named clients.
