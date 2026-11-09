"""Backoff helper tests."""

from __future__ import annotations

import pytest
from app.core.retry import with_backoff


@pytest.mark.asyncio
async def test_backoff_retries_then_succeeds() -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("nope")
        return "ok"

    assert await with_backoff(flaky, retries=3, base_delay=0.001, max_delay=0.01) == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_backoff_gives_up() -> None:
    async def always_fail() -> None:
        raise ValueError("x")

    with pytest.raises(ValueError):
        await with_backoff(always_fail, retries=1, base_delay=0.001, retry_on=(ValueError,))
