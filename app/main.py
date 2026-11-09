"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings
from app.services.queue import JobQueue, RedisJobQueue

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    queue: JobQueue = RedisJobQueue.from_settings(settings)
    app.state.queue = queue
    logger.info("app_started", env=settings.app_env)
    try:
        yield
    finally:
        await queue.close()
        logger.info("app_stopped")


def create_app(settings: Settings | None = None, queue: JobQueue | None = None) -> FastAPI:
    """Application factory used by uvicorn and tests."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="ReviewPilot",
        version="0.1.0",
        lifespan=lifespan if queue is None else None,
    )
    app.state.settings = cfg
    if queue is not None:
        app.state.queue = queue

    app.include_router(health_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
