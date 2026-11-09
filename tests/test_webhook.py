"""Tests for GitHub webhook signature verification and enqueue behavior."""

from __future__ import annotations

import json

from app.services.queue import InMemoryJobQueue
from fastapi.testclient import TestClient

from tests.conftest import make_pr_payload, post_webhook, sign_payload


def test_valid_signature_enqueues_once(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    payload = make_pr_payload(action="opened")
    response = post_webhook(client, secret=webhook_secret, payload=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert "job_id" in body

    assert len(queue.jobs) == 1
    job = queue.jobs[0]
    assert job.pr.owner == "acme"
    assert job.pr.repo == "widgets"
    assert job.pr.number == 42
    assert job.pr.head_sha == "abc123def456"
    assert job.action == "opened"
    assert job.delivery_id == "delivery-1"


def test_invalid_signature_rejected(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    payload = make_pr_payload()
    response = post_webhook(
        client,
        secret=webhook_secret,
        payload=payload,
        signature="sha256=deadbeef",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid signature"
    assert queue.jobs == []


def test_missing_signature_rejected(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    body = json.dumps(make_pr_payload()).encode("utf-8")
    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-2",
        },
    )

    assert response.status_code == 401
    assert queue.jobs == []
    assert sign_payload(webhook_secret, body).startswith("sha256=")


def test_ignored_event_types_do_not_enqueue(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    payload = make_pr_payload()
    response = post_webhook(
        client,
        secret=webhook_secret,
        payload=payload,
        event="push",
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert queue.jobs == []


def test_ignored_pr_actions_do_not_enqueue(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    for action in ("closed", "edited", "labeled", "assigned"):
        response = post_webhook(
            client,
            secret=webhook_secret,
            payload=make_pr_payload(action=action),
            delivery_id=f"delivery-{action}",
        )
        assert response.status_code == 202
        assert response.json()["status"] == "ignored"

    assert queue.jobs == []


def test_accepted_actions_each_enqueue_once(
    client: TestClient,
    queue: InMemoryJobQueue,
    webhook_secret: str,
) -> None:
    for action in ("opened", "synchronize", "reopened"):
        response = post_webhook(
            client,
            secret=webhook_secret,
            payload=make_pr_payload(action=action),
            delivery_id=f"delivery-{action}",
        )
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"

    assert len(queue.jobs) == 3
    assert [j.action for j in queue.jobs] == ["opened", "synchronize", "reopened"]
