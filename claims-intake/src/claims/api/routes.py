"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Two mappings live here because both are facts about HTTP rather than about
insurance. `STATUS_BY_CODE` is contract section 6. `_jsonable` is the wire
representation of the typed values a refusal was decided on: a `date` becomes an
ISO string and a `Decimal` becomes a string, never a float, because a float would
change a monetary figure on its way to the caller.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from starlette.exceptions import HTTPException as StarletteHTTPException

from claims.models import CLAIM_TYPE_VOCABULARY, ClaimRecord, NotificationRequest
from claims.policy_client import PolicyClient, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import submit_notification

# Contract section 6. Exactly one status per code, in one place, so the HTTP layer
# cannot disagree with the document about what a code means.
STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_JSON": 400,
    "SCHEMA_INVALID": 400,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_CANCELLED": 422,
    "POLICY_MASTER_TIMEOUT": 504,
    "POLICY_MASTER_UNAVAILABLE": 503,
    "POLICY_MASTER_INVALID_RESPONSE": 502,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "METHOD_NOT_ALLOWED": 405,
    "NOT_FOUND": 404,
    "INTERNAL_ERROR": 500,
}

# Contract section 6.3. The three dependency failures differ in what operations
# should do next, which is why they are three codes and not one.
_CODE_BY_LOOKUP_REASON: dict[str, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNAVAILABLE",
    "unparsable": "POLICY_MASTER_INVALID_RESPONSE",
}

# Section 6.3 states these values directly. `unreachable` is retryable even though
# an immediate retry is not worth making: the question `retryable` answers is
# whether the caller may send the identical payload again at all, and only a policy
# master that broke its own response shape will still be broken on the next attempt.
_RETRYABLE_BY_LOOKUP_REASON: dict[str, bool] = {
    "timeout": True,
    "unreachable": True,
    "unparsable": False,
}

_CODE_BY_HTTP_STATUS: dict[int, str] = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    415: "UNSUPPORTED_MEDIA_TYPE",
}

# Section 2.1 and 6.4. The endpoint accepts one method and one media type, and both
# have to be reportable in `detail`, so neither is written as a literal twice.
_ALLOWED_METHODS: tuple[str, ...] = ("POST",)
_EXPECTED_MEDIA_TYPE = "application/json"


def _jsonable(value: object) -> Any:
    """Render a decision value for the wire.

    Money becomes a string rather than a float: `Decimal("3499.99")` through a
    float is no longer the figure the caller sent, and `estimated_amount` is the
    value V-4 compared and downstream reserving reads.
    """
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _wire_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in detail.items()}


def _correlation_id() -> str:
    """An opaque identifier that ties a response to a line in our logs."""
    return uuid4().hex.upper()


def _message_for(code: str, detail: dict[str, Any]) -> str:
    """Prose for a human reader.

    Section 5.2: `message` is not a promise. It exists to be logged and shown to a
    person, and a caller that asserts on it has built on something this contract
    does not maintain. Everything a caller decides on is in `code`, the status, and
    the documented keys of `detail`.
    """
    messages: dict[str, str] = {
        "MALFORMED_JSON": "The request body could not be read as a JSON object.",
        "POLICY_NOT_FOUND": (
            f"No policy was found with number {detail.get('policy_number')}."
        ),
        "LOSS_BEFORE_INCEPTION": (
            f"Loss date {detail.get('loss_date')} is before the policy effective date "
            f"{detail.get('effective_date')}."
        ),
        "LOSS_AFTER_EXPIRY": (
            f"Loss date {detail.get('loss_date')} is after the policy expiry date "
            f"{detail.get('expiry_date')}."
        ),
        "AMOUNT_EXCEEDS_LIMIT": (
            f"Estimated amount {detail.get('estimated_amount')} exceeds the policy limit "
            f"{detail.get('limit')}."
        ),
        "TYPE_NOT_COVERED": (
            f"Claim type {detail.get('claim_type')} is not permitted on product "
            f"{detail.get('product')}."
        ),
        "DUPLICATE_NOTIFICATION": (
            f"This loss is already recorded as {detail.get('claim_reference')}."
        ),
        "POLICY_CANCELLED": (
            f"Cover ended when the policy was cancelled with effect from "
            f"{detail.get('cancellation_date')}."
        ),
        "POLICY_MASTER_TIMEOUT": "The policy master did not respond in time. Please retry.",
        "POLICY_MASTER_UNAVAILABLE": "The policy master could not be reached.",
        "POLICY_MASTER_INVALID_RESPONSE": (
            "The policy master returned a response this service cannot read."
        ),
        "UNSUPPORTED_MEDIA_TYPE": (
            f"This endpoint accepts {detail.get('expected')} only, and the request "
            f"carried {detail.get('received')}."
        ),
        "METHOD_NOT_ALLOWED": (
            f"This endpoint accepts {', '.join(_ALLOWED_METHODS)} only, and the request "
            f"used {detail.get('method')}."
        ),
        "NOT_FOUND": "This service defines no resource at that path.",
        "INTERNAL_ERROR": "The service failed to handle this request.",
    }
    if code == "SCHEMA_INVALID":
        violations = detail.get("violations", [])
        count = len(violations) if isinstance(violations, Sequence) else 0
        field_word = "field is" if count == 1 else "fields are"
        return f"The request could not be interpreted. {count} {field_word} invalid."
    return messages.get(code, "The request was refused.")


def _error_response(
    code: str,
    detail: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the section 5.1 envelope.

    There is no `status` key in the body. The status appears in the status line and
    nowhere else, so the two cannot disagree.
    """
    wire_detail = _wire_detail(detail)
    return JSONResponse(
        status_code=STATUS_BY_CODE[code],
        content={
            "code": code,
            "message": _message_for(code, wire_detail),
            "detail": wire_detail,
        },
        headers=headers,
    )


def _unsupported_media_type_response(received: str | None) -> JSONResponse:
    """Section 6.4. `detail` names what arrived and what the endpoint accepts."""
    return _error_response(
        "UNSUPPORTED_MEDIA_TYPE",
        {"received": received, "expected": _EXPECTED_MEDIA_TYPE},
    )


def _method_not_allowed_response(method: str) -> JSONResponse:
    """Section 6.4, including the `Allow` header the method requires."""
    return _error_response(
        "METHOD_NOT_ALLOWED",
        {"method": method, "allowed": list(_ALLOWED_METHODS)},
        headers={"Allow": ", ".join(_ALLOWED_METHODS)},
    )


def _dependency_error_response(failure: PolicyLookupFailed) -> JSONResponse:
    """Section 6.3. The caller sent a valid request, so this is ours and it is 5xx."""
    return _error_response(
        _CODE_BY_LOOKUP_REASON[failure.reason],
        {
            "dependency": "policy_master",
            "reason": failure.reason,
            "retryable": _RETRYABLE_BY_LOOKUP_REASON[failure.reason],
            "correlation_id": _correlation_id(),
        },
    )


def _violation(error: ErrorDetails) -> dict[str, str]:
    """Describe one V-0 violation as `{ field, problem }` (section 4.3).

    The field is named so a developer can go and read it, which is the whole
    difference between SCHEMA_INVALID and MALFORMED_JSON.
    """
    location = error["loc"]
    field = str(location[0]) if location else "body"
    error_type = error["type"]
    if error_type == "missing" or error["input"] is None:
        # Section 4.3 violation 1: a required field present with the value null is
        # the same violation as an absent one.
        return {"field": field, "problem": "required field absent"}
    if error_type == "extra_forbidden":
        return {"field": field, "problem": "field is not defined by this contract"}
    if error_type == "literal_error":
        permitted = ", ".join(CLAIM_TYPE_VOCABULARY)
        return {
            "field": field,
            "problem": f"value {error['input']!r} is not one of: {permitted}",
        }
    if error_type.startswith("date"):
        return {
            "field": field,
            "problem": "value is not a calendar date of the form YYYY-MM-DD",
        }
    if error_type == "decimal_max_places":
        return {"field": field, "problem": "value carries more than two decimal places"}
    if error_type == "greater_than":
        return {"field": field, "problem": "value must be greater than zero"}
    # Pydantic prefixes a validator's own message with "Value error, ". That prefix
    # names the library that refused rather than the thing the caller got wrong, and
    # `problem` is read by a developer fixing a payload.
    return {"field": field, "problem": error["msg"].removeprefix("Value error, ")}


def _violations(error: ValidationError) -> list[dict[str, str]]:
    """Every violation in the request, reported together (section 4.1, the V-0 exception)."""
    return [_violation(entry) for entry in error.errors()]


def _is_json_request(content_type: str | None) -> bool:
    if content_type is None:
        return False
    return content_type.split(";")[0].strip().lower() == "application/json"


def create_app(
    policy_client: PolicyClient | None = None,
    repository: NotificationRepository | None = None,
) -> FastAPI:
    """Build the application over a policy master and a store.

    Both dependencies are arguments so a test can supply a stub that fails on
    demand and a store that starts empty. Nothing here reaches for a global.
    """
    app = FastAPI(title="Claims Intake Service")
    client = policy_client if policy_client is not None else StubPolicyClient()
    store = repository if repository is not None else NotificationRepository()

    @app.post("/notifications")
    async def create_notification(request: Request) -> Response:
        """Accept a first notice of loss (contract sections 2, 3, 5 and 6)."""
        received = request.headers.get("content-type")
        if not _is_json_request(received):
            return _unsupported_media_type_response(received)

        try:
            payload: object = json.loads(await request.body())
        except json.JSONDecodeError:
            return _error_response("MALFORMED_JSON", {})
        if not isinstance(payload, dict):
            return _error_response("MALFORMED_JSON", {})

        try:
            notification = NotificationRequest.model_validate(payload)
        except ValidationError as invalid:
            return _error_response("SCHEMA_INVALID", {"violations": _violations(invalid)})

        try:
            outcome = submit_notification(notification, client, store)
        except PolicyLookupFailed as failure:
            return _dependency_error_response(failure)

        if isinstance(outcome, ClaimRecord):
            return JSONResponse(
                status_code=201,
                content={
                    "claim_reference": outcome.claim_reference,
                    "status": "recorded",
                },
            )

        if outcome.code is None:
            raise RuntimeError("a refusal must name a contract code")
        return _error_response(outcome.code, outcome.detail)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: Exception) -> Response:
        """Keep transport failures inside the section 5.1 envelope.

        Section 4.1: these are decided before stage 0, so no body is read here.
        """
        status = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
        if status == 405:
            return _method_not_allowed_response(request.method)
        if status == 415:
            return _unsupported_media_type_response(request.headers.get("content-type"))
        return _error_response(_CODE_BY_HTTP_STATUS.get(status, "INTERNAL_ERROR"), {})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        """Section 6.4. Nothing escapes the envelope, and nothing we did not anticipate
        is described to the caller beyond an identifier operations can trace.
        """
        return _error_response("INTERNAL_ERROR", {"correlation_id": _correlation_id()})

    return app


app = create_app()
