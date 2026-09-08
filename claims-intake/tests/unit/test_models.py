"""Shape-boundary tests for Day 2 models.

Written against contract sections 2–4 and the payload classification in
`docs/payload-triage.md` (EDGE-07 / EDGE-11 / EDGE-12 decisions). A failure here
means the type is too loose (a structurally bad payload reached the rules) or too
tight (a well-formed business-rule case was treated as 400).

JSON fixtures are the HTTP wire format, so their dates and amounts are strings.
Every Python construction in this file uses `date(...)` and `Decimal("...")`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from claims.models import (
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleIdentifier,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

Boundary = Literal["model", "rules"]


def _fnol_payloads_by_id(filename: str) -> dict[str, dict[str, object]]:
    records = json.loads((DATA_DIR / filename).read_text())
    return {record["id"]: record["payload"] for record in records}


VALID = _fnol_payloads_by_id("fnol_valid.json")
INVALID = _fnol_payloads_by_id("fnol_invalid.json")
EDGE = _fnol_payloads_by_id("fnol_edge.json")

# Contract §4 / triage: only EDGE-08, EDGE-11, EDGE-12 fail to parse.
# Everything else is well formed even when the rules would later refuse it.
_MODEL_FAILURE_IDS = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})

_WELL_FORMED: list[tuple[str, dict[str, object]]] = [
    (payload_id, payload)
    for source in (VALID, INVALID, EDGE)
    for payload_id, payload in source.items()
    if payload_id not in _MODEL_FAILURE_IDS
]


def _copy(payload: dict[str, object]) -> dict[str, object]:
    return dict(payload)


def _valid_body() -> dict[str, object]:
    """Wire-format body cloned from VALID-01 so mutation cannot leak."""
    return _copy(VALID["VALID-01"])


def _claim_body() -> dict[str, object]:
    """Python construction for ClaimRecord. Dates and money are never strings."""
    return {
        "claim_reference": "CLM-2026-000001",
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }


# --- NotificationRequest: accepts well-formed payloads --------------------------------


@pytest.mark.parametrize(
    ("payload_id", "payload"),
    _WELL_FORMED,
    ids=[payload_id for payload_id, _ in _WELL_FORMED],
)
def test_notification_request_accepts_well_formed_payload(
    payload_id: str,
    payload: dict[str, object],
) -> None:
    """A well-formed body becomes date and Decimal, not leftover strings."""
    parsed = NotificationRequest.model_validate(_copy(payload))
    assert type(parsed.loss_date) is date
    assert type(parsed.estimated_amount) is Decimal
    assert payload_id  # ids identify the case; the payload is what is asserted


# --- NotificationRequest: extra fields forbidden (contract §2.2) ----------------------


@pytest.mark.parametrize(
    "extra_field",
    ["loss_time", "policy_numbr"],
    ids=["unknown_field", "misspelled_field"],
)
def test_notification_request_rejects_unknown_field(extra_field: str) -> None:
    # A misspelled field accepted-and-ignored would record data the caller did not send.
    body = _valid_body()
    body[extra_field] = "unexpected"
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


# --- NotificationRequest: required fields (contract §2.2) -----------------------------


@pytest.mark.parametrize(
    ("field_name", "body"),
    [
        ("policy_number", {k: v for k, v in VALID["VALID-01"].items() if k != "policy_number"}),
        ("loss_date", {k: v for k, v in VALID["VALID-01"].items() if k != "loss_date"}),
        ("claim_type", {k: v for k, v in VALID["VALID-01"].items() if k != "claim_type"}),
        ("estimated_amount", {k: v for k, v in VALID["VALID-01"].items() if k != "estimated_amount"}),
        ("estimated_amount", _copy(EDGE["EDGE-08"])),
    ],
    ids=[
        "missing_policy_number",
        "missing_loss_date",
        "missing_claim_type",
        "missing_estimated_amount",
        "missing_estimated_amount_edge_08",
    ],
)
def test_notification_request_rejects_missing_required_field(
    field_name: str,
    body: dict[str, object],
) -> None:
    assert field_name not in body
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "field_name",
    ["policy_number", "loss_date", "claim_type", "estimated_amount"],
    ids=[
        "policy_number_has_no_default",
        "loss_date_has_no_default",
        "claim_type_has_no_default",
        "estimated_amount_has_no_default",
    ],
)
def test_notification_request_required_field_has_no_default(field_name: str) -> None:
    # Missing-rejected is not enough: a default would invent caller data.
    assert NotificationRequest.model_fields[field_name].is_required()


def test_notification_request_rejects_empty_policy_number() -> None:
    body = _valid_body()
    body["policy_number"] = ""
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


def test_notification_request_rejects_policy_number_wrong_type() -> None:
    body = _valid_body()
    body["policy_number"] = 4471
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


# --- NotificationRequest: claim_type vocabulary is structural (contract §2.3) ---------


@pytest.mark.parametrize(
    "claim_type",
    ["flood", "", "collison"],
    ids=["claim_type_not_in_vocabulary", "empty_claim_type", "claim_type_misspelled"],
)
def test_notification_request_rejects_claim_type_not_in_vocabulary(claim_type: str) -> None:
    # flood is EDGE-11. Contract §4: MALFORMED_REQUEST, not V-5 TYPE_NOT_COVERED.
    body = _valid_body()
    body["claim_type"] = claim_type
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


def test_notification_request_rejects_claim_type_wrong_type() -> None:
    body = _valid_body()
    body["claim_type"] = 1
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


def test_notification_request_rejects_edge_11_flood_as_unknown_vocabulary() -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_copy(EDGE["EDGE-11"]))


# --- NotificationRequest: estimated_amount (contract §2.2) ----------------------------


@pytest.mark.parametrize(
    "amount",
    ["0.00", "-1.00"],
    ids=["amount_not_greater_than_zero", "amount_negative"],
)
def test_notification_request_rejects_amount_not_greater_than_zero(amount: str) -> None:
    body = _valid_body()
    body["estimated_amount"] = amount
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


@pytest.mark.parametrize(
    "amount",
    ["3499.999", "10.5", "10"],
    ids=["amount_three_decimal_places", "amount_one_decimal_place", "amount_integer_scale"],
)
def test_notification_request_rejects_amount_not_exactly_two_decimal_places(
    amount: str,
) -> None:
    # EDGE-12 is three places. One place and integer scale also violate §2.2.
    body = _valid_body()
    body["estimated_amount"] = amount
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


def test_notification_request_rejects_edge_12_three_decimal_places() -> None:
    # Contract §4: not two decimal places is MALFORMED_REQUEST, not V-4.
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(_copy(EDGE["EDGE-12"]))


def test_notification_request_rejects_float_money() -> None:
    # JSON numbers become float in Python; Decimal cannot represent USD exactly
    # from binary float. Coerce from str/int only (contract §2.2).
    body = _valid_body()
    body["estimated_amount"] = 4200.00
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


def test_notification_request_rejects_estimated_amount_wrong_type() -> None:
    body = _valid_body()
    body["estimated_amount"] = True
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


# --- NotificationRequest: loss_date must be a calendar date (contract §2.2) -----------


@pytest.mark.parametrize(
    "loss_date",
    [123, "not-a-date", "04/02/2026"],
    ids=["loss_date_wrong_type", "loss_date_unparsable", "loss_date_not_iso"],
)
def test_notification_request_rejects_loss_date_that_is_not_a_date(
    loss_date: object,
) -> None:
    body = _valid_body()
    body["loss_date"] = loss_date
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(body)


# --- NotificationRequest: description absent ≡ null (contract §2.2) -------------------


@pytest.mark.parametrize(
    "body",
    [_copy(VALID["VALID-06"]), {**VALID["VALID-01"], "description": None}],
    ids=["description_absent", "description_null"],
)
def test_optional_description_normalizes_to_none(body: dict[str, object]) -> None:
    parsed = NotificationRequest.model_validate(body)
    assert parsed.description is None


# --- Policy: dates, Decimal, extras, WI-0158 AC-3 typing ------------------------------


def test_policy_term_dates_are_date_values(make_policy: Callable[..., Policy]) -> None:
    policy = make_policy(cancellation_date=date(2026, 6, 1), limit=Decimal("25000.00"))
    assert type(policy.effective_date) is date
    assert type(policy.expiry_date) is date
    assert type(policy.cancellation_date) is date


def test_policy_limit_is_decimal(make_policy: Callable[..., Policy]) -> None:
    policy = make_policy(limit=Decimal("25000.00"))
    assert type(policy.limit) is Decimal


def test_policy_accepts_null_cancellation_date(make_policy: Callable[..., Policy]) -> None:
    # WI-0158 AC-3: null means not cancelled. None is a real value, not a missing field.
    policy = make_policy(cancellation_date=None)
    assert policy.cancellation_date is None


def test_policy_cancellation_date_is_required_but_nullable() -> None:
    field = Policy.model_fields["cancellation_date"]
    assert field.is_required()
    assert field.annotation == date | None


@pytest.mark.parametrize(
    "field_name",
    [
        "policy_number",
        "product",
        "effective_date",
        "expiry_date",
        "cancellation_date",
        "limit",
        "permitted_claim_types",
    ],
    ids=[
        "omitted_policy_number",
        "omitted_product",
        "omitted_effective_date",
        "omitted_expiry_date",
        "omitted_cancellation_date",
        "omitted_limit",
        "omitted_permitted_claim_types",
    ],
)
def test_policy_rejects_omitted_required_field(
    make_policy: Callable[..., Policy],
    field_name: str,
) -> None:
    body = make_policy().model_dump()
    del body[field_name]
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


@pytest.mark.parametrize(
    "field_name",
    [
        "policy_number",
        "product",
        "effective_date",
        "expiry_date",
        "cancellation_date",
        "limit",
        "permitted_claim_types",
    ],
    ids=[
        "policy_number_has_no_default",
        "product_has_no_default",
        "effective_date_has_no_default",
        "expiry_date_has_no_default",
        "cancellation_date_has_no_default",
        "limit_has_no_default",
        "permitted_claim_types_has_no_default",
    ],
)
def test_policy_required_field_has_no_default(field_name: str) -> None:
    assert Policy.model_fields[field_name].is_required()


def test_policy_rejects_unparsable_cancellation_date(make_policy: Callable[..., Policy]) -> None:
    body = make_policy().model_dump()
    body["cancellation_date"] = "not-a-date"
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


def test_policy_rejects_unknown_field(make_policy: Callable[..., Policy]) -> None:
    body = make_policy().model_dump()
    body["cover_note"] = "extra"
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


def test_policy_rejects_empty_policy_number(make_policy: Callable[..., Policy]) -> None:
    with pytest.raises(ValidationError):
        make_policy(policy_number="")


def test_policy_rejects_float_limit(make_policy: Callable[..., Policy]) -> None:
    body = make_policy().model_dump()
    body["limit"] = 10000.00
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


def test_policy_rejects_unparsable_limit(make_policy: Callable[..., Policy]) -> None:
    body = make_policy().model_dump()
    body["limit"] = "not-a-decimal"
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


def test_policy_rejects_permitted_claim_type_not_in_vocabulary(
    make_policy: Callable[..., Policy],
) -> None:
    body = make_policy().model_dump()
    body["permitted_claim_types"] = ("flood",)
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


@pytest.mark.parametrize(
    "field_name",
    ["effective_date", "expiry_date"],
    ids=["effective_date_not_a_date", "expiry_date_not_a_date"],
)
def test_policy_rejects_term_date_that_is_not_a_date(
    make_policy: Callable[..., Policy],
    field_name: str,
) -> None:
    body = make_policy().model_dump()
    body[field_name] = "not-a-date"
    with pytest.raises(ValidationError):
        Policy.model_validate(body)


# --- RuleFailure: two types so a rule id cannot be passed as an error code ------------


@pytest.mark.parametrize(
    "field",
    ["rule", "code"],
    ids=["rule_is_frozen", "code_is_frozen"],
)
def test_rule_failure_is_immutable(field: str) -> None:
    failure = RuleFailure(rule=RuleIdentifier("V-1"), code=ErrorCode("POLICY_NOT_FOUND"))
    replacement: object = (
        RuleIdentifier("V-2") if field == "rule" else ErrorCode("TYPE_NOT_COVERED")
    )
    with pytest.raises(FrozenInstanceError):
        setattr(failure, field, replacement)


def test_rule_failure_carries_rule_identifier_and_error_code_separately() -> None:
    failure = RuleFailure(rule=RuleIdentifier("V-1"), code=ErrorCode("POLICY_NOT_FOUND"))
    assert failure.rule == "V-1"
    assert failure.code == "POLICY_NOT_FOUND"


# --- ClaimRecord: claim_reference format (contract §3) ---------------------------------


def test_claim_record_uses_date_and_decimal() -> None:
    recorded = ClaimRecord.model_validate(_claim_body())
    assert type(recorded.loss_date) is date
    assert type(recorded.estimated_amount) is Decimal


@pytest.mark.parametrize(
    "claim_reference",
    ["CLM-26-1", "CLM-2026-1", "2026-000001"],
    ids=["year_not_four_digits", "sequence_not_six_digits", "missing_clm_prefix"],
)
def test_claim_record_rejects_claim_reference_not_matching_format(
    claim_reference: str,
) -> None:
    body = _claim_body()
    body["claim_reference"] = claim_reference
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


def test_claim_record_rejects_unknown_field() -> None:
    body = _claim_body()
    body["handler_id"] = "extra"
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


def test_claim_record_rejects_loss_date_that_is_not_a_date() -> None:
    body = _claim_body()
    body["loss_date"] = "not-a-date"
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


def test_claim_record_rejects_claim_type_not_in_vocabulary() -> None:
    body = _claim_body()
    body["claim_type"] = "flood"
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


def test_claim_record_rejects_float_money() -> None:
    body = _claim_body()
    body["estimated_amount"] = 4200.00
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


def test_claim_record_rejects_empty_policy_number() -> None:
    body = _claim_body()
    body["policy_number"] = ""
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


@pytest.mark.parametrize(
    "amount",
    ["0.00", "10.5"],
    ids=["amount_not_greater_than_zero", "amount_one_decimal_place"],
)
def test_claim_record_rejects_amount_that_is_not_usd(amount: str) -> None:
    body = _claim_body()
    body["estimated_amount"] = amount
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


@pytest.mark.parametrize(
    "field_name",
    [
        "claim_reference",
        "policy_number",
        "loss_date",
        "claim_type",
        "estimated_amount",
        "description",
    ],
    ids=[
        "omitted_claim_reference",
        "omitted_policy_number",
        "omitted_loss_date",
        "omitted_claim_type",
        "omitted_estimated_amount",
        "omitted_description",
    ],
)
def test_claim_record_rejects_omitted_required_field(field_name: str) -> None:
    body = _claim_body()
    del body[field_name]
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate(body)


# --- Deliberate classification of invalid and edge payloads (contract §4 / triage) ---


@pytest.mark.parametrize(
    ("filename", "payload_id", "boundary"),
    [
        ("fnol_invalid.json", "INVALID-01", "rules"),
        ("fnol_invalid.json", "INVALID-02", "rules"),
        ("fnol_invalid.json", "INVALID-03", "rules"),
        ("fnol_invalid.json", "INVALID-04", "rules"),
        ("fnol_invalid.json", "INVALID-05", "rules"),
        ("fnol_invalid.json", "INVALID-06", "rules"),
        ("fnol_invalid.json", "INVALID-07", "rules"),
        ("fnol_edge.json", "EDGE-01", "rules"),
        ("fnol_edge.json", "EDGE-02", "rules"),
        ("fnol_edge.json", "EDGE-03", "rules"),
        ("fnol_edge.json", "EDGE-04", "rules"),
        ("fnol_edge.json", "EDGE-05", "rules"),
        ("fnol_edge.json", "EDGE-06", "rules"),
        ("fnol_edge.json", "EDGE-07", "rules"),
        ("fnol_edge.json", "EDGE-08", "model"),
        ("fnol_edge.json", "EDGE-09", "rules"),
        ("fnol_edge.json", "EDGE-10", "rules"),
        ("fnol_edge.json", "EDGE-11", "model"),
        ("fnol_edge.json", "EDGE-12", "model"),
    ],
    ids=[
        "INVALID-01",
        "INVALID-02",
        "INVALID-03",
        "INVALID-04",
        "INVALID-05",
        "INVALID-06",
        "INVALID-07",
        "EDGE-01",
        "EDGE-02",
        "EDGE-03",
        "EDGE-04",
        "EDGE-05",
        "EDGE-06",
        "EDGE-07",
        "EDGE-08",
        "EDGE-09",
        "EDGE-10",
        "EDGE-11",
        "EDGE-12",
    ],
)
def test_payload_fails_at_model_or_survives_to_rules(
    filename: str,
    payload_id: str,
    boundary: Boundary,
) -> None:
    """INVALID-* are well formed; EDGE-08/11/12 fail at parse (contract §4, triage)."""
    payload = _fnol_payloads_by_id(filename)[payload_id]
    if boundary == "model":
        with pytest.raises(ValidationError):
            NotificationRequest.model_validate(payload)
    else:
        NotificationRequest.model_validate(payload)
