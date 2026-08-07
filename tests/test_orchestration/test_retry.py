from __future__ import annotations

import pytest

from orchestration.retry import retry


def test_retry_eventually_succeeds() -> None:
    calls = {"n": 0}

    @retry(max_attempts=2, backoff_seconds=(0, 0))
    def flaky(attempt_number: int = 1) -> str:
        calls["n"] += 1
        if attempt_number < 3:
            raise RuntimeError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_exhausted() -> None:
    @retry(max_attempts=1, backoff_seconds=(0,))
    def always_fail(attempt_number: int = 1) -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        always_fail()
