"""Typed engine errors with explicit retry semantics."""

from __future__ import annotations


class EngineError(Exception):
    """Base class for all engine failures."""

    retryable: bool = False
    code: str = "engine_error"


class ProviderNotConfigured(EngineError):
    """The provider needs credentials or configuration that are absent."""

    retryable = False
    code = "provider_not_configured"


class ProviderUnavailable(EngineError):
    """The provider could not be reached or is temporarily failing."""

    retryable = True
    code = "provider_unavailable"


class ProviderTimeout(ProviderUnavailable):
    """A provider call exceeded the configured timeout."""

    retryable = True
    code = "provider_timeout"


class ProviderRateLimited(ProviderUnavailable):
    """The provider rejected the call because of a rate limit."""

    retryable = True
    code = "provider_rate_limited"


class ProviderResponseError(EngineError):
    """The provider returned a response the engine cannot use."""

    retryable = False
    code = "provider_response_error"


class BudgetExceeded(EngineError):
    """The configured batch cost budget has been exhausted."""

    retryable = False
    code = "budget_exceeded"


class EvidenceValidationError(EngineError):
    """Output cites sources that were not actually retrieved."""

    retryable = False
    code = "evidence_validation_error"


class PipelineCancelled(EngineError):
    """The batch was cancelled by an operator."""

    retryable = False
    code = "pipeline_cancelled"


class ICPValidationError(EngineError):
    """The ICP is incomplete and cannot drive a real search."""

    retryable = False
    code = "icp_validation_error"
