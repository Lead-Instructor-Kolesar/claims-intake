"""Shared fixtures.

A fixture returns fresh state on every request. A fixture that returns the same
object to two tests makes the suite order-dependent, and an order-dependent suite
fails in CI on a day nothing changed.
"""

from __future__ import annotations

import pytest

from claims.policy_client import StubPolicyClient


@pytest.fixture
def policy_client() -> StubPolicyClient:
    """A policy master loaded from `data/policies.json`.

    Set `fail_with` on the returned client to exercise the three server-side
    lookup failures.
    """
    return StubPolicyClient()
