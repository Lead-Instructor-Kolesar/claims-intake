# Claims Intake Service

This service accepts a first notice of loss, checks it against the policy
master and the rules in `docs/api-contract.md`, and either records the
notification or refuses it with a specific code.

The only HTTP operation is `POST /notifications`. A valid notification returns
`201` with a `claim_reference` and `status: recorded`. Every refusal uses the
error envelope in contract section 5 (`code`, `message`, `detail`) and the
status in section 6.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. |
| `docs/requirements-brief.md` | Work items and acceptance criteria. |
| `docs/payload-triage.md` | Classification of the edge payloads. |
| `data/` | Synthetic policies and sample notification bodies. |
| `src/claims/` | Models, repository, rules, and HTTP routes. |
| `tests/` | Unit tests for objects and rules. Integration tests call HTTP. |
| `Dockerfile` | Image that runs the service. |

## Working in this repository

You are already in the lab Linux container. Confirm:

```
uname -sm     # often Linux aarch64
pwd           # /workspaces/claims-intake
```

Python, `uv`, and project dependencies are already here. Do not install
anything. If a tool is missing, report it; do not work around it.

## Run the service

From this folder:

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

Submit a notification:

```
curl -s -X POST http://127.0.0.1:8000/notifications \
  -H "Content-Type: application/json" \
  -d '{"policy_number":"MOT-4471","loss_date":"2026-04-02","claim_type":"collision","estimated_amount":"4200.00"}'
```

A valid body returns `201` and a `claim_reference` such as `CLM-2026-000001`.
Sending the same policy, loss date, and claim type again returns `409`
(`DUPLICATE_NOTIFICATION`) until you restart the process (storage is in memory).

Interactive docs: http://127.0.0.1:8000/docs

Sample bodies: `data/fnol_valid.json`, `data/fnol_invalid.json`,
`data/fnol_edge.json`.

## Run the tests

From the same folder:

```
uv run pytest
uv run ruff check .
uv run mypy src tests
```

HTTP tests only: `uv run pytest tests/integration`.

## Container image

This container does not include the `docker` CLI. That is a gap in the lab
image. Build on a machine that already has Docker (for example your laptop).
Do not install Docker here.

The `Dockerfile` copies `src/` and `data/`, installs from `uv.lock` with
`uv sync --frozen --no-dev`, and starts uvicorn on port 8000.

On a machine that has Docker, from this folder:

```
docker buildx build --platform linux/amd64 -t claims-intake .
docker run --rm -p 8000:8000 claims-intake
```

Then use the same `curl` against `http://127.0.0.1:8000/notifications`.

### Why `--platform linux/amd64`

Docker defaults to the CPU of the machine doing the build. This lab reports
`Linux aarch64` (ARM). A Mac with Apple silicon is ARM as well. The machines
this image is meant to run on — typical cloud VMs and many CI runners — are
`linux/amd64` (Intel/AMD 64-bit).

Without the flag you get an ARM image. On an amd64 host that image will not
run, or it will fail in a way that looks like an application bug. The flag
does not “enable Docker.” It builds for the **target** CPU, not the CPU of
the laptop or container you are sitting in.

## Data

Everything in `data/` is synthetic. There is no real client data and no named
clients.
