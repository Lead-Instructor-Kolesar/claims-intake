"""Error taxonomy. Week 2 reference implementation."""

from __future__ import annotations


class PromptLabError(RuntimeError):
    """Base for every error this package raises."""


class TransientProviderError(PromptLabError):
    """Rate limit, server error, timeout, connection failure. Retried."""


class PermanentProviderError(PromptLabError):
    """Authentication, authorization, malformed request, unsupported parameter."""


class TruncatedResponseError(PromptLabError):
    """The provider stopped because the output ceiling was reached."""


class BudgetExceededError(PromptLabError):
    """The weekly ceiling or the per-run cap would be crossed."""


class UnknownModelError(PromptLabError):
    """Model identifier absent from the rate table."""


class MissingPromptVariableError(PromptLabError):
    """A template placeholder had no supplied value."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"missing prompt variables: {', '.join(missing)}")
        self.missing = missing


class StructuredOutputError(PromptLabError):
    """The response did not validate against the schema after the repair cap."""
