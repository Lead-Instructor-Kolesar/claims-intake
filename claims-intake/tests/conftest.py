"""Shared fixtures.

A fixture returns fresh state on every request. A fixture that returns the same
object to two tests makes the suite order-dependent, and an order-dependent suite
fails in CI on a day nothing changed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimType, NotificationRequest, Policy
from claims.policy_client import StubPolicyClient
from claims.repository import NotificationRepository

# Python construction uses date/Decimal, never JSON strings or floats.
# Contract §2.2 is the wire format; these factories are already past parse.
_DEFAULT_LOSS = date(2026, 4, 2)
_DEFAULT_AMOUNT = Decimal("4200.00")
_DEFAULT_LIMIT = Decimal("10000.00")


@pytest.fixture
def policy_client() -> StubPolicyClient:
    """A policy master loaded from `data/policies.json`.

    Set `fail_with` on the returned client to exercise the three server-side
    lookup failures.
    """
    return StubPolicyClient()


@pytest.fixture
def make_notification() -> Callable[..., NotificationRequest]:
    """Return a new well-formed NotificationRequest on every call."""

    def _make(
        *,
        policy_number: str = "MOT-4471",
        loss_date: date = _DEFAULT_LOSS,
        claim_type: ClaimType = "collision",
        estimated_amount: Decimal = _DEFAULT_AMOUNT,
        description: str | None = "Rear ended at a junction.",
    ) -> NotificationRequest:
        return NotificationRequest(
            policy_number=policy_number,
            loss_date=loss_date,
            claim_type=claim_type,
            estimated_amount=estimated_amount,
            description=description,
        )

    return _make


@pytest.fixture
def make_policy() -> Callable[..., Policy]:
    """Return a new Policy on every call.

    cancellation_date is passed explicitly (including None) so the factory
    cannot hide WI-0158 AC-3: null means not cancelled, and the field is
    required at construction.
    """

    def _make(
        *,
        policy_number: str = "MOT-4471",
        product: str = "comprehensive",
        effective_date: date = date(2026, 3, 1),
        expiry_date: date = date(2026, 12, 31),
        cancellation_date: date | None = None,
        limit: Decimal = _DEFAULT_LIMIT,
        permitted_claim_types: tuple[ClaimType, ...] = (
            "collision",
            "theft",
            "glass",
            "liability",
            "weather",
        ),
    ) -> Policy:
        return Policy(
            policy_number=policy_number,
            product=product,
            effective_date=effective_date,
            expiry_date=expiry_date,
            cancellation_date=cancellation_date,
            limit=limit,
            permitted_claim_types=permitted_claim_types,
        )

    return _make


@pytest.fixture
def repository() -> NotificationRepository:
    """A new in-memory store. Never shared across tests."""
    return NotificationRepository()
