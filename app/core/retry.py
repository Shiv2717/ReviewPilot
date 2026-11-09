"""Async retry with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable


async def with_backoff[T](
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.25,
    max_delay: float = 8.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call `fn` with exponential backoff + full jitter on selected errors."""
    attempt = 0
    while True:
        try:
            return await fn()
        except retry_on as exc:
            if attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            delay = random.uniform(0, delay)
            await asyncio.sleep(delay)
            attempt += 1
            _ = exc
