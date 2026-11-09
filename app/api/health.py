"""Liveness and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.core.schemas import HealthResponse, ReadyResponse
from app.services.queue import JobQueue

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness probe — process is up."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(request: Request, response: Response) -> ReadyResponse:
    """Readiness probe — dependencies are reachable."""
    queue: JobQueue = request.app.state.queue
    checks: dict[str, Any] = {}
    try:
        checks["redis"] = "ok" if await queue.ping() else "fail"
    except Exception as exc:  # noqa: BLE001 — readiness should never raise
        checks["redis"] = f"error: {exc}"

    ready = checks.get("redis") == "ok"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ok" if ready else "not_ready", checks=checks)
