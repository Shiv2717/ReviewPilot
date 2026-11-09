"""Dashboard API tests against in-memory SQLite."""

from __future__ import annotations

import pytest
from app.core.schemas import Finding, Severity
from app.core.settings import Settings
from app.db import repository as repo
from app.db.models import Base
from app.main import create_app
from app.services.queue import InMemoryJobQueue
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def db_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_list_detail_feedback_export(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        pr = await repo.get_or_create_pr(
            session, owner="acme", repo="demo", number=9, installation_id=1
        )
        await repo.save_review_run(
            session,
            pr=pr,
            job_id="j",
            head_sha="abc",
            findings=[
                Finding(
                    file_path="a.py",
                    line_start=1,
                    line_end=1,
                    severity=Severity.HIGH,
                    category="security",
                    title="t",
                    explanation="e",
                    suggested_fix=None,
                    confidence=0.9,
                    agent_name="security",
                )
            ],
            prompt_tokens=10,
            completion_tokens=5,
            agent_latency_ms={"security": 12.0},
            published=True,
        )

    settings = Settings(APP_ENV="test", GITHUB_WEBHOOK_SECRET="s")
    app = create_app(settings=settings, queue=InMemoryJobQueue())
    app.state.session_factory = db_factory
    with TestClient(app) as client:
        prs = client.get("/api/prs")
        assert prs.status_code == 200
        assert len(prs.json()) == 1
        pr_id = prs.json()[0]["id"]
        detail = client.get(f"/api/prs/{pr_id}")
        assert detail.status_code == 200
        finding_id = detail.json()["runs"][0]["findings"][0]["id"]
        fb = client.post(
            "/api/feedback",
            json={"finding_id": finding_id, "action": "accept"},
        )
        assert fb.status_code == 200
        csv_resp = client.get("/api/export/findings.csv")
        assert csv_resp.status_code == 200
        assert "a.py" in csv_resp.text
        missing = client.get("/api/prs/9999")
        assert missing.status_code == 404
