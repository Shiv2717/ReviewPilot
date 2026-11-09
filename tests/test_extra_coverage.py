"""Extra coverage for repository helpers."""

from __future__ import annotations

import pytest
from app.core.schemas import FeedbackAction
from app.db import repository as repo
from app.db.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_repo_helpers_empty_and_missing() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        assert await repo.list_pull_requests(session) == []
        pr, runs = await repo.get_pr_with_runs(session, 123)
        assert pr is None and runs == []
        missing = await repo.set_finding_feedback(session, 999, FeedbackAction.DISMISS, None)
        assert missing is None
        csv = await repo.export_findings_csv(session)
        assert csv.startswith("id,")
        a = await repo.get_or_create_pr(
            session, owner="o", repo="r", number=1, installation_id=None
        )
        b = await repo.get_or_create_pr(
            session, owner="o", repo="r", number=1, installation_id=None
        )
        assert a.id == b.id
    await engine.dispose()
