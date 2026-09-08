"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


class RuleId(StrEnum):
    """Identifiers from the contract rule table. Distinct from `ErrorCode`."""

    V1 = "V-1"
    V2 = "V-2"
    V3 = "V-3"
    V4 = "V-4"
    V5 = "V-5"
    V6 = "V-6"
    V7 = "V-7"


class ErrorCode(StrEnum):
    """Stable codes from contract section 6. Distinct from `RuleId`."""

    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_CANCELLED = "POLICY_CANCELLED"
    LOSS_BEFORE_INCEPTION = "LOSS_BEFORE_INCEPTION"
    LOSS_AFTER_EXPIRY = "LOSS_AFTER_EXPIRY"
    AMOUNT_EXCEEDS_LIMIT = "AMOUNT_EXCEEDS_LIMIT"
    TYPE_NOT_COVERED = "TYPE_NOT_COVERED"
    DUPLICATE_NOTIFICATION = "DUPLICATE_NOTIFICATION"
    POLICY_MASTER_UNAVAILABLE = "POLICY_MASTER_UNAVAILABLE"
    POLICY_MASTER_TIMEOUT = "POLICY_MASTER_TIMEOUT"
    POLICY_MASTER_INVALID_RESPONSE = "POLICY_MASTER_INVALID_RESPONSE"


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Annotated[Decimal, Field(gt=0)]
    description: str | None = None

    @field_validator("loss_date", mode="before")
    @classmethod
    def loss_date_is_calendar_date(cls, value: object) -> object:
        """Contract section 2.2: calendar date, `YYYY-MM-DD`. Not a datetime."""
        if isinstance(value, datetime):
            raise PydanticCustomError(
                "date_type",
                "loss_date must be a calendar date YYYY-MM-DD",
            )
        if isinstance(value, date):
            return value
        if isinstance(value, str) and ISO_DATE.fullmatch(value):
            return value
        raise ValueError("loss_date must be a calendar date YYYY-MM-DD")

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def estimated_amount_is_decimal(cls, value: object) -> object:
        """Reject types that cannot be a USD amount as this contract defines it."""
        if isinstance(value, (bool, float)):
            raise PydanticCustomError(
                "decimal_type",
                "estimated_amount must be a decimal",
            )
        return value

    @field_validator("estimated_amount")
    @classmethod
    def estimated_amount_has_at_most_two_places(cls, value: Decimal) -> Decimal:
        """Section 4.1: more than two decimal places is uninterpretable, not rounded."""
        if not value.is_finite():
            raise ValueError("estimated_amount must be a finite decimal")
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("estimated_amount must have at most two decimal places")
        return value


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    `cancellation_date` is `date | None` with no default. Omitting it is a
    construction error, so WI-0158 AC-3 cannot be satisfied by forgetting to
    pass the field. A null value is the only representation of "not cancelled".
    """

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    policy_number: str
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal
    permitted_claim_types: tuple[str, ...]


class RuleFailure(BaseModel):
    """A rule that a notification failed, with the code that failure produces.

    `rule` and `code` are different types so a rule identifier cannot be passed
    where an error code is expected.
    """

    model_config = ConfigDict(frozen=True)

    rule: RuleId
    code: ErrorCode


class RecordedNotification(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: str = Field(pattern=CLAIM_REFERENCE_PATTERN.pattern)
    policy_number: str
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None
