"""Coverage tests for LLM circuit breaker, pipeline, DLQ, metrics."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.core.metrics import metrics_payload
from app.core.schemas import DiffFile, Finding, PullRequestRef, ReviewJob, Severity
from app.core.settings import Settings
from app.db.models import Base
from app.main import create_app
from app.services.dlq import DeadLetterQueue
from app.services.llm import CircuitBreaker, CircuitOpenError, FakeLLM
from app.services.pipeline import ReviewPipeline
from app.services.publisher import ReviewPublisher
from app.services.queue import InMemoryJobQueue
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def test_circuit_breaker_opens() -> None:
    br = CircuitBreaker(failure_threshold=2, reset_seconds=60)
    br.record_failure()
    br.record_failure()
    with pytest.raises(CircuitOpenError):
        br.before_call()
    br.record_success()
    br.before_call()


def test_metrics_payload_bytes() -> None:
    assert b"reviewpilot" in metrics_payload() or b"#" in metrics_payload()


@pytest.mark.asyncio
async def test_dlq_push_and_replay() -> None:
    class MemRedis:
        def __init__(self) -> None:
            self.data: dict[str, list[str]] = {}

        async def lpush(self, key: str, value: str) -> int:
            self.data.setdefault(key, []).insert(0, value)
            return len(self.data[key])

        async def rpop(self, key: str) -> str | None:
            items = self.data.get(key) or []
            if not items:
                return None
            return items.pop()

        async def llen(self, key: str) -> int:
            return len(self.data.get(key) or [])

    redis = MemRedis()
    dlq = DeadLetterQueue(redis, "dlq", "jobs")  # type: ignore[arg-type]
    job = ReviewJob(
        job_id="j1",
        delivery_id="d1",
        action="opened",
        pr=PullRequestRef(owner="o", repo="r", number=1, head_sha="abc"),
        received_at="2026-01-01T00:00:00Z",
    )
    await dlq.push(job, "boom")
    assert await dlq.size() == 1
    assert await dlq.replay(limit=10) == 1
    assert redis.data["jobs"]


@pytest.mark.asyncio
async def test_pipeline_with_fake_github_and_sqlite(tmp_path: Any) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    class FakeGH:
        async def list_pull_files(self, *args: Any, **kwargs: Any) -> list[DiffFile]:
            return [
                DiffFile(
                    filename="app.py",
                    status="modified",
                    patch="@@ -1,1 +1,2 @@\n def x():\n+    API_KEY='sk-test'\n",
                )
            ]

        async def create_review(self, *args: Any, **kwargs: Any) -> dict[str, str]:
            return {"id": "1"}

    finding = Finding(
        file_path="app.py",
        line_start=2,
        line_end=2,
        severity=Severity.HIGH,
        category="secrets",
        title="secret",
        explanation="key",
        suggested_fix=None,
        confidence=0.9,
        agent_name="security",
    )
    llm = FakeLLM(
        [
            json.dumps({"findings": [finding.model_dump()]}),
            json.dumps({"findings": []}),
            json.dumps({"findings": []}),
            json.dumps({"findings": []}),
        ]
    )
    settings = Settings(
        APP_ENV="test",
        GITHUB_WEBHOOK_SECRET="x",
        GITHUB_APP_INSTALLATION_ID="7",
        CONFIDENCE_THRESHOLD=0.5,
        MAX_COMMENTS_PER_PR=10,
        AGENT_CONCURRENCY=4,
        AGENT_TIMEOUT_SECONDS=5,
        TOKEN_BUDGET_PER_CHUNK=4000,
    )
    pipeline = ReviewPipeline(
        settings=settings,
        github=FakeGH(),  # type: ignore[arg-type]
        llm=llm,
        publisher=ReviewPublisher(),
        session_factory=factory,
    )
    job = ReviewJob(
        job_id="job-1",
        delivery_id="d",
        action="opened",
        pr=PullRequestRef(
            owner="acme", repo="demo", number=3, head_sha="deadbeef", installation_id=7
        ),
        received_at="2026-01-01T00:00:00Z",
    )
    result = await pipeline.run(job)
    assert result["status"] == "ok"
    assert result["findings"] >= 1
    # second run same sha should be idempotent via DB published flag
    result2 = await pipeline.run(job)
    assert result2["status"] == "idempotent"
    await engine.dispose()


def test_metrics_endpoint() -> None:
    settings = Settings(APP_ENV="test", GITHUB_WEBHOOK_SECRET="s")
    app = create_app(settings=settings, queue=InMemoryJobQueue())
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
