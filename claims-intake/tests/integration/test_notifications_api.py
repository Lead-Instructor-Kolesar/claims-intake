"""Integration tests for `POST /notifications`.

These assert what a caller can rely on: the status, the `code`, and the documented
keys of `detail` (section 5.2). No test asserts on `message`, because the contract
does not maintain its wording.

Every payload identifier here is classified in `docs/payload-triage.md`, so a
failure names a payload and the rule that decided it.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import STATUS_BY_CODE, create_app
from claims.models import CONTRACT_ERROR_CODES
from claims.policy_client import LookupFailureReason, PolicyRecord, StubPolicyClient
from claims.repository import NotificationRepository
from tests.payloads import payload, payload_ids

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


@pytest.fixture
def client() -> TestClient:
    """A service over a fresh store and a policy master loaded from `data/`."""
    return TestClient(create_app(StubPolicyClient(), NotificationRepository()))


def post(client: TestClient, payload: dict[str, object]) -> Any:
    return client.post("/notifications", json=payload)


def test_a_notification_that_passes_every_rule_is_recorded(client: TestClient) -> None:
    response = post(client, payload("VALID-01"))
    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.fullmatch(body["claim_reference"])
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    "payload_id",
    [
        pytest.param("VALID-01", id="VALID-01"),
        pytest.param("VALID-02", id="VALID-02"),
        pytest.param("VALID-03", id="VALID-03"),
        pytest.param("VALID-04", id="VALID-04"),
        pytest.param("VALID-05", id="VALID-05"),
        pytest.param("VALID-06", id="VALID-06_description_absent"),
        pytest.param("VALID-07", id="VALID-07"),
        pytest.param("VALID-08", id="VALID-08"),
    ],
)
def test_every_valid_payload_is_accepted(client: TestClient, payload_id: str) -> None:
    assert post(client, payload(payload_id)).status_code == 201


def test_claim_references_are_unique_across_claim_records(
    client: TestClient,
) -> None:
    """Section 3: a reference is unique across all recorded notifications."""
    first = post(client, payload("VALID-01")).json()["claim_reference"]
    second = post(client, payload("VALID-02")).json()["claim_reference"]
    third = post(client, payload("VALID-03")).json()["claim_reference"]
    assert len({first, second, third}) == 3


@pytest.mark.parametrize(
    ("payload_id", "expected_status", "expected_code"),
    [
        pytest.param("EDGE-01", 201, None, id="EDGE-01_loss_on_inception_recorded"),
        pytest.param("EDGE-02", 201, None, id="EDGE-02_amount_equals_limit_recorded"),
        pytest.param("EDGE-03", 201, None, id="EDGE-03_loss_on_expiry_recorded"),
        pytest.param("EDGE-04", 422, "POLICY_CANCELLED", id="EDGE-04_cancelled"),
        pytest.param("EDGE-05", 422, "LOSS_BEFORE_INCEPTION", id="EDGE-05_inception"),
        pytest.param("EDGE-06", 422, "AMOUNT_EXCEEDS_LIMIT", id="EDGE-06_over_limit"),
        pytest.param("EDGE-07", 422, "POLICY_NOT_FOUND", id="EDGE-07_lowercase_policy"),
        pytest.param("EDGE-08", 400, "SCHEMA_INVALID", id="EDGE-08_amount_absent"),
        pytest.param("EDGE-09", 422, "TYPE_NOT_COVERED", id="EDGE-09_type_not_covered"),
        pytest.param("EDGE-10", 422, "POLICY_CANCELLED", id="EDGE-10_cancelled_and_expired"),
        pytest.param("EDGE-11", 400, "SCHEMA_INVALID", id="EDGE-11_claim_type_flood"),
        pytest.param("EDGE-12", 400, "SCHEMA_INVALID", id="EDGE-12_amount_three_places"),
    ],
)
def test_edge_payloads_return_the_status_the_triage_records(
    client: TestClient,
    payload_id: str,
    expected_status: int,
    expected_code: str | None,
) -> None:
    response = post(client, payload(payload_id))
    assert response.status_code == expected_status
    if expected_code is not None:
        assert response.json()["code"] == expected_code


@pytest.mark.parametrize(
    ("payload_id", "expected_status", "expected_code"),
    [
        pytest.param("INVALID-01", 422, "POLICY_NOT_FOUND", id="INVALID-01_not_found"),
        pytest.param("INVALID-02", 422, "LOSS_BEFORE_INCEPTION", id="INVALID-02_inception"),
        pytest.param("INVALID-03", 422, "LOSS_AFTER_EXPIRY", id="INVALID-03_expiry"),
        pytest.param("INVALID-04", 422, "AMOUNT_EXCEEDS_LIMIT", id="INVALID-04_limit"),
        pytest.param("INVALID-05", 422, "TYPE_NOT_COVERED", id="INVALID-05_type"),
        pytest.param("INVALID-07", 422, "POLICY_CANCELLED", id="INVALID-07_cancelled"),
    ],
)
def test_invalid_payloads_return_the_status_the_contract_maps(
    client: TestClient,
    payload_id: str,
    expected_status: int,
    expected_code: str,
) -> None:
    response = post(client, payload(payload_id))
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


def test_every_error_response_carries_the_section_5_1_envelope(
    client: TestClient,
) -> None:
    body = post(client, payload("EDGE-04")).json()
    assert set(body) == {"code", "message", "detail"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["detail"], dict)


def test_the_error_body_carries_no_status_field(client: TestClient) -> None:
    """Section 5.1: the status lives in the status line and in one place only."""
    assert "status" not in post(client, payload("EDGE-04")).json()


@pytest.mark.parametrize(
    ("payload_id", "expected_detail_keys"),
    [
        pytest.param("EDGE-07", {"policy_number"}, id="POLICY_NOT_FOUND_detail"),
        pytest.param(
            "EDGE-05",
            {"policy_number", "loss_date", "effective_date"},
            id="LOSS_BEFORE_INCEPTION_detail",
        ),
        pytest.param(
            "EDGE-06",
            {"policy_number", "estimated_amount", "limit"},
            id="AMOUNT_EXCEEDS_LIMIT_detail",
        ),
        pytest.param(
            "EDGE-09",
            {"policy_number", "claim_type", "permitted_claim_types", "product"},
            id="TYPE_NOT_COVERED_detail",
        ),
        pytest.param(
            "EDGE-04",
            {"policy_number", "loss_date", "cancellation_date"},
            id="POLICY_CANCELLED_detail",
        ),
    ],
)
def test_refusal_detail_carries_the_keys_section_6_2_documents(
    client: TestClient, payload_id: str, expected_detail_keys: set[str]
) -> None:
    body = post(client, payload(payload_id)).json()
    assert set(body["detail"]) == expected_detail_keys


def test_dates_and_money_in_detail_are_strings_and_never_floats(
    client: TestClient,
) -> None:
    """A float would change the monetary figure on its way to the caller."""
    detail = post(client, payload("EDGE-06")).json()["detail"]
    assert detail["estimated_amount"] == "26000.00"
    assert detail["limit"] == "10000.00"
    assert isinstance(detail["estimated_amount"], str)
    assert isinstance(detail["limit"], str)

    cancellation = post(client, payload("EDGE-04")).json()["detail"]
    assert cancellation["loss_date"] == "2026-01-15"
    assert cancellation["cancellation_date"] == "2026-01-15"


@pytest.mark.parametrize(
    "estimated_amount",
    [
        pytest.param(4200.00, id="json_float"),
        pytest.param(4200, id="json_integer"),
        pytest.param("4.2e3", id="not_a_decimal_numeral"),
    ],
)
def test_money_sent_as_anything_but_a_decimal_numeral_string_is_refused(
    client: TestClient, estimated_amount: object
) -> None:
    """Section 4.3 violation 2: a JSON number is read as a binary float.

    Refusing it at the boundary is what keeps the `V-4` comparison exact, so this is
    a 400 about the shape of the request and never a 201 recording a figure that
    differs from the one the caller sent.
    """
    wire = payload("VALID-01")
    wire["estimated_amount"] = estimated_amount
    response = client.post("/notifications", json=wire)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "SCHEMA_INVALID"
    assert {violation["field"] for violation in body["detail"]["violations"]} == {
        "estimated_amount"
    }


def test_schema_invalid_names_every_field_that_failed(client: TestClient) -> None:
    """Section 4.1: V-0 reports all of them, so one submission tells a developer everything."""
    response = client.post(
        "/notifications",
        json={
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "flood",
            "policy_holder_name": "unrecognised",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "SCHEMA_INVALID"
    violations = body["detail"]["violations"]
    assert {violation["field"] for violation in violations} == {
        "claim_type",
        "estimated_amount",
        "policy_holder_name",
    }
    assert all({"field", "problem"} == set(violation) for violation in violations)


@pytest.mark.parametrize(
    ("payload_id", "expected_field"),
    [
        pytest.param("EDGE-08", "estimated_amount", id="EDGE-08_required_field_absent"),
        pytest.param("EDGE-11", "claim_type", id="EDGE-11_outside_vocabulary"),
        pytest.param("EDGE-12", "estimated_amount", id="EDGE-12_scale_too_fine"),
    ],
)
def test_schema_invalid_names_the_field_a_developer_must_read(
    client: TestClient, payload_id: str, expected_field: str
) -> None:
    body = post(client, payload(payload_id)).json()
    fields = {violation["field"] for violation in body["detail"]["violations"]}
    assert expected_field in fields


def test_a_resubmitted_notification_is_refused_with_the_existing_reference(
    client: TestClient,
) -> None:
    """WI-0151 AC-2: the reference in detail belongs to the record made earlier."""
    first = post(client, payload("VALID-01"))
    assert first.status_code == 201

    duplicate = post(client, payload("INVALID-06"))
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"]["claim_reference"] == first.json()["claim_reference"]
    assert set(body["detail"]) == {
        "policy_number",
        "loss_date",
        "claim_type",
        "claim_reference",
    }


def test_a_refused_notification_is_not_recorded_so_resubmitting_repeats_the_refusal(
    client: TestClient,
) -> None:
    """WI-0151 AC-3: nothing was written, so there is nothing to duplicate."""
    first = post(client, payload("EDGE-06"))
    second = post(client, payload("EDGE-06"))
    assert first.status_code == second.status_code == 422
    assert second.json()["code"] == "AMOUNT_EXCEEDS_LIMIT"


def test_a_refusal_issues_no_claim_reference(client: TestClient) -> None:
    body = post(client, payload("EDGE-04")).json()
    assert "claim_reference" not in body
    assert "claim_reference" not in body["detail"]


def test_malformed_json_cannot_name_a_field(client: TestClient) -> None:
    response = client.post(
        "/notifications",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_JSON"
    assert body["detail"] == {}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"[]", id="json_array"),
        pytest.param(b'"a string"', id="json_string"),
        pytest.param(b"7", id="json_number"),
        pytest.param(b"null", id="json_null"),
    ],
)
def test_a_body_that_is_not_a_json_object_is_malformed(
    client: TestClient, body: bytes
) -> None:
    response = client.post(
        "/notifications", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_JSON"


@pytest.mark.parametrize(
    "content_type",
    [
        pytest.param("text/plain", id="text_plain"),
        pytest.param("application/xml", id="application_xml"),
        pytest.param("application/x-www-form-urlencoded", id="form_encoded"),
    ],
)
def test_a_body_that_is_not_json_is_refused_before_it_is_read(
    client: TestClient, content_type: str
) -> None:
    response = client.post(
        "/notifications", content=b"policy_number=MOT-4471", headers={"content-type": content_type}
    )
    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert body["detail"] == {"received": content_type, "expected": "application/json"}


def test_unsupported_media_type_reports_a_null_received_when_none_was_sent(
    client: TestClient,
) -> None:
    """Section 6.4: `received` is the Content-Type as sent, and null where none was."""
    response = client.post("/notifications", content=b"{}", headers={"content-type": ""})
    assert response.status_code == 415
    assert response.json()["detail"]["expected"] == "application/json"


def test_application_json_with_a_charset_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/notifications",
        content=b'{"policy_number": "MOT-4471", "loss_date": "2026-04-02",'
        b' "claim_type": "collision", "estimated_amount": "4200.00"}',
        headers={"content-type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "method",
    [
        pytest.param("get", id="GET"),
        pytest.param("put", id="PUT"),
        pytest.param("patch", id="PATCH"),
        pytest.param("delete", id="DELETE"),
    ],
)
def test_a_method_other_than_post_is_refused(client: TestClient, method: str) -> None:
    response = getattr(client, method)("/notifications")
    assert response.status_code == 405
    body = response.json()
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert body["detail"] == {"method": method.upper(), "allowed": ["POST"]}


@pytest.mark.parametrize(
    "method",
    [
        pytest.param("get", id="GET"),
        pytest.param("put", id="PUT"),
        pytest.param("patch", id="PATCH"),
        pytest.param("delete", id="DELETE"),
    ],
)
def test_a_405_carries_the_allow_header_the_method_requires(
    client: TestClient, method: str
) -> None:
    """Section 6.4 requires the header, and RFC 9110 requires it of any 405."""
    response = getattr(client, method)("/notifications")
    assert response.headers["allow"] == "POST"


def test_an_undefined_path_stays_inside_the_envelope(client: TestClient) -> None:
    response = client.post("/claims", json=payload("VALID-01"))
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "detail"}
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("reason", "expected_status", "expected_code", "expected_retryable"),
    [
        pytest.param("timeout", 504, "POLICY_MASTER_TIMEOUT", True, id="timeout_is_retryable"),
        pytest.param(
            "unreachable",
            503,
            "POLICY_MASTER_UNAVAILABLE",
            True,
            id="unreachable_is_retryable",
        ),
        pytest.param(
            "unparsable",
            502,
            "POLICY_MASTER_INVALID_RESPONSE",
            False,
            id="unparsable_is_not_retryable",
        ),
    ],
)
def test_a_policy_master_failure_is_reported_as_ours(
    reason: LookupFailureReason,
    expected_status: int,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    """Section 6.3: the caller sent a valid request and can do nothing about these."""
    client = TestClient(
        create_app(StubPolicyClient(fail_with=reason), NotificationRepository())
    )
    response = client.post("/notifications", json=payload("VALID-01"))
    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    assert body["detail"]["dependency"] == "policy_master"
    assert body["detail"]["reason"] == reason
    assert body["detail"]["retryable"] is expected_retryable
    assert body["detail"]["correlation_id"]
    assert set(body["detail"]) == {"dependency", "reason", "retryable", "correlation_id"}


def test_a_policy_master_failure_records_nothing() -> None:
    """Section 6.3: a retry of the identical payload after a 5xx is safe."""
    repository = NotificationRepository()
    failing = TestClient(create_app(StubPolicyClient(fail_with="timeout"), repository))
    failing.post("/notifications", json=payload("VALID-01"))

    recovered = TestClient(create_app(StubPolicyClient(), repository))
    response = recovered.post("/notifications", json=payload("VALID-01"))
    assert response.status_code == 201


class BrokenPolicyClient:
    """A policy master that fails in a way this service does not anticipate."""

    def get_policy(self, policy_number: str) -> PolicyRecord:
        raise RuntimeError("the dependency raised something we never specified")


def test_an_unanticipated_fault_does_not_escape_the_envelope() -> None:
    """Section 6.4: INTERNAL_ERROR exists so that no failure escapes the envelope."""
    client = TestClient(
        create_app(BrokenPolicyClient(), NotificationRepository()),
        raise_server_exceptions=False,
    )
    response = client.post("/notifications", json=payload("VALID-01"))
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert set(body["detail"]) == {"correlation_id"}


@pytest.mark.parametrize("payload_id", payload_ids("EDGE-"), ids=payload_ids("EDGE-"))
def test_every_response_status_is_inside_the_contracts_status_set(
    client: TestClient, payload_id: str
) -> None:
    """Section 6.5: a status outside this set is a defect in the service.

    Parametrised over every edge payload rather than looped over inside one test,
    so adding a payload to `data/` puts it under test and one bad status does not
    hide behind another.
    """
    permitted = {201, 400, 404, 405, 409, 415, 422, 500, 502, 503, 504}
    assert post(client, payload(payload_id)).status_code in permitted


def test_the_status_mapping_covers_exactly_the_codes_the_contract_enumerates() -> None:
    """Section 6: one status per code, and no code the service can emit is unmapped."""
    assert set(STATUS_BY_CODE) == set(CONTRACT_ERROR_CODES)
