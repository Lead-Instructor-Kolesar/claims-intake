"""HTTP-level tests for `POST /notifications`.

Fixtures are loaded straight from `data/fnol_valid.json`, `data/fnol_invalid.json`,
and `data/fnol_edge.json` rather than hand-copied, so a change to the fixture data
is a change to what this suite exercises. Expected outcomes for the edge cases
come from `docs/payload-triage.md`; expected outcomes for the invalid cases come
from reading each payload against `docs/api-contract.md` section 4 and the
records in `data/policies.json`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client
from claims.policy_client import LookupFailureReason, StubPolicyClient

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")


def _load(name: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", json.loads((DATA_DIR / name).read_text()))


VALID_FIXTURES = _load("fnol_valid.json")
INVALID_FIXTURES = _load("fnol_invalid.json")
EDGE_FIXTURES = _load("fnol_edge.json")


def _by_id(fixtures: list[dict[str, Any]], fixture_id: str) -> dict[str, Any]:
    for fixture in fixtures:
        if fixture["id"] == fixture_id:
            return fixture
    raise KeyError(fixture_id)


def _assert_error_envelope(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {"code", "message", "detail"}


def _assert_detail(
    body: dict[str, Any], expected: dict[str, Any], *, absent: tuple[str, ...] = ()
) -> None:
    for key, value in expected.items():
        assert body["detail"][key] == value
    for key in absent:
        assert key not in body["detail"]


# ---------------------------------------------------------------------------
# fnol_valid.json: every record must be recorded.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", VALID_FIXTURES, ids=[f["id"] for f in VALID_FIXTURES])
def test_valid_payloads_are_recorded(client: TestClient, fixture: dict[str, Any]) -> None:
    response = client.post("/notifications", json=fixture["payload"])
    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"claim_reference", "status"}
    assert CLAIM_REFERENCE_PATTERN.match(body["claim_reference"])
    assert body["status"] == "recorded"


# ---------------------------------------------------------------------------
# fnol_invalid.json: each payload fails exactly one thing.
# ---------------------------------------------------------------------------

# id -> (expected status, expected code, expected detail)
INVALID_EXPECTATIONS: dict[str, tuple[int, str, dict[str, Any]]] = {
    "INVALID-01": (
        422,
        "POLICY_NOT_FOUND",
        {"rule": "V-1", "policy_number": "MOT-9999"},
    ),
    "INVALID-02": (
        422,
        "LOSS_BEFORE_INCEPTION",
        {"rule": "V-2", "loss_date": "2026-02-20", "effective_date": "2026-03-15"},
    ),
    "INVALID-03": (
        422,
        "LOSS_AFTER_EXPIRY",
        {"rule": "V-3", "loss_date": "2026-03-20", "expiry_date": "2026-02-28"},
    ),
    "INVALID-04": (
        422,
        "AMOUNT_EXCEEDS_LIMIT",
        {"rule": "V-4", "estimated_amount": "14500.00", "limit": "10000.00"},
    ),
    "INVALID-05": (
        422,
        "TYPE_NOT_COVERED",
        {"rule": "V-5", "claim_type": "collision"},
    ),
    "INVALID-07": (
        422,
        "POLICY_CANCELLED",
        {"rule": "V-7", "loss_date": "2026-03-05", "cancellation_date": "2026-02-01"},
    ),
}


@pytest.mark.parametrize(
    "fixture",
    [f for f in INVALID_FIXTURES if f["id"] != "INVALID-06"],
    ids=[f["id"] for f in INVALID_FIXTURES if f["id"] != "INVALID-06"],
)
def test_invalid_payloads_are_refused(client: TestClient, fixture: dict[str, Any]) -> None:
    expected_status, expected_code, expected_detail = INVALID_EXPECTATIONS[fixture["id"]]
    response = client.post("/notifications", json=fixture["payload"])
    assert response.status_code == expected_status
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == expected_code
    _assert_detail(body, expected_detail)


def test_invalid_06_is_a_duplicate_of_valid_01(client: TestClient) -> None:
    """INVALID-06 documents itself as a resubmission of VALID-01."""
    first = client.post("/notifications", json=_by_id(VALID_FIXTURES, "VALID-01")["payload"])
    assert first.status_code == 201
    first_reference = first.json()["claim_reference"]

    second = client.post("/notifications", json=_by_id(INVALID_FIXTURES, "INVALID-06")["payload"])
    assert second.status_code == 409
    body = second.json()
    _assert_error_envelope(body)
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    _assert_detail(body, {"rule": "V-6", "claim_reference": first_reference})


# ---------------------------------------------------------------------------
# fnol_edge.json: per docs/payload-triage.md's classification table.
# ---------------------------------------------------------------------------

# id -> (expected status, expected code or None for a 201, expected detail)
EDGE_EXPECTATIONS: dict[str, tuple[int, str | None, dict[str, Any]]] = {
    "EDGE-01": (201, None, {}),
    "EDGE-02": (201, None, {}),
    "EDGE-03": (201, None, {}),
    "EDGE-04": (
        422,
        "POLICY_CANCELLED",
        {"rule": "V-7", "loss_date": "2026-01-15", "cancellation_date": "2026-01-15"},
    ),
    "EDGE-05": (
        422,
        "LOSS_BEFORE_INCEPTION",
        {"rule": "V-2", "loss_date": "2026-03-02", "effective_date": "2026-04-15"},
    ),
    "EDGE-06": (
        422,
        "AMOUNT_EXCEEDS_LIMIT",
        {"rule": "V-4", "estimated_amount": "26000.00", "limit": "10000.00"},
    ),
    "EDGE-07": (
        422,
        "POLICY_NOT_FOUND",
        {"rule": "V-1", "policy_number": "mot-4471"},
    ),
    "EDGE-08": (400, "MALFORMED_REQUEST", {"field": "estimated_amount"}),
    "EDGE-09": (
        422,
        "TYPE_NOT_COVERED",
        {"rule": "V-5", "claim_type": "collision"},
    ),
    "EDGE-10": (
        422,
        "POLICY_CANCELLED",
        {"rule": "V-7", "loss_date": "2026-01-08", "cancellation_date": "2025-10-01"},
    ),
    "EDGE-11": (400, "MALFORMED_REQUEST", {"field": "claim_type"}),
    "EDGE-12": (400, "MALFORMED_REQUEST", {"field": "estimated_amount"}),
}


@pytest.mark.parametrize("fixture", EDGE_FIXTURES, ids=[f["id"] for f in EDGE_FIXTURES])
def test_edge_payloads_match_triage(client: TestClient, fixture: dict[str, Any]) -> None:
    expected_status, expected_code, expected_detail = EDGE_EXPECTATIONS[fixture["id"]]
    response = client.post("/notifications", json=fixture["payload"])
    assert response.status_code == expected_status
    body = response.json()
    if expected_code is None:
        assert set(body.keys()) == {"claim_reference", "status"}
        assert CLAIM_REFERENCE_PATTERN.match(body["claim_reference"])
        assert body["status"] == "recorded"
    else:
        _assert_error_envelope(body)
        assert body["code"] == expected_code
        absent = ("rule",) if expected_code == "MALFORMED_REQUEST" else ()
        _assert_detail(body, expected_detail, absent=absent)


# ---------------------------------------------------------------------------
# Direct boundary tests.
# ---------------------------------------------------------------------------


def test_non_json_body_is_malformed_with_no_field_key(client: TestClient) -> None:
    response = client.post(
        "/notifications",
        content=b"not json at all",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == "MALFORMED_REQUEST"
    _assert_detail(body, {}, absent=("field", "rule"))


def test_unknown_field_is_malformed_with_field_key(client: TestClient) -> None:
    payload = dict(_by_id(VALID_FIXTURES, "VALID-01")["payload"])
    payload["adjuster_notes"] = "not a contract field"
    response = client.post("/notifications", json=payload)
    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == "MALFORMED_REQUEST"
    _assert_detail(body, {"field": "adjuster_notes"}, absent=("rule",))


@pytest.mark.parametrize(
    ("fail_with", "expected_status", "expected_code"),
    [
        ("timeout", 504, "POLICY_MASTER_TIMEOUT"),
        ("unreachable", 503, "POLICY_MASTER_UNREACHABLE"),
        ("unparsable", 502, "POLICY_MASTER_UNPARSABLE"),
    ],
)
def test_policy_lookup_failures_map_to_5xx_with_no_rule_key(
    client: TestClient,
    make_policy_client: Callable[[LookupFailureReason | None], StubPolicyClient],
    fail_with: LookupFailureReason,
    expected_status: int,
    expected_code: str,
) -> None:
    app.dependency_overrides[get_policy_client] = lambda: make_policy_client(fail_with)
    payload = _by_id(VALID_FIXTURES, "VALID-01")["payload"]

    response = client.post("/notifications", json=payload)

    assert response.status_code == expected_status
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == expected_code
    _assert_detail(
        body,
        {"policy_number": payload["policy_number"], "reason": fail_with},
        absent=("rule",),
    )


def test_duplicate_submission_is_refused_with_original_reference(client: TestClient) -> None:
    payload = _by_id(VALID_FIXTURES, "VALID-02")["payload"]

    first = client.post("/notifications", json=payload)
    assert first.status_code == 201
    first_reference = first.json()["claim_reference"]

    second = client.post("/notifications", json=payload)
    assert second.status_code == 409
    body = second.json()
    _assert_error_envelope(body)
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    _assert_detail(body, {"rule": "V-6", "claim_reference": first_reference})
