"""Request and policy shapes from contract sections 2 and 3.

A payload that fails these models is uninterpretable (W-*). Whether the
policy exists or the loss is covered is a rule and belongs in service.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

RuleIdentifier = Literal[
    "W-1",
    "W-2",
    "W-3",
    "V-1",
    "V-2",
    "V-3",
    "V-4",
    "V-5",
    "V-6",
    "V-7",
]

ErrorCode = Literal[
    "MALFORMED_REQUEST",
    "DUPLICATE_NOTIFICATION",
    "POLICY_NOT_FOUND",
    "LOSS_BEFORE_INCEPTION",
    "LOSS_AFTER_EXPIRY",
    "AMOUNT_EXCEEDS_LIMIT",
    "TYPE_NOT_COVERED",
    "POLICY_CANCELLED",
]

CLAIM_REFERENCE_PATTERN = r"^CLM-\d{4}-\d{6}$"


def _exactly_two_decimal_places(value: object) -> object:
    # W-3 / section 2.2: Field(decimal_places=2) would pad 3499 to 3499.00.
    if isinstance(value, bool):
        raise TypeError("money values are not booleans")
    if isinstance(value, int):
        value = Decimal(value)
    if isinstance(value, Decimal):
        if value.as_tuple().exponent != -2:
            raise ValueError("decimal scale must be exactly 2")
        return value
    if isinstance(value, str):
        if "." not in value:
            raise ValueError("decimal scale must be exactly 2")
        fraction = value.rsplit(".", 1)[1]
        if len(fraction) != 2 or not fraction.isdigit():
            raise ValueError("decimal scale must be exactly 2")
        return value
    return value


UsdToTheCent = Annotated[
    Decimal,
    BeforeValidator(_exactly_two_decimal_places),
    Field(gt=0, max_digits=16),
]


class NotificationRequest(BaseModel):
    # Section 2.2: a misspelled key must not be ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_number: Annotated[str, StringConstraints(min_length=1)]
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdToTheCent
    description: str | None = None


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_number: Annotated[str, StringConstraints(min_length=1)]
    product: str
    effective_date: date
    expiry_date: date
    # WI-0158 AC-3: null means not cancelled. Comparing without handling
    # None is a type error, not a missed branch.
    cancellation_date: date | None
    limit: UsdToTheCent
    permitted_claim_types: tuple[ClaimType, ...]


@dataclass(frozen=True)
class RuleFailure:
    # Separate Literals so a rule id cannot be passed where a section-6 code is expected.
    rule: RuleIdentifier
    code: ErrorCode


class RecordedNotification(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: Annotated[str, StringConstraints(pattern=CLAIM_REFERENCE_PATTERN)]
    policy_number: Annotated[str, StringConstraints(min_length=1)]
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdToTheCent
    description: str | None = None

    @classmethod
    def from_accepted(
        cls, notification: NotificationRequest, claim_reference: str
    ) -> RecordedNotification:
        return cls(
            claim_reference=claim_reference,
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
