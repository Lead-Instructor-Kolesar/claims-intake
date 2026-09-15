"""Errors used by the Week 2 local model lab."""


class UnknownModelError(ValueError):
    """Raised when a model identifier is not present in the configured model table."""


class TransientProviderError(RuntimeError):
    """Timeout, connection failure, or other temporary Ollama/server failure."""


class PermanentProviderError(RuntimeError):
    """Malformed request, unavailable model, or other non-retryable request failure."""


class TruncatedResponseError(RuntimeError):
    """Ollama reported that the output token ceiling was reached."""
