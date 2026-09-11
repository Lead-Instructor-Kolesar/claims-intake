"""Exercise POST /notifications through HTTP.

Payloads come from data/fnol_*.json. Each test builds its own client and
repository so the suite does not depend on run order.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.models import CLAIM_REFERENCE_PATTERN
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository

DATA = Path(__file__).resolve().parents[2] / "data"
REFERENCE = re.compile(CLAIM_REFERENCE_PATTERN)


def _payload(filename: str, item_id: str) -> dict[str, object]:
    for row in json.loads((DATA / filename).read_text()):
        if row["id"] == item_id:
            return dict(row["payload"])
    raise KeyError(item_id)


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recorded_on=date(2026, 8, 25))


@pytest.fixture
def http_client(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> Iterator[TestClient]:
    app.dependency_overrides[get_policy_client] = lambda: policy_client
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_accepted_notification_returns_201_and_claim_reference(
    http_client: TestClient,
) -> None:
    response = http_client.post(
        "/notifications", json=_payload("fnol_valid.json", "VALID-01")
    )
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "recorded"
    assert REFERENCE.match(body["claim_reference"])


@pytest.mark.parametrize(
    ("item_id", "status", "code", "detail_keys"),
    [
        pytest.param(
            "INVALID-01",
            422,
            "POLICY_NOT_FOUND",
            ("policy_number",),
            id="V-1-POLICY_NOT_FOUND",
        ),
        pytest.param(
            "INVALID-02",
            422,
            "LOSS_BEFORE_INCEPTION",
            ("policy_number", "loss_date", "effective_date"),
            id="V-2-LOSS_BEFORE_INCEPTION",
        ),
        pytest.param(
            "INVALID-03",
            422,
            "LOSS_AFTER_EXPIRY",
            ("policy_number", "loss_date", "expiry_date"),
            id="V-3-LOSS_AFTER_EXPIRY",
        ),
        pytest.param(
            "INVALID-04",
            422,
            "AMOUNT_EXCEEDS_LIMIT",
            ("policy_number", "estimated_amount", "limit"),
            id="V-4-AMOUNT_EXCEEDS_LIMIT",
        ),
        pytest.param(
            "INVALID-05",
            422,
            "TYPE_NOT_COVERED",
            ("policy_number", "claim_type", "product", "permitted_claim_types"),
            id="V-5-TYPE_NOT_COVERED",
        ),
        pytest.param(
            "INVALID-07",
            422,
            "POLICY_CANCELLED",
            ("policy_number", "loss_date", "cancellation_date"),
            id="V-7-POLICY_CANCELLED",
        ),
    ],
)
def test_each_cover_rule_refusal_matches_section_6(
    http_client: TestClient,
    item_id: str,
    status: int,
    code: str,
    detail_keys: tuple[str, ...],
) -> None:
    payload = _payload("fnol_invalid.json", item_id)
    response = http_client.post("/notifications", json=payload)
    body = response.json()
    assert response.status_code == status
    assert body["code"] == code
    for key in detail_keys:
        assert key in body["detail"]
    assert body["detail"]["policy_number"] == payload["policy_number"]
    if "loss_date" in detail_keys:
        assert body["detail"]["loss_date"] == payload["loss_date"]
    if "claim_type" in detail_keys:
        assert body["detail"]["claim_type"] == payload["claim_type"]
    if "estimated_amount" in detail_keys:
        assert body["detail"]["estimated_amount"] == payload["estimated_amount"]


def test_duplicate_notification_returns_409_with_existing_claim_reference(
    http_client: TestClient,
) -> None:
    first = http_client.post("/notifications", json=_payload("fnol_valid.json", "VALID-01"))
    assert first.status_code == 201
    second = http_client.post(
        "/notifications", json=_payload("fnol_invalid.json", "INVALID-06")
    )
    body = second.json()
    assert second.status_code == 409
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"]["policy_number"] == "MOT-4471"
    assert body["detail"]["loss_date"] == "2026-04-02"
    assert body["detail"]["claim_type"] == "collision"
    assert body["detail"]["claim_reference"] == first.json()["claim_reference"]


@pytest.mark.parametrize(
    ("payload", "field", "reason"),
    [
        pytest.param(
            _payload("fnol_edge.json", "EDGE-08"),
            "estimated_amount",
            "required_field_absent",
            id="parse-missing-required-field",
        ),
        pytest.param(
            {**_payload("fnol_valid.json", "VALID-02"), "unexpected": "x"},
            "unexpected",
            "unexpected_field",
            id="parse-extra-field-rejected",
        ),
        pytest.param(
            _payload("fnol_edge.json", "EDGE-11"),
            "claim_type",
            "not_in_vocabulary",
            id="parse-flood-not-in-vocabulary",
        ),
        pytest.param(
            _payload("fnol_edge.json", "EDGE-12"),
            "estimated_amount",
            "invalid_decimal_scale",
            id="parse-amount-invalid-decimal-scale",
        ),
    ],
)
def test_parse_failure_returns_400_not_a_rule_code(
    http_client: TestClient,
    payload: dict[str, object],
    field: str,
    reason: str,
) -> None:
    response = http_client.post("/notifications", json=payload)
    body = response.json()
    assert response.status_code == 400
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["field"] == field
    assert body["detail"]["reason"] == reason


@pytest.mark.parametrize(
    ("reason", "status", "code"),
    [
        pytest.param("timeout", 504, "POLICY_MASTER_TIMEOUT", id="lookup-timeout-504"),
        pytest.param(
            "unreachable", 503, "POLICY_MASTER_UNREACHABLE", id="lookup-unreachable-503"
        ),
        pytest.param(
            "unparsable", 502, "POLICY_MASTER_UNPARSABLE", id="lookup-unparsable-502"
        ),
    ],
)
def test_policy_lookup_failed_returns_distinct_5xx(
    repository: NotificationRepository,
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    failing = StubPolicyClient(fail_with=reason)
    app.dependency_overrides[get_policy_client] = lambda: failing
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        response = client.post(
            "/notifications", json=_payload("fnol_valid.json", "VALID-01")
        )
    app.dependency_overrides.clear()
    body = response.json()
    assert response.status_code == status
    assert body["code"] == code
    assert body["detail"]["dependency"] == "policy_master"
    assert body["detail"]["reason"] == reason
    assert status >= 500
