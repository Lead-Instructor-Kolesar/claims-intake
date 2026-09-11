"""Errors used by the Week 2 local model lab."""


class UnknownModelError(ValueError):
    """Raised when a model identifier is not present in the configured model table."""


class TransientProviderError(Exception):
    """Timeout, connection failure, or a temporary Ollama failure. Retryable."""


class PermanentProviderError(Exception):
    """Malformed request, missing model, or another non-retryable failure."""


class TruncatedResponseError(Exception):
    """Ollama reported that the output token ceiling was reached."""
