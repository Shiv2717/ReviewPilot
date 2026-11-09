"""Seed a local SQLite DB with sample PR/findings for dashboard demos."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.schemas import Finding, Severity
from app.db import repository as repo
from app.db.models import Base

DB_URL = "sqlite+aiosqlite:///./reviewpilot_demo.db"


async def main() -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        pr = await repo.get_or_create_pr(
            session, owner="acme", repo="payments", number=128, installation_id=1
        )
        await repo.save_review_run(
            session,
            pr=pr,
            job_id="demo-job",
            head_sha="abc123",
            findings=[
                Finding(
                    file_path="api/charges.py",
                    line_start=42,
                    line_end=45,
                    severity=Severity.CRITICAL,
                    category="injection",
                    title="SQL injection via f-string",
                    explanation="User input is interpolated into SQL.",
                    suggested_fix="Use parameterized queries.",
                    confidence=0.96,
                    agent_name="security",
                ),
                Finding(
                    file_path="api/charges.py",
                    line_start=88,
                    line_end=90,
                    severity=Severity.HIGH,
                    category="blocking_async",
                    title="Blocking sleep in async handler",
                    explanation="time.sleep blocks the event loop.",
                    suggested_fix="await asyncio.sleep(...)",
                    confidence=0.91,
                    agent_name="performance",
                ),
                Finding(
                    file_path="services/ledger.py",
                    line_start=15,
                    line_end=20,
                    severity=Severity.MEDIUM,
                    category="race",
                    title="Non-atomic balance update",
                    explanation="Read-modify-write without a lock/transaction.",
                    suggested_fix=None,
                    confidence=0.84,
                    agent_name="correctness",
                ),
            ],
            prompt_tokens=4200,
            completion_tokens=900,
            agent_latency_ms={
                "security": 1200,
                "performance": 980,
                "correctness": 1100,
                "style": 700,
            },
            published=True,
        )
        pr2 = await repo.get_or_create_pr(
            session, owner="acme", repo="payments", number=130, installation_id=1
        )
        await repo.save_review_run(
            session,
            pr=pr2,
            job_id="demo-job-2",
            head_sha="def456",
            findings=[
                Finding(
                    file_path="tests/test_ledger.py",
                    line_start=1,
                    line_end=1,
                    severity=Severity.LOW,
                    category="missing_tests",
                    title="No tests for refund path",
                    explanation="Critical refund logic lacks coverage.",
                    suggested_fix=None,
                    confidence=0.7,
                    agent_name="style",
                )
            ],
            prompt_tokens=800,
            completion_tokens=200,
            agent_latency_ms={"style": 400},
            published=True,
        )
    await engine.dispose()
    print(f"seeded {DB_URL}")


if __name__ == "__main__":
    asyncio.run(main())
