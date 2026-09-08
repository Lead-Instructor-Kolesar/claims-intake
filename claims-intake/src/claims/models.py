"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, NewType

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic_core import PydanticCustomError

# Contract §2.3 vocabulary. Membership here is structural: `flood` dies at
# parse as MALFORMED_REQUEST (400). Whether a product permits a vocabulary
# type is V-5 (TYPE_NOT_COVERED, 422) and lives in service.py (Day 3).
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

# Distinct NewTypes so a rule identifier cannot be passed where an error code
# is expected. Two `str` fields would type-check a swapped construction.
RuleIdentifier = NewType("RuleIdentifier", str)
ErrorCode = NewType("ErrorCode", str)


def _reject_float_money(value: object) -> object:
    # Contract §2.2: money is decimal USD. JSON numbers become float, and float
    # cannot represent two-place decimal exactly. Coerce from str and int (the
    # data files use strings). Full strict mode would also reject those strings.
    if isinstance(value, float):
        # PydanticCustomError becomes ValidationError. TypeError leaks out of
        # BeforeValidator; ValueError trips ruff TRY004. This is the typed refusal.
        raise PydanticCustomError(
            "float_money",
            "money values must be exact decimals, not float",
        )
    return value


def _require_exactly_two_decimal_places(value: Decimal) -> Decimal:
    # Contract §2.2 and §4: exactly two decimal places (`invalid_scale`).
    # Pydantic `decimal_places=2` is a maximum; `10.5` and `10` would otherwise pass.
    exponent = value.as_tuple().exponent
    if exponent != -2:
        raise PydanticCustomError(
            "invalid_scale",
            "money values must have exactly two decimal places",
        )
    return value


UsdAmount = Annotated[
    Decimal,
    BeforeValidator(_reject_float_money),
    Field(gt=0, decimal_places=2),
    AfterValidator(_require_exactly_two_decimal_places),
]
# Policy.limit is already Decimal from the master. Reject float so V-4 cannot
# rest on binary money. Scale and positivity are not section 2.2 constraints
# on the policy record.
PolicyLimit = Annotated[Decimal, BeforeValidator(_reject_float_money)]


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.
    """

    # Contract §2.2: a misspelled field accepted-and-ignored would record data
    # the caller did not send.
    model_config = ConfigDict(extra="forbid")

    policy_number: Annotated[str, Field(min_length=1)]
    # date, not str, so V-2/V-3 compare two dates rather than two strings.
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    # Contract §2.2: the only optional field. Absent and null are equivalent;
    # defaulting to None does not invent caller data.
    description: str | None = None


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: Annotated[str, Field(min_length=1)]
    product: str
    effective_date: date
    expiry_date: date
    # WI-0158 AC-3: required-but-nullable. No `= None` default, so construction
    # cannot silently treat a forgotten cancellation as "not cancelled".
    # `date | None` makes an unguarded comparison fail type checking.
    cancellation_date: date | None
    limit: PolicyLimit
    permitted_claim_types: tuple[ClaimType, ...]


@dataclass(frozen=True)
class RuleFailure:
    """One rule refusal, with the identifier and the contract code kept apart."""

    rule: RuleIdentifier
    code: ErrorCode


class ClaimRecord(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format. Duplicate detection (WI-0151 AC-1) is a
    query against recorded notifications, so this type holds the three-field
    composite as well as the amount and description as written.
    """

    model_config = ConfigDict(extra="forbid")

    claim_reference: Annotated[str, Field(pattern=r"^CLM-\d{4}-\d{6}$")]
    policy_number: Annotated[str, Field(min_length=1)]
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    description: str | None


# Day 3 stub in service.py still imports this name.
RecordedNotification = ClaimRecord
