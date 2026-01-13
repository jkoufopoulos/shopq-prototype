# Collection to track invalid JSON rates for LLM outputs
from __future__ import annotations

from collections import deque


class InvalidJSONCircuitBreaker:
    def __init__(self, window: int = 1000, threshold: float = 0.01) -> None:
        self.window = window
        self.threshold = threshold
        self._events: deque[bool] = deque(maxlen=window)

    def record(self, success: bool) -> None:
        """record implementation.

        Side Effects:
            None (pure function)
        """

        self._events.append(success)

    def invalid_rate(self) -> float:
        if not self._events:
            return 0.0
        invalid = self._events.count(False)
        return invalid / len(self._events)

    def is_tripped(self) -> bool:
        return self.invalid_rate() >= self.threshold

    def reset(self) -> None:
        """Reset circuit breaker state.

        Side Effects:
            Clears all recorded events from the circuit breaker.
        """
        self._events.clear()
