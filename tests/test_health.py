"""Tests for health and readiness endpoints."""

from __future__ import annotations

from app.core.settings import Settings
from app.main import create_app
from app.services.queue import InMemoryJobQueue, JobQueue
from fastapi.testclient import TestClient


class FailingQueue(InMemoryJobQueue):
    async def ping(self) -> bool:
        raise RuntimeError("redis down")


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_ok(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_readyz_fails_when_redis_unreachable(settings: Settings) -> None:
    queue: JobQueue = FailingQueue()
    app = create_app(settings=settings, queue=queue)
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "error" in body["checks"]["redis"]
