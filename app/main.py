"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.webhooks import router as webhooks_router
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.services.queue import InMemoryJobQueue, JobQueue, RedisJobQueue

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    if getattr(app.state, "queue", None) is None:
        if settings.redis_url.startswith("memory://"):
            app.state.queue = InMemoryJobQueue()
        else:
            app.state.queue = RedisJobQueue.from_settings(settings)
    queue: JobQueue = app.state.queue
    engine = create_engine(settings)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    logger.info("app_started", env=settings.app_env)
    try:
        yield
    finally:
        await queue.close()
        await engine.dispose()
        logger.info("app_stopped")


def create_app(settings: Settings | None = None, queue: JobQueue | None = None) -> FastAPI:
    """Application factory used by uvicorn and tests."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="ReviewPilot",
        version="0.1.0",
        lifespan=None if queue is not None else lifespan,
    )
    app.state.settings = cfg
    if queue is not None:
        app.state.queue = queue

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(metrics_router)
    app.include_router(dashboard_router)

    dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")
    return app


app = create_app()
