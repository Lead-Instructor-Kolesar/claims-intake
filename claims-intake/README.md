# Claims Intake Service

A service that accepts a first notice of loss, validates it against the policy
master and the rule table in `docs/api-contract.md`, and either records a
notification and issues a claim reference or refuses the submission with a
specific reason.

`docs/api-contract.md` is the authority on what the service accepts, returns, and
refuses. Where this code and that document disagree, the document is correct and
the code is a defect.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | The classification of the edge payloads and the reconciliation notes. |
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

All three must exit zero before a change is committed.

## Running the service

```
uv run uvicorn claims.api.routes:app --reload
```

The service listens on `http://127.0.0.1:8000`. It reads policies from
`data/policies.json` through `StubPolicyClient` and stores notifications in
memory, so restarting it discards every recorded notification and the claim
reference sequence starts again.

Submit a notification:

```
curl -i -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction."
      }'
```

```
201 Created

{"claim_reference": "CLM-2026-000001", "status": "recorded"}
```

Send it a second time and the duplicate rule refuses it with the reference of the
record that already exists:

```
409 Conflict

{
  "code": "DUPLICATE_NOTIFICATION",
  "message": "This loss is already recorded as CLM-2026-000001.",
  "detail": {
    "policy_number": "MOT-4471",
    "loss_date": "2026-04-02",
    "claim_type": "collision",
    "claim_reference": "CLM-2026-000001"
  }
}
```

Every response that is not `201` carries that three-key envelope. Branch on
`code` and on the HTTP status; do not branch on `message`, whose wording the
contract does not maintain (section 5.2).

## How a request moves through the code

Each module owns one decision, and the boundaries between them are the point.

| Module | What it decides | What it must not do |
| --- | --- | --- |
| `models.py` | Whether a payload is a well-formed request at all | Read a policy, or decide admissibility |
| `policy_client.py` | What the policy master holds, and how it failed | Interpret a policy against a request |
| `service.py` | Which rule refuses this notification, and in what order | Know about HTTP, or know where records are stored |
| `repository.py` | What has been recorded, and what reference it carries | Evaluate a rule |
| `api/routes.py` | Which status a code maps to, and the wire shape | Hold rule logic |

`models.py` is the only module that accepts a raw payload dictionary. Everything
after it works with typed objects, which is why `loss_date` is a `date` and
`estimated_amount` is a `Decimal` everywhere, and never a string or a float.

A refused notification is never recorded, so there is no state between "recorded
with a reference" and "does not exist" (contract section 3).

## Working on the rules

The rule table is contract section 4.2 and the evaluation order is section 4.1.
The order is caller-visible, because a notification can violate several rules and
the caller is told about exactly one. In the code that order lives in
`_POLICY_RULE_STAGES` in `service.py` and nowhere else.

Adding a rule means, in this order: amend `docs/api-contract.md` with the rule,
its code, its status, and the stage it belongs to; add a failing test that names
the guarantee; then implement it. A rule that appears in the code before it
appears in the contract is a rule no caller was told about.

## Data

Everything in `data/` is synthetic and was authored for this program. It contains
no real client data and no named clients.

`fnol_valid.json`, `fnol_invalid.json`, and `fnol_edge.json` carry identifiers
such as `VALID-01` and `EDGE-07`. Those identifiers are classified in
`docs/payload-triage.md` and the tests index by them, so a failing test names the
payload and the rule that decided it.
