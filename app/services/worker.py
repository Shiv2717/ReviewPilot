"""Worker process: consume Redis jobs and run the review pipeline."""

from __future__ import annotations

import asyncio
import signal

from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.dlq import DeadLetterQueue
from app.services.github_client import GitHubClient
from app.services.llm import FakeLLM, HttpLLMClient
from app.services.pipeline import ReviewPipeline
from app.services.publisher import ReviewPublisher
from app.services.queue import RedisJobQueue

logger = get_logger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    queue = RedisJobQueue.from_settings(settings)
    redis = queue._redis
    dlq = DeadLetterQueue(redis, settings.redis_dlq, settings.redis_job_queue)

    github: GitHubClient | None = None
    http = None
    if settings.github_app_id and settings.github_app_private_key_path:
        github, http = GitHubClient.from_settings(settings)

    if settings.llm_api_key:
        llm: FakeLLM | HttpLLMClient = HttpLLMClient.from_settings(settings)
    else:
        llm = FakeLLM(responses=['{"findings":[]}'])

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    publisher = ReviewPublisher()
    pipeline: ReviewPipeline | None = None
    if github is not None:
        pipeline = ReviewPipeline(
            settings=settings,
            github=github,
            llm=llm,
            publisher=publisher,
            session_factory=session_factory,
        )

    stop = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        logger.info("worker_shutdown_requested")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal())

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
            if pipeline is None:
                logger.info("job_skipped_no_github", job_id=job.job_id)
                continue
            try:
                result = await pipeline.run(job)
                logger.info("job_completed", job_id=job.job_id, **result)
            except Exception as exc:  # noqa: BLE001
                await dlq.push(job, str(exc))
    finally:
        await queue.close()
        if http is not None:
            await http.aclose()
        if isinstance(llm, HttpLLMClient):
            await llm.aclose()
        await engine.dispose()
        logger.info("worker_stopped")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
