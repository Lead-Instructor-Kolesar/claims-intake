"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from claims.models import NotificationRequest, RecordedNotification
from claims.policy_client import PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import ValidationOutcome, submit_notification

app = FastAPI(title="Claims Intake Service")

# Contract section 6: every code this contract defines maps to exactly one status.
_STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "TYPE_NOT_COVERED": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "POLICY_MASTER_TIMEOUT": 504,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 502,
}

# `message` is unstable (contract section 5) and exists only for display.
_MESSAGE_BY_CODE: dict[str, str] = {
    "MALFORMED_REQUEST": "The request body could not be interpreted.",
    "DUPLICATE_NOTIFICATION": "A notification already exists for this policy, loss date, and claim type.",
    "POLICY_NOT_FOUND": "No policy was found with that number.",
    "LOSS_BEFORE_INCEPTION": "Loss date precedes policy inception.",
    "POLICY_CANCELLED": "The policy was cancelled before the loss date.",
    "LOSS_AFTER_EXPIRY": "Loss date falls after policy expiry.",
    "TYPE_NOT_COVERED": "This claim type is not permitted on the policy's product.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not answer in time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_UNPARSABLE": "The policy master returned a response that could not be used.",
}

_REASON_TO_CODE: dict[str, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNREACHABLE",
    "unparsable": "POLICY_MASTER_UNPARSABLE",
}

# Module-level singletons. Overridden per test via `app.dependency_overrides`.
_policy_client = StubPolicyClient()
_repository = NotificationRepository()


def get_policy_client() -> StubPolicyClient:
    return _policy_client


def get_repository() -> NotificationRepository:
    return _repository


def _jsonable(value: Any) -> Any:
    """Make `detail` values safe for `JSONResponse`.

    `outcome.detail` can carry raw `Decimal` and `date` objects. The default JSON
    encoder cannot serialize either, and FastAPI's `jsonable_encoder` would coerce
    `Decimal` to `float`, risking binary-float artifacts on money values. `Decimal`
    becomes its exact string; `date`/`datetime` becomes its ISO form.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _error_response(code: str, status_code: int, detail: dict[str, Any]) -> JSONResponse:
    """Build the three-key error envelope contract section 5 requires."""
    body = {
        "code": code,
        "message": _MESSAGE_BY_CODE.get(code, code),
        "detail": _jsonable(detail),
    }
    return JSONResponse(status_code=status_code, content=body)


@app.post("/notifications")
async def create_notification(
    request: Request,
    policy_client: StubPolicyClient = Depends(get_policy_client),  # noqa: B008
    repository: NotificationRepository = Depends(get_repository),  # noqa: B008
) -> JSONResponse:
    """Parse a first notice of loss, delegate to the service, map the outcome.

    The body is parsed by hand rather than declared as a path-operation parameter
    so that a malformed body produces this contract's 400 envelope instead of
    FastAPI's own `RequestValidationError` shape.
    """
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _error_response("MALFORMED_REQUEST", 400, {})

    try:
        notification = NotificationRequest.model_validate(payload)
    except ValidationError as exc:
        field = str(exc.errors()[0]["loc"][-1])
        return _error_response("MALFORMED_REQUEST", 400, {"field": field})

    try:
        result = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        code = _REASON_TO_CODE[exc.reason]
        return _error_response(
            code,
            _STATUS_BY_CODE[code],
            {"policy_number": exc.policy_number, "reason": exc.reason},
        )

    if isinstance(result, ValidationOutcome):
        assert result.code is not None
        detail = {"rule": result.rule, **result.detail}
        return _error_response(result.code, _STATUS_BY_CODE[result.code], detail)

    recorded: RecordedNotification = result
    return JSONResponse(
        status_code=201,
        content={"claim_reference": recorded.claim_reference, "status": recorded.status},
    )
