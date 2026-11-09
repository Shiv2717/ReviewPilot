"""GitHub webhook receiver."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.schemas import PullRequestRef, ReviewJob
from app.core.settings import Settings
from app.services.queue import JobQueue
from app.services.webhook import (
    IgnoredEventError,
    WebhookVerificationError,
    parse_pull_request_event,
    verify_signature,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


class EnqueueAccepted(BaseModel):
    status: str = "accepted"
    job_id: str


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    response: Response,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> EnqueueAccepted | dict[str, str]:
    """Verify signature, filter events, enqueue a review job, return 202."""
    settings: Settings = request.app.state.settings
    queue: JobQueue = request.app.state.queue
    body = await request.body()

    try:
        verify_signature(
            secret=settings.github_webhook_secret,
            body=body,
            signature_header=x_hub_signature_256,
        )
    except WebhookVerificationError as exc:
        logger.warning("webhook_signature_invalid", error=str(exc), delivery_id=x_github_delivery)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        ) from exc

    payload = _parse_json(body)

    try:
        event = parse_pull_request_event(
            event_type=x_github_event,
            delivery_id=x_github_delivery,
            payload=payload,
        )
    except IgnoredEventError as exc:
        logger.info(
            "webhook_ignored",
            reason=str(exc),
            github_event=x_github_event,
            delivery_id=x_github_delivery,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return {"status": "ignored", "reason": str(exc)}

    job = ReviewJob(
        job_id=str(uuid.uuid4()),
        delivery_id=event.delivery_id,
        action=event.action,
        pr=PullRequestRef(
            owner=event.owner,
            repo=event.repo,
            number=event.number,
            head_sha=event.head_sha,
            installation_id=event.installation_id,
        ),
        received_at=datetime.now(UTC).isoformat(),
    )

    await queue.enqueue(job)
    logger.info(
        "review_job_enqueued",
        job_id=job.job_id,
        delivery_id=job.delivery_id,
        owner=job.pr.owner,
        repo=job.pr.repo,
        number=job.pr.number,
        head_sha=job.pr.head_sha,
        action=job.action,
    )
    return EnqueueAccepted(job_id=job.job_id)


def _parse_json(body: bytes) -> dict[str, Any]:
    """Parse JSON from raw body bytes (signature already verified on these bytes)."""
    import json

    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid JSON body",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON body must be an object",
        )
    return data
