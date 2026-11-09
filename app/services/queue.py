"""Redis job queue for review work."""

from __future__ import annotations

from typing import Any, Protocol

from redis.asyncio import Redis

from app.core.schemas import ReviewJob
from app.core.settings import Settings


class JobQueue(Protocol):
    """Abstract enqueue interface used by the webhook handler."""

    async def enqueue(self, job: ReviewJob) -> None: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class RedisJobQueue:
    """LPUSH-based Redis list queue."""

    def __init__(self, redis: Redis, queue_name: str) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._queue_name = queue_name

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisJobQueue:
        client: Any = Redis.from_url(settings.redis_url, decode_responses=True)
        return cls(client, settings.redis_job_queue)

    async def enqueue(self, job: ReviewJob) -> None:
        await self._redis.lpush(self._queue_name, job.model_dump_json())

    async def dequeue(self, timeout_seconds: int = 5) -> ReviewJob | None:
        result = await self._redis.brpop(self._queue_name, timeout=timeout_seconds)
        if result is None:
            return None
        _, payload = result
        return ReviewJob.model_validate_json(payload)

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def close(self) -> None:
        # redis-py 5+ exposes aclose(); stubs may still only declare close().
        await self._redis.aclose()  # type: ignore[attr-defined]


class InMemoryJobQueue:
    """In-memory queue for tests that do not need Redis."""

    def __init__(self) -> None:
        self.jobs: list[ReviewJob] = []

    async def enqueue(self, job: ReviewJob) -> None:
        self.jobs.append(job)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
