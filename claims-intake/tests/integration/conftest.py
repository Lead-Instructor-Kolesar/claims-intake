"""Fixtures for the HTTP-level tests.

Each test gets a fresh `NotificationRepository` and a fresh `StubPolicyClient`,
wired into the app through `app.dependency_overrides`, so that claim-reference
sequencing and duplicate detection cannot leak between tests (see the warning in
`tests/conftest.py`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository


@pytest.fixture
def make_policy_client() -> Callable[[LookupFailureReason | None], StubPolicyClient]:
    """A factory for a fresh `StubPolicyClient`, optionally set to fail lookups.

    Exposed as a factory rather than a single fixture value so a test can ask for
    a client with a particular `fail_with` reason without affecting any other
    test's client.
    """

    def _make(fail_with: LookupFailureReason | None = None) -> StubPolicyClient:
        return StubPolicyClient(fail_with=fail_with)

    return _make


@pytest.fixture
def client(
    make_policy_client: Callable[[LookupFailureReason | None], StubPolicyClient],
) -> Iterator[TestClient]:
    """A `TestClient` wired to fresh dependencies for the duration of one test.

    A test that needs a failing policy master can replace the override after
    receiving the client, e.g.::

        app.dependency_overrides[get_policy_client] = lambda: make_policy_client("timeout")
    """
    repository = NotificationRepository()
    app.dependency_overrides[get_policy_client] = lambda: make_policy_client(None)
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
