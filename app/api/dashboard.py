"""Dashboard API: PR list, findings, feedback, CSV export."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.core.schemas import FeedbackAction, FindingFeedback
from app.db import repository as repo
from app.db.session import create_engine, create_session_factory

router = APIRouter(prefix="/api", tags=["dashboard"])


class PROut(BaseModel):
    id: int
    owner: str
    repo: str
    number: int


class FindingOut(BaseModel):
    id: int
    file_path: str
    line_start: int
    line_end: int
    severity: str
    category: str
    title: str
    explanation: str
    confidence: float
    agent_name: str
    feedback: str | None = None


class RunOut(BaseModel):
    id: int
    head_sha: str
    prompt_tokens: int
    completion_tokens: int
    agent_latency_ms: dict[str, Any] | None
    findings: list[FindingOut]


def _session_factory(request: Request) -> Any:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is not None:
        return factory
    settings = request.app.state.settings
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    request.app.state.db_engine = engine
    request.app.state.session_factory = factory
    return factory


@router.get("/prs", response_model=list[PROut])
async def list_prs(request: Request) -> list[PROut]:
    factory = _session_factory(request)
    async with factory() as session:
        prs = await repo.list_pull_requests(session)
    return [PROut(id=p.id, owner=p.owner, repo=p.repo, number=p.number) for p in prs]


@router.get("/prs/{pr_id}", response_model=dict[str, Any])
async def get_pr(
    pr_id: int,
    request: Request,
    severity: str | None = Query(default=None),
) -> dict[str, Any]:
    factory = _session_factory(request)
    async with factory() as session:
        pr, runs = await repo.get_pr_with_runs(session, pr_id)
        if pr is None:
            raise HTTPException(status_code=404, detail="PR not found")
        run_payload: list[RunOut] = []
        for run in runs:
            findings = await repo.list_findings_for_run(session, run.id, severity=severity)
            run_payload.append(
                RunOut(
                    id=run.id,
                    head_sha=run.head_sha,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    agent_latency_ms=run.agent_latency_ms,
                    findings=[
                        FindingOut(
                            id=f.id,
                            file_path=f.file_path,
                            line_start=f.line_start,
                            line_end=f.line_end,
                            severity=f.severity,
                            category=f.category,
                            title=f.title,
                            explanation=f.explanation,
                            confidence=f.confidence,
                            agent_name=f.agent_name,
                            feedback=f.feedback,
                        )
                        for f in findings
                    ],
                )
            )
    return {
        "id": pr.id,
        "owner": pr.owner,
        "repo": pr.repo,
        "number": pr.number,
        "runs": [r.model_dump() for r in run_payload],
    }


@router.post("/feedback")
async def post_feedback(payload: FindingFeedback, request: Request) -> dict[str, str]:
    factory = _session_factory(request)
    async with factory() as session:
        row = await repo.set_finding_feedback(
            session, payload.finding_id, payload.action, payload.note
        )
    if row is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return {"status": "ok", "action": payload.action.value}


@router.get("/export/findings.csv")
async def export_csv(request: Request) -> Response:
    factory = _session_factory(request)
    async with factory() as session:
        csv_data = await repo.export_findings_csv(session)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=findings.csv"},
    )


# Ensure FeedbackAction is referenced for importers / OpenAPI
_ = FeedbackAction
