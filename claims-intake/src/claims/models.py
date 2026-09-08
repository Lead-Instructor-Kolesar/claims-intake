"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, NewType, Protocol

from pydantic import BaseModel, ConfigDict, Field

from claims.policy_client import PolicyRecord

RuleId = NewType("RuleId", str)
ErrorCode = NewType("ErrorCode", str)

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]
CLAIM_REFERENCE_PATTERN = r"^CLM-\d{4}-\d{6}$"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FnolFields(FrozenModel):
    """Well-formed first notice of loss. Not a recorded claim."""

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None


class DuplicateKey(Protocol):
    """Anything V-6 / WI-0151 can compare. Structural, not a parent class."""

    @property
    def policy_number(self) -> str: ...

    @property
    def loss_date(self) -> date: ...

    @property
    def claim_type(self) -> ClaimType: ...


@dataclass(frozen=True)
class RuleFailure:
    """A rule that did not pass.

    `rule` and `code` are distinct types so a rule identifier cannot be passed
    where an error code is expected.
    """

    rule: RuleId
    code: ErrorCode


class NotificationRequest(FnolFields):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.

    `policy_number` is declared so that the V-1 rule in `service.py` has something
    to read. Every other field, and every constraint on every field including this
    one, is Day 2's work.
    """


class AdmittedNotification(FnolFields):
    """A well-formed FNOL that has already passed every rule.

    Sibling of NotificationRequest, not a subclass of it: after admission the
    object is no longer an inbound payload. The repository will not accept a
    NotificationRequest.
    """

    @classmethod
    def admit(cls, request: NotificationRequest) -> AdmittedNotification:
        return cls.model_validate(request.model_dump())


class Policy(FrozenModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    `cancellation_date` is `None` when the policy was not cancelled (WI-0158 AC-3).
    Callers read `is_cancelled` rather than comparing the date to None.
    """

    policy_number: str = Field(min_length=1)
    product: str = Field(min_length=1)
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal = Field(gt=0, decimal_places=2)
    permitted_claim_types: tuple[ClaimType, ...]

    @classmethod
    def from_record(cls, record: PolicyRecord) -> Policy:
        return cls.model_validate(
            {
                "policy_number": record.policy_number,
                "product": record.product,
                "effective_date": record.effective_date,
                "expiry_date": record.expiry_date,
                "cancellation_date": record.cancellation_date,
                "limit": record.limit,
                "permitted_claim_types": record.permitted_claim_types,
            }
        )

    @property
    def is_cancelled(self) -> bool:
        """WI-0158 AC-3: None means not cancelled. Callers do not compare to None."""
        return self.cancellation_date is not None


class RecordedNotification(FrozenModel):
    """Contract section 3: the identity issued when a notification is written."""

    claim_reference: str = Field(pattern=CLAIM_REFERENCE_PATTERN)
    status: Literal["recorded"]


class ClaimRecord(FrozenModel):
    """A recorded notification: issued identity plus the admitted payload."""

    identity: RecordedNotification
    payload: AdmittedNotification

    @classmethod
    def issue(cls, payload: AdmittedNotification, claim_reference: str) -> ClaimRecord:
        return cls(
            identity=RecordedNotification(
                claim_reference=claim_reference,
                status="recorded",
            ),
            payload=payload,
        )

    @property
    def claim_reference(self) -> str:
        return self.identity.claim_reference

    @property
    def status(self) -> Literal["recorded"]:
        return self.identity.status

    @property
    def policy_number(self) -> str:
        return self.payload.policy_number

    @property
    def loss_date(self) -> date:
        return self.payload.loss_date

    @property
    def claim_type(self) -> ClaimType:
        return self.payload.claim_type

    @property
    def estimated_amount(self) -> Decimal:
        return self.payload.estimated_amount

    @property
    def description(self) -> str | None:
        return self.payload.description

    def matches(self, other: DuplicateKey) -> bool:
        return (
            self.policy_number == other.policy_number
            and self.loss_date == other.loss_date
            and self.claim_type == other.claim_type
        )
