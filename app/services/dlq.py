"""Dead-letter queue helpers and replay CLI."""

from __future__ import annotations

import argparse
import asyncio

from redis.asyncio import Redis

from app.core.logging import configure_logging, get_logger
from app.core.schemas import ReviewJob
from app.core.settings import get_settings

logger = get_logger(__name__)


class DeadLetterQueue:
    def __init__(self, redis: Redis, dlq_name: str, job_queue: str) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._dlq_name = dlq_name
        self._job_queue = job_queue

    async def push(self, job: ReviewJob, error: str) -> None:
        payload = job.model_dump()
        payload["error"] = error
        await self._redis.lpush(self._dlq_name, ReviewJob.model_validate(job).model_dump_json())
        await self._redis.lpush(f"{self._dlq_name}:errors", error)
        logger.error("job_dead_lettered", job_id=job.job_id, error=error)

    async def replay(self, limit: int = 100) -> int:
        count = 0
        for _ in range(limit):
            raw = await self._redis.rpop(self._dlq_name)
            if raw is None:
                break
            await self._redis.lpush(self._job_queue, raw)
            count += 1
        logger.info("dlq_replayed", count=count)
        return count

    async def size(self) -> int:
        return int(await self._redis.llen(self._dlq_name))


async def _async_main(limit: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    dlq = DeadLetterQueue(redis, settings.redis_dlq, settings.redis_job_queue)
    n = await dlq.replay(limit=limit)
    print(f"replayed {n} jobs")
    await redis.aclose()  # type: ignore[attr-defined]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay ReviewPilot DLQ jobs")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(_async_main(args.limit))


if __name__ == "__main__":
    main()
