"""Shared pacing and narrowly scoped HTTP 429 retry policy for chat endpoints."""

from __future__ import annotations

import random
import time
from typing import Any, Callable


class RateLimitRetriesExhausted(RuntimeError):
    """Raised after the configured number of HTTP 429 retries is exhausted."""


def is_rate_limit_error(exc: Exception) -> bool:
    """Recognize OpenAI RateLimitError or an exception carrying HTTP status 429."""
    try:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
    except ImportError:
        pass
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code == 429


class RateLimitedChatClient:
    """Serialize chat calls with minimum spacing and bounded 429-only retries."""

    def __init__(
        self,
        client: Any,
        request_interval_seconds: float = 2.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.25),
    ) -> None:
        if request_interval_seconds < 0:
            raise ValueError("request interval must be non-negative")
        if max_retries < 0:
            raise ValueError("max retries must be non-negative")
        self._client = client
        self._interval = request_interval_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._last_request_at: float | None = None

    def _pace(self) -> None:
        if self._last_request_at is not None:
            remaining = self._interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def create(self, **kwargs: Any) -> Any:
        attempts = 0
        while True:
            attempts += 1
            self._pace()
            try:
                return self._client.create(**kwargs)
            except Exception as exc:
                if not is_rate_limit_error(exc):
                    raise
                retries_used = attempts - 1
                if retries_used >= self._max_retries:
                    raise RateLimitRetriesExhausted(
                        f"HTTP 429 rate limit after {attempts} attempts: {exc}"
                    ) from exc
                self._sleep((2 ** retries_used) * 2.0 + self._jitter())
