"""GitHub webhook signature verification and event filtering."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from pydantic import BaseModel, Field

ACCEPTED_PR_ACTIONS: frozenset[str] = frozenset({"opened", "synchronize", "reopened"})


class WebhookVerificationError(ValueError):
    """Raised when the webhook signature is missing or invalid."""


class IgnoredEventError(ValueError):
    """Raised when the event type/action should not be processed."""


class ParsedPullRequestEvent(BaseModel):
    """Normalized fields extracted from a pull_request webhook payload."""

    action: str
    delivery_id: str
    owner: str
    repo: str
    number: int
    head_sha: str
    installation_id: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


def verify_signature(*, secret: str, body: bytes, signature_header: str | None) -> None:
    """Verify X-Hub-Signature-256 using a constant-time compare."""
    if not secret:
        raise WebhookVerificationError("webhook secret is not configured")
    if not signature_header or not signature_header.startswith("sha256="):
        raise WebhookVerificationError("missing or malformed signature header")

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise WebhookVerificationError("signature mismatch")


def parse_pull_request_event(
    *,
    event_type: str | None,
    delivery_id: str | None,
    payload: dict[str, Any],
) -> ParsedPullRequestEvent:
    """Accept only pull_request opened/synchronize/reopened events."""
    if event_type != "pull_request":
        raise IgnoredEventError(f"ignored event type: {event_type!r}")

    action = str(payload.get("action", ""))
    if action not in ACCEPTED_PR_ACTIONS:
        raise IgnoredEventError(f"ignored pull_request action: {action!r}")

    if not delivery_id:
        raise IgnoredEventError("missing X-GitHub-Delivery header")

    pr = payload.get("pull_request")
    repo = payload.get("repository")
    if not isinstance(pr, dict) or not isinstance(repo, dict):
        raise IgnoredEventError("malformed pull_request payload")

    owner_login = _nested_str(repo, "owner", "login")
    repo_name = str(repo.get("name", ""))
    number = pr.get("number")
    head_sha = _nested_str(pr, "head", "sha")
    if not owner_login or not repo_name or not isinstance(number, int) or not head_sha:
        raise IgnoredEventError("incomplete pull_request identity")

    installation = payload.get("installation")
    installation_id: int | None = None
    if isinstance(installation, dict) and isinstance(installation.get("id"), int):
        installation_id = installation["id"]

    return ParsedPullRequestEvent(
        action=action,
        delivery_id=delivery_id,
        owner=owner_login,
        repo=repo_name,
        number=number,
        head_sha=head_sha,
        installation_id=installation_id,
        raw=payload,
    )


def _nested_str(data: dict[str, Any], *keys: str) -> str:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current) if current else ""
