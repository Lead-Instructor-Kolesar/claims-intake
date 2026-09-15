"""Errors used by the Week 2 local model lab."""


class UnknownModelError(ValueError):
    """Raised when a model identifier is not present in the configured model table."""


class TransientProviderError(Exception):
    """Raised when a provider call fails in a way that may succeed on retry."""


class PermanentProviderError(Exception):
    """Raised when a provider call fails in a way that must not be retried."""


class TruncatedResponseError(Exception):
    """Raised when a model response was cut off by the output-token ceiling."""
