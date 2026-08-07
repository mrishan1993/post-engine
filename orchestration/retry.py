from __future__ import annotations

import functools
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 2,
    backoff_seconds: Sequence[float] = (5, 15),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[F], F]:
    """Retry a function with exponential-style backoff from a fixed schedule.

    max_attempts is the number of *retries* after the first try (PRP §6).
    Total tries = max_attempts + 1.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            total_tries = max_attempts + 1
            for attempt in range(1, total_tries + 1):
                try:
                    return fn(*args, **kwargs, attempt_number=attempt)
                except Exception as exc:  # noqa: BLE001 — pipeline boundary
                    last_exc = exc
                    if attempt < total_tries:
                        wait = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                        sleep(wait)
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
