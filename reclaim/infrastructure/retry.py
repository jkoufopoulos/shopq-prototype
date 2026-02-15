"""
Retry helpers with exponential backoff, jitter, and circuit breaker.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from reclaim.observability.telemetry import counter, log_event

T = TypeVar("T")


class AdapterError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class RetryPolicy:
    stage: str
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 5.0
    jitter: float = 0.1
    timeout_seconds: float = 10.0
    sleep_fn: Callable[[float], None] = time.sleep

    def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """execute implementation.

        Side Effects:
            None (pure function)
        """

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.max_attempts:
            attempt += 1
            try:
                return func(*args, **kwargs)
            except AdapterError as exc:
                if not self._should_retry(exc):
                    log_event(
                        "stage_error",
                        stage=self.stage,
                        error=str(exc),
                        status=exc.status_code,
                        attempt=attempt,
                    )
                    raise
                last_error = exc
            except Exception as exc:
                last_error = exc
                log_event("stage_error", stage=self.stage, error=str(exc), attempt=attempt)

            if attempt >= self.max_attempts:
                break

            self._backoff(attempt)

        assert last_error is not None
        raise last_error

    def _should_retry(self, exc: AdapterError) -> bool:
        status = exc.status_code
        if status is None:
            return True
        return bool(status == 429 or 500 <= status < 600)

    def _backoff(self, attempt: int) -> None:
        counter("retry_count")
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        delay += random.uniform(0, self.jitter)
        log_event("retry_scheduled", stage=self.stage, attempt=attempt, delay=round(delay, 3))
        if self.sleep_fn is not None:
            self.sleep_fn(delay)


@dataclass
class CircuitBreaker:
    stage: str
    fail_max: int = 5
    reset_timeout: float = 60.0
    _failures: int = field(default=0, init=False)
    _state: str = field(default="closed", init=False)
    _opened_at: float = field(default=0.0, init=False)

    def allow_request(self) -> bool:
        if self._state == "open":
            if time.time() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
                self._failures = 0
                return True
            counter("circuit_open_rate")
            log_event("circuit.open", stage=self.stage)
            return False
        return True

    def record_success(self) -> None:
        """record_success implementation.

        Side Effects:
            None (pure function)
        """

        self._failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """record_failure implementation.

        Side Effects:
            None (pure function)
        """

        self._failures += 1
        if self._failures >= self.fail_max:
            self._state = "open"
            self._opened_at = time.time()
            counter("circuit_open_rate")
            log_event("circuit.opened", stage=self.stage, failures=self._failures)
