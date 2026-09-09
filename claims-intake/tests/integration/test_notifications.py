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

# id -> (expected status, expected code)
INVALID_EXPECTATIONS: dict[str, tuple[int, str]] = {
    "INVALID-01": (422, "POLICY_NOT_FOUND"),  # MOT-9999 is not in the policy master.
    "INVALID-02": (422, "LOSS_BEFORE_INCEPTION"),  # loss precedes MOT-4479's inception.
    "INVALID-03": (422, "LOSS_AFTER_EXPIRY"),  # loss falls after MOT-4489's expiry.
    "INVALID-04": (422, "AMOUNT_EXCEEDS_LIMIT"),  # exceeds MOT-4502's 10000.00 limit.
    "INVALID-05": (422, "TYPE_NOT_COVERED"),  # collision on a liability-only product.
    "INVALID-07": (422, "POLICY_CANCELLED"),  # loss after cancellation, before expiry.
}


@pytest.mark.parametrize(
    "fixture",
    [f for f in INVALID_FIXTURES if f["id"] != "INVALID-06"],
    ids=[f["id"] for f in INVALID_FIXTURES if f["id"] != "INVALID-06"],
)
def test_invalid_payloads_are_refused(client: TestClient, fixture: dict[str, Any]) -> None:
    expected_status, expected_code = INVALID_EXPECTATIONS[fixture["id"]]
    response = client.post("/notifications", json=fixture["payload"])
    assert response.status_code == expected_status
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == expected_code


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
    assert body["detail"]["claim_reference"] == first_reference


# ---------------------------------------------------------------------------
# fnol_edge.json: per docs/payload-triage.md's classification table.
# ---------------------------------------------------------------------------

# id -> (expected status, expected code or None for a 201)
EDGE_EXPECTATIONS: dict[str, tuple[int, str | None]] = {
    "EDGE-01": (201, None),
    "EDGE-02": (201, None),
    "EDGE-03": (201, None),
    "EDGE-04": (422, "POLICY_CANCELLED"),
    "EDGE-05": (422, "LOSS_BEFORE_INCEPTION"),
    "EDGE-06": (422, "AMOUNT_EXCEEDS_LIMIT"),
    "EDGE-07": (422, "POLICY_NOT_FOUND"),
    "EDGE-08": (400, "MALFORMED_REQUEST"),
    "EDGE-09": (422, "TYPE_NOT_COVERED"),
    "EDGE-10": (422, "POLICY_CANCELLED"),
    "EDGE-11": (400, "MALFORMED_REQUEST"),
    "EDGE-12": (400, "MALFORMED_REQUEST"),
}


@pytest.mark.parametrize("fixture", EDGE_FIXTURES, ids=[f["id"] for f in EDGE_FIXTURES])
def test_edge_payloads_match_triage(client: TestClient, fixture: dict[str, Any]) -> None:
    expected_status, expected_code = EDGE_EXPECTATIONS[fixture["id"]]
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
    assert "field" not in body["detail"]


def test_unknown_field_is_malformed_with_field_key(client: TestClient) -> None:
    payload = dict(_by_id(VALID_FIXTURES, "VALID-01")["payload"])
    payload["adjuster_notes"] = "not a contract field"
    response = client.post("/notifications", json=payload)
    assert response.status_code == 400
    body = response.json()
    _assert_error_envelope(body)
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["field"] == "adjuster_notes"


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
    assert body["detail"].keys() == {"policy_number", "reason"}
    assert body["detail"]["policy_number"] == payload["policy_number"]
    assert body["detail"]["reason"] == fail_with
    assert "rule" not in body["detail"]


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
    assert body["detail"]["claim_reference"] == first_reference
