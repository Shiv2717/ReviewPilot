"""Persistence helpers for review runs and feedback."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import FeedbackAction, Finding
from app.db.models import FindingRow, PullRequest, ReviewRun


async def get_or_create_pr(
    session: AsyncSession,
    *,
    owner: str,
    repo: str,
    number: int,
    installation_id: int | None,
) -> PullRequest:
    result = await session.execute(
        select(PullRequest).where(
            PullRequest.owner == owner,
            PullRequest.repo == repo,
            PullRequest.number == number,
        )
    )
    pr = result.scalar_one_or_none()
    if pr:
        return pr
    pr = PullRequest(owner=owner, repo=repo, number=number, installation_id=installation_id)
    session.add(pr)
    await session.flush()
    return pr


async def find_run_by_commit(
    session: AsyncSession, *, owner: str, repo: str, number: int, head_sha: str
) -> ReviewRun | None:
    result = await session.execute(
        select(ReviewRun).where(
            ReviewRun.owner == owner,
            ReviewRun.repo == repo,
            ReviewRun.number == number,
            ReviewRun.head_sha == head_sha,
        )
    )
    return result.scalar_one_or_none()


async def save_review_run(
    session: AsyncSession,
    *,
    pr: PullRequest,
    job_id: str,
    head_sha: str,
    findings: list[Finding],
    prompt_tokens: int,
    completion_tokens: int,
    agent_latency_ms: dict[str, float],
    published: bool,
) -> ReviewRun:
    run = ReviewRun(
        pull_request_id=pr.id,
        owner=pr.owner,
        repo=pr.repo,
        number=pr.number,
        head_sha=head_sha,
        job_id=job_id,
        status="completed",
        published=1 if published else 0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        agent_latency_ms=agent_latency_ms,
    )
    session.add(run)
    await session.flush()
    for finding in findings:
        session.add(
            FindingRow(
                run_id=run.id,
                file_path=finding.file_path,
                line_start=finding.line_start,
                line_end=finding.line_end,
                severity=finding.severity.value,
                category=finding.category,
                title=finding.title,
                explanation=finding.explanation,
                suggested_fix=finding.suggested_fix,
                confidence=finding.confidence,
                agent_name=finding.agent_name,
            )
        )
    await session.commit()
    await session.refresh(run)
    return run


async def list_pull_requests(session: AsyncSession, limit: int = 50) -> list[PullRequest]:
    result = await session.execute(select(PullRequest).order_by(PullRequest.id.desc()).limit(limit))
    return list(result.scalars().all())


async def get_pr_with_runs(
    session: AsyncSession, pr_id: int
) -> tuple[PullRequest | None, list[ReviewRun]]:
    pr = await session.get(PullRequest, pr_id)
    if not pr:
        return None, []
    result = await session.execute(
        select(ReviewRun).where(ReviewRun.pull_request_id == pr_id).order_by(ReviewRun.id.desc())
    )
    return pr, list(result.scalars().all())


async def list_findings_for_run(
    session: AsyncSession, run_id: int, *, severity: str | None = None
) -> list[FindingRow]:
    stmt = select(FindingRow).where(FindingRow.run_id == run_id)
    if severity:
        stmt = stmt.where(FindingRow.severity == severity)
    result = await session.execute(stmt.order_by(FindingRow.id))
    return list(result.scalars().all())


async def set_finding_feedback(
    session: AsyncSession, finding_id: int, action: FeedbackAction, note: str | None
) -> FindingRow | None:
    finding = await session.get(FindingRow, finding_id)
    if not finding:
        return None
    await session.execute(
        update(FindingRow)
        .where(FindingRow.id == finding_id)
        .values(feedback=action.value, feedback_note=note)
    )
    await session.commit()
    await session.refresh(finding)
    return finding


async def export_findings_csv(session: AsyncSession) -> str:
    result = await session.execute(select(FindingRow).order_by(FindingRow.id))
    rows = list(result.scalars().all())
    lines = [
        "id,run_id,file_path,line_start,line_end,severity,category,title,confidence,agent_name,feedback"
    ]
    for r in rows:
        title = r.title.replace('"', "'")
        lines.append(
            f'{r.id},{r.run_id},"{r.file_path}",{r.line_start},{r.line_end},{r.severity},'
            f'{r.category},"{title}",{r.confidence},{r.agent_name},{r.feedback or ""}'
        )
    return "\n".join(lines) + "\n"
