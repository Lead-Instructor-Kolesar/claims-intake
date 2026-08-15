"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from pydantic import BaseModel


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.

    `policy_number` is declared so that the V-1 rule in `service.py` has something
    to read. Every other field, and every constraint on every field including this
    one, is Day 2's work.
    """

    policy_number: str


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    Day 2 assignment: declare the fields.
    """


class RecordedNotification(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format.

    Day 2 assignment: declare the fields.
    """
