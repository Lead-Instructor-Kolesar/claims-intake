"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from claims.models import NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import submit_notification

app = FastAPI(title="Claims Intake Service")

# Process-wide defaults so duplicate detection (V-6) sees prior records.
# Tests replace these through FastAPI dependency overrides.
_policy_client: PolicyClient = StubPolicyClient()
_repository = NotificationRepository()

# Contract section 6. The only map from code to status. Not a rule table.
STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "POLICY_CANCELLED": 422,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 502,
    "POLICY_MASTER_TIMEOUT": 504,
}

_MESSAGE_BY_CODE: dict[str, str] = {
    "MALFORMED_REQUEST": "The request body could not be interpreted.",
    "DUPLICATE_NOTIFICATION": "A notification for this loss is already recorded.",
    "POLICY_NOT_FOUND": "No policy exists for the submitted policy number.",
    "LOSS_BEFORE_INCEPTION": "The loss date is before the policy effective date.",
    "LOSS_AFTER_EXPIRY": "The loss date is after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not covered on this policy.",
    "POLICY_CANCELLED": "The policy was cancelled on or before the loss date.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not respond in time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be contacted.",
    "POLICY_MASTER_UNPARSABLE": "The policy master response could not be parsed as a policy record.",
}

_LOOKUP: dict[LookupFailureReason, tuple[str, str]] = {
    "timeout": ("POLICY_MASTER_TIMEOUT", "timeout"),
    "unreachable": ("POLICY_MASTER_UNREACHABLE", "unreachable"),
    "unparsable": ("POLICY_MASTER_UNPARSABLE", "unparsable"),
}


def get_policy_client() -> PolicyClient:
    return _policy_client


def get_repository() -> NotificationRepository:
    return _repository


def _envelope(code: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "message": _MESSAGE_BY_CODE[code],
        "detail": detail,
    }


def _json(status: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def _malformed_reason(err: dict[str, Any]) -> str:
    err_type = str(err.get("type", ""))
    msg = str(err.get("msg", "")).lower()
    if err_type == "json_invalid" or "json" in err_type:
        return "invalid_json"
    if err_type == "extra_forbidden":
        return "unexpected_field"
    if err_type == "missing":
        return "required_field_absent"
    if err_type == "string_too_short":
        return "empty_value"
    if err_type in {"literal_error", "enum"}:
        return "not_in_vocabulary"
    if err_type in {"greater_than", "greater_than_equal"}:
        return "not_greater_than_zero"
    if "decimal scale" in msg or "scale" in msg:
        return "invalid_decimal_scale"
    if err_type.startswith("date_") or "date" in msg:
        return "invalid_date"
    if "type" in err_type or "boolean" in msg:
        return "wrong_type"
    return "wrong_type"


def _malformed_field(err: dict[str, Any]) -> str:
    loc = err.get("loc", ())
    parts = [str(part) for part in loc if part not in {"body", "request"}]
    if not parts:
        return ""
    return parts[0]


@app.exception_handler(RequestValidationError)
async def malformed_request(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    if not errors:
        field, reason = "", "invalid_json"
    else:
        err = errors[0]
        field = _malformed_field(err)
        reason = _malformed_reason(err)
        if reason == "invalid_json":
            field = ""
    return _json(400, _envelope("MALFORMED_REQUEST", {"field": field, "reason": reason}))


@app.post("/notifications")
def post_notification(
    notification: NotificationRequest,
    policy_client: Annotated[PolicyClient, Depends(get_policy_client)],
    repository: Annotated[NotificationRepository, Depends(get_repository)],
) -> JSONResponse:
    try:
        outcome = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        code, reason = _LOOKUP[exc.reason]
        return _json(
            STATUS_BY_CODE[code],
            _envelope(code, {"dependency": "policy_master", "reason": reason}),
        )
    if outcome.passed:
        return _json(
            201,
            {
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )
    code = outcome.code or "MALFORMED_REQUEST"
    return _json(STATUS_BY_CODE[code], _envelope(code, dict(outcome.detail)))
