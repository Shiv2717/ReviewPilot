"""Unit tests for webhook parsing helpers."""

from __future__ import annotations

import pytest
from app.services.webhook import (
    IgnoredEventError,
    WebhookVerificationError,
    parse_pull_request_event,
    verify_signature,
)

from tests.conftest import make_pr_payload, sign_payload


def test_verify_signature_accepts_valid() -> None:
    body = b'{"ok": true}'
    secret = "s3cret"
    verify_signature(
        secret=secret,
        body=body,
        signature_header=sign_payload(secret, body),
    )


def test_verify_signature_rejects_mismatch() -> None:
    with pytest.raises(WebhookVerificationError, match="signature mismatch"):
        verify_signature(
            secret="s3cret",
            body=b"{}",
            signature_header="sha256=00",
        )


def test_parse_requires_delivery_id() -> None:
    with pytest.raises(IgnoredEventError, match="missing X-GitHub-Delivery"):
        parse_pull_request_event(
            event_type="pull_request",
            delivery_id=None,
            payload=make_pr_payload(),
        )


def test_parse_extracts_installation_id() -> None:
    event = parse_pull_request_event(
        event_type="pull_request",
        delivery_id="d1",
        payload=make_pr_payload(installation_id=123),
    )
    assert event.installation_id == 123
    assert event.owner == "acme"
