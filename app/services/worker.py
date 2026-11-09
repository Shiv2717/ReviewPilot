"""Worker process stub — Phase 1 only logs dequeued jobs."""

from __future__ import annotations

import asyncio
import signal

from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.services.queue import RedisJobQueue

logger = get_logger(__name__)


async def run_worker() -> None:
    """Consume review jobs and log them (diff processing arrives in Phase 2)."""
    settings = get_settings()
    configure_logging(settings.log_level)
    queue = RedisJobQueue.from_settings(settings)
    stop = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        logger.info("worker_shutdown_requested")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    logger.info("worker_started", queue=settings.redis_job_queue)
    try:
        while not stop.is_set():
            job = await queue.dequeue(timeout_seconds=1)
            if job is None:
                continue
            logger.info(
                "job_received",
                job_id=job.job_id,
                owner=job.pr.owner,
                repo=job.pr.repo,
                number=job.pr.number,
                head_sha=job.pr.head_sha,
            )
    finally:
        await queue.close()
        logger.info("worker_stopped")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
