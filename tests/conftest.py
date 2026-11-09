"""Shared pytest fixtures."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from app.core.settings import Settings
from app.main import create_app
from app.services.queue import InMemoryJobQueue
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def webhook_secret() -> str:
    return "test-webhook-secret"


@pytest.fixture
def settings(webhook_secret: str) -> Settings:
    return Settings(
        APP_ENV="test",
        LOG_LEVEL="WARNING",
        GITHUB_WEBHOOK_SECRET=webhook_secret,
        REDIS_URL="redis://localhost:6379/15",
        DATABASE_URL="postgresql+asyncpg://reviewpilot:reviewpilot@localhost:5432/reviewpilot_test",
    )


@pytest.fixture
def queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def client(settings: Settings, queue: InMemoryJobQueue) -> Iterator[TestClient]:
    app = create_app(settings=settings, queue=queue)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(settings: Settings, queue: InMemoryJobQueue) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=settings, queue=queue)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def make_pr_payload(
    *,
    action: str = "opened",
    owner: str = "acme",
    repo: str = "widgets",
    number: int = 42,
    head_sha: str = "abc123def456",
    installation_id: int | None = 99,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": action,
        "number": number,
        "pull_request": {
            "number": number,
            "head": {"sha": head_sha},
        },
        "repository": {
            "name": repo,
            "owner": {"login": owner},
        },
    }
    if installation_id is not None:
        payload["installation"] = {"id": installation_id}
    return payload


def post_webhook(
    client: TestClient,
    *,
    secret: str,
    payload: dict[str, Any],
    event: str = "pull_request",
    delivery_id: str = "delivery-1",
    signature: str | None = None,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": signature if signature is not None else sign_payload(secret, body),
    }
    return client.post("/webhooks/github", content=body, headers=headers)
