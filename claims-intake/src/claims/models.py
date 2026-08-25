"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictStr,
)

from claims.policy_client import PolicyRecord

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

# Section 2.3 fixes the vocabulary. Derived from the type so the two can never
# drift: anything that reports the permitted values reads this.
CLAIM_TYPE_VOCABULARY: tuple[ClaimType, ...] = get_args(ClaimType)

# Section 4: the rule identifiers. Section 4.1 is explicit that these are
# permanent labels and carry no information about evaluation order.
RuleId = Literal["V-0", "V-1", "V-2", "V-3", "V-4", "V-5", "V-6", "V-7"]

# Section 6: every code the service can return. `RuleId` and `ErrorCode` are
# separate types rather than both being `str` so that the type checker refuses a
# rule identifier where a code is expected, which is the whole reason RuleFailure
# has two fields instead of one.
ErrorCode = Literal[
    "MALFORMED_JSON",
    "SCHEMA_INVALID",
    "POLICY_NOT_FOUND",
    "LOSS_BEFORE_INCEPTION",
    "LOSS_AFTER_EXPIRY",
    "AMOUNT_EXCEEDS_LIMIT",
    "TYPE_NOT_COVERED",
    "DUPLICATE_NOTIFICATION",
    "POLICY_CANCELLED",
    "POLICY_MASTER_TIMEOUT",
    "POLICY_MASTER_UNAVAILABLE",
    "POLICY_MASTER_INVALID_RESPONSE",
    "UNSUPPORTED_MEDIA_TYPE",
    "METHOD_NOT_ALLOWED",
    "NOT_FOUND",
    "INTERNAL_ERROR",
]

CONTRACT_ERROR_CODES: tuple[ErrorCode, ...] = get_args(ErrorCode)

# Section 3: CLM-YYYY-NNNNNN. YYYY is the recording year; NNNNNN is a zero-padded
# sequence. The pattern lives on the type so an ill-formed reference cannot be a
# ClaimRecord.
ClaimReference = Annotated[str, Field(pattern=r"^CLM-\d{4}-\d{6}$")]

# Section 4.3: the JSON numeral form money is carried in. Any number of decimal
# places matches here, because a scale that is too fine is violation 7 rather than
# violation 2, and the two are reported differently.
_DECIMAL_NUMERAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")


def _decimal_from_json_string(value: object) -> object:
    """Accept money only in the form section 4.3 fixes: a JSON string.

    JSON has no decimal primitive, so section 4.3 carries money as a string and
    makes a JSON number the wrong type under violation 2. That is not pedantry
    about notation. A JSON number is read as a binary float, and this value is the
    operand `V-4` compares against the policy `limit`, so accepting one would make
    a boundary comparison depend on how the caller happened to write the figure.

    A `Decimal` passes through because it is already exact; that is the form the
    rule layer and the tests construct. Everything else, `float` and `int`
    included, is refused here rather than quietly coerced.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        if _DECIMAL_NUMERAL.fullmatch(value) is None:
            raise ValueError("must be a decimal numeral carried as a JSON string")
        return Decimal(value)
    raise ValueError("must be a JSON string holding a decimal numeral, not a JSON number")


# Section 2.2 and 4.3 violation 8 / determination D-3: greater than zero, at most
# two decimal places, never rounded.
EstimatedAmount = Annotated[
    Decimal,
    BeforeValidator(_decimal_from_json_string),
    Field(gt=0, decimal_places=2),
]


def _reject_blank_policy_number(value: str) -> str:
    """Refuse empty or whitespace-only identifiers without changing the value.

    Section 4.3 violation 4 rejects a blank `policy_number`. Determination D-1
    forbids trimming: a value of `" MOT-4471"` must reach V-1 as sent, not as
    `"MOT-4471"`. Returning the original string keeps that promise.
    """
    if value.strip() == "":
        raise ValueError("policy_number must not be empty or whitespace-only")
    return value


# StrictStr so a JSON number is SCHEMA_INVALID (section 4.3.2), not silently
# coerced into an identifier the caller never typed.
PolicyNumber = Annotated[
    StrictStr, Field(min_length=1), AfterValidator(_reject_blank_policy_number)
]


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_number: PolicyNumber
    loss_date: date
    claim_type: ClaimType
    estimated_amount: EstimatedAmount
    description: StrictStr | None = None


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    `cancellation_date` is `date | None` with no default: the field must be
    present, and `None` is the only representation of "not cancelled" (WI-0158
    AC-3). A comparison against it without narrowing fails type checking, which
    is what makes skipping the absence check a type error rather than a missed
    test. An omitted field is a policy-master defect, not an uncancelled policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_number: PolicyNumber
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    # Section 4.3 fixes money as a JSON string on both sides of the `V-4`
    # comparison, so the policy master's `limit` is held to the same form. A master
    # that sends a JSON number fails to parse and becomes
    # POLICY_MASTER_INVALID_RESPONSE (section 6.3), which is the correct answer: a
    # float limit would make the boundary comparison inexact.
    limit: Annotated[Decimal, BeforeValidator(_decimal_from_json_string)]
    permitted_claim_types: tuple[ClaimType, ...]

    @classmethod
    def from_record(cls, record: PolicyRecord) -> Policy:
        """Parse a policy-master record into the model the rules read.

        This validates rather than constructs, because the master is a dependency
        this service does not own (section 1) and its `permitted_claim_types` is a
        tuple of arbitrary strings. Narrowing those to the section 2.3 vocabulary
        is a parse of foreign data: a peril this contract does not define means the
        master answered with something the service cannot use, which section 6.3
        reports as POLICY_MASTER_INVALID_RESPONSE rather than accepting quietly.
        """
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


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleFailure:
    """An immutable refusal naming one rule and one contract code.

    The two fields carry different types, so `RuleFailure(rule="POLICY_CANCELLED",
    code="V-7")` is a type error rather than a refusal that reports a rule label
    to a caller branching on `code`. Keyword-only construction rules out the
    positional swap as well.
    """

    rule: RuleId
    code: ErrorCode


class ClaimRecord(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format. The three fields `policy_number`,
    `loss_date`, and `claim_type` are the duplicate key WI-0151 AC-1 defines.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: ClaimReference
    policy_number: PolicyNumber
    loss_date: date
    claim_type: ClaimType
    estimated_amount: EstimatedAmount
    description: StrictStr | None = None


# The starter shipped this type as `RecordedNotification` and its service.py stub
# imported that name, but the C2 interface contract names it `ClaimRecord`. The
# contract wins, because C2 is what Day 3 and Day 4 were written against. The old
# name stays bound so code carrying the starter's signature still resolves.
RecordedNotification = ClaimRecord
