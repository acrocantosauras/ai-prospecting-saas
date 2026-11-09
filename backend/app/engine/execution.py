"""Execution layer: timeouts, retries, rate limits, metering and budgets.

Every external call made by the engine passes through :class:`ProviderRunner`,
so retry behaviour, failure isolation and cost accounting are applied uniformly
regardless of provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import TypeVar

from app.engine.contracts import ProviderDescriptor
from app.engine.errors import (
    BudgetExceeded,
    EngineError,
    ProviderResponseError,
    ProviderTimeout,
)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Retry/backoff/timeout configuration for provider calls."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    timeout_seconds: float = 15.0
    # Retrying a timed-out call can double-charge a provider and duplicate side
    # effects; a timeout is reported instead of retried by default.
    retry_on_timeout: bool = False

    def delay_for(self, attempt: int) -> float:
        """Return the exponential backoff delay after ``attempt`` failures."""
        delay: float = self.base_delay_seconds * (2 ** max(attempt - 1, 0))
        return float(min(delay, self.max_delay_seconds))


@dataclass(frozen=True)
class UsageEvent:
    """A single metered provider attempt."""

    provider: str
    capability: str
    operation: str
    units: int
    cost_usd: float
    success: bool
    attempts: int
    error: str | None = None


@dataclass
class UsageMeter:
    """In-memory usage accounting with an optional persistence listener.

    A budget is enforced *before* each call so a runaway batch cannot spend
    without bound. Failures are metered too: a retried provider call still costs
    money.
    """

    max_cost_usd: float | None = None
    listener: Callable[[UsageEvent], None] | None = None
    events: list[UsageEvent] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        """Total measured spend so far."""
        return round(sum(event.cost_usd for event in self.events), 6)

    @property
    def total_calls(self) -> int:
        """Total provider attempts made so far."""
        return len(self.events)

    def check_budget(self) -> None:
        """Raise when the configured budget has been reached."""
        if self.max_cost_usd is not None and self.total_cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(
                f"Batch cost budget exhausted (${self.total_cost_usd:.4f} of "
                f"${self.max_cost_usd:.4f}); remaining work was not executed"
            )

    def record(
        self,
        provider: ProviderDescriptor,
        operation: str,
        *,
        success: bool,
        attempts: int = 1,
        units: int = 1,
        cost_usd: float | None = None,
        error: str | None = None,
        capability: str | None = None,
    ) -> UsageEvent:
        """Record one provider attempt and notify the listener."""
        event = UsageEvent(
            provider=provider.name,
            capability=capability or provider.capability,
            operation=operation,
            units=units,
            cost_usd=provider.cost_per_call_usd if cost_usd is None else cost_usd,
            success=success,
            attempts=attempts,
            error=error,
        )
        self.events.append(event)
        if self.listener is not None:
            self.listener(event)
        return event

    def cost_by_capability(self) -> dict[str, float]:
        """Return measured spend grouped by capability."""
        totals: dict[str, float] = {}
        for event in self.events:
            totals[event.capability] = round(
                totals.get(event.capability, 0.0) + event.cost_usd, 6
            )
        return totals


class RateLimiter:
    """Enforces a minimum interval between calls to the same provider."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialise the limiter with a per-provider minimum interval."""
        self._min_interval = max(min_interval_seconds, 0.0)
        self._clock = clock
        self._sleeper = sleeper
        self._last_call: dict[str, float] = {}

    def wait(self, provider_name: str) -> None:
        """Block (or sleep via the injected sleeper) until a call is allowed."""
        if self._min_interval <= 0:
            return
        last = self._last_call.get(provider_name)
        now = self._clock()
        if last is not None:
            remaining = self._min_interval - (now - last)
            if remaining > 0:
                self._sleeper(remaining)
        self._last_call[provider_name] = self._clock()


class ProviderRunner:
    """Runs provider calls with retries, timeouts, rate limits and metering."""

    def __init__(
        self,
        *,
        retry: RetryPolicy | None = None,
        meter: UsageMeter | None = None,
        limiter: RateLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Wire the runner dependencies; all are optional for simple tests."""
        self._retry = retry or RetryPolicy()
        self._meter = meter or UsageMeter()
        self._limiter = limiter
        self._sleeper = sleeper

    @property
    def meter(self) -> UsageMeter:
        """Expose the meter for cost reporting."""
        return self._meter

    def run(
        self,
        provider: ProviderDescriptor,
        operation: str,
        call: Callable[[], T],
        *,
        units: int = 1,
        capability: str | None = None,
    ) -> T:
        """Execute ``call`` with retries and return its result.

        Retryable provider failures are retried with exponential backoff;
        non-retryable failures (missing credentials, invalid responses) surface
        immediately. Unexpected exceptions are wrapped so callers can isolate
        failures per company.
        """
        if self._limiter is not None:
            self._limiter.wait(provider.name)
        attempts = self._retry.max_attempts
        last_error: EngineError | None = None
        for attempt in range(1, attempts + 1):
            self._meter.check_budget()
            try:
                result = self._call_with_timeout(provider, operation, call)
            except EngineError as exc:
                last_error = exc
                self._meter.record(
                    provider,
                    operation,
                    success=False,
                    attempts=attempt,
                    units=units,
                    error=str(exc),
                    capability=capability,
                )
                if isinstance(exc, ProviderTimeout) and not self._retry.retry_on_timeout:
                    raise
                if not exc.retryable or attempt >= attempts:
                    raise
                self._sleeper(self._retry.delay_for(attempt))
            except Exception as exc:  # noqa: BLE001 - provider boundary
                wrapped = ProviderResponseError(
                    f"{provider.name} {operation} failed unexpectedly: {exc}"
                )
                self._meter.record(
                    provider,
                    operation,
                    success=False,
                    attempts=attempt,
                    units=units,
                    error=str(wrapped),
                    capability=capability,
                )
                raise wrapped from exc
            else:
                self._meter.record(
                    provider,
                    operation,
                    success=True,
                    attempts=attempt,
                    units=units,
                    capability=capability,
                )
                return result
        raise last_error or ProviderResponseError(
            f"{provider.name} {operation} failed without a recorded error"
        )

    def _call_with_timeout(
        self, provider: ProviderDescriptor, operation: str, call: Callable[[], T]
    ) -> T:
        """Run ``call`` in a worker thread and enforce the timeout."""
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="engine-provider")
        future = executor.submit(call)
        try:
            return future.result(timeout=self._retry.timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise ProviderTimeout(
                f"{provider.name} {operation} exceeded "
                f"{self._retry.timeout_seconds:.1f}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
