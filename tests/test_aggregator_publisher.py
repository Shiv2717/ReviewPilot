"""Tests for aggregation, position mapping, and publish idempotency."""

from __future__ import annotations

from typing import Any

import pytest
from app.core.schemas import DiffFile, DiffHunk, Finding, Severity
from app.services.aggregator import aggregate_findings, dedupe_findings, rank_findings
from app.services.publisher import ReviewPublisher


def _finding(
    *,
    file: str = "a.py",
    start: int = 1,
    end: int = 1,
    severity: Severity = Severity.HIGH,
    category: str = "security",
    confidence: float = 0.9,
    title: str = "issue",
) -> Finding:
    return Finding(
        file_path=file,
        line_start=start,
        line_end=end,
        severity=severity,
        category=category,
        title=title,
        explanation="x",
        suggested_fix=None,
        confidence=confidence,
        agent_name="security",
    )


def test_dedupe_overlapping_same_category() -> None:
    a = _finding(confidence=0.95, title="better")
    b = _finding(confidence=0.5, title="worse")
    out = dedupe_findings([b, a])
    assert len(out) == 1
    assert out[0].title == "better"


def test_rank_by_severity_then_confidence() -> None:
    findings = [
        _finding(severity=Severity.LOW, confidence=0.99, title="low"),
        _finding(severity=Severity.CRITICAL, confidence=0.5, title="crit"),
        _finding(severity=Severity.HIGH, confidence=0.9, title="high"),
    ]
    ranked = rank_findings(findings)
    assert [f.title for f in ranked] == ["crit", "high", "low"]


def test_aggregate_threshold_and_cap() -> None:
    findings = [
        _finding(confidence=0.2, title="drop"),
        _finding(confidence=0.9, title="keep1", start=1),
        _finding(confidence=0.8, title="keep2", start=10, category="perf"),
        _finding(confidence=0.7, title="keep3", start=20, category="style"),
    ]
    out = aggregate_findings(findings, confidence_threshold=0.5, max_comments=2)
    assert len(out) == 2
    assert all(f.confidence >= 0.5 for f in out)


def test_position_mapping() -> None:
    files = [
        DiffFile(
            filename="a.py",
            status="modified",
            hunks=[
                DiffHunk(
                    header="@@ -1,1 +1,2 @@",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=2,
                    lines=["-a", "+b", "+c"],
                    new_line_numbers=[None, 1, 2],
                    old_line_numbers=[1, None, None],
                )
            ],
        )
    ]
    pub = ReviewPublisher()
    assert pub.map_position(_finding(start=2), files) == 2
    assert pub.map_position(_finding(file="missing.py", start=1), files) is None


@pytest.mark.asyncio
async def test_publish_idempotent() -> None:
    calls: list[Any] = []

    class FakeGH:
        async def create_review(self, *args: Any, **kwargs: Any) -> dict[str, str]:
            calls.append(kwargs)
            return {"id": "1"}

    files = [
        DiffFile(
            filename="a.py",
            status="modified",
            hunks=[
                DiffHunk(
                    header="@@ -1 +1 @@",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=["+b"],
                    new_line_numbers=[1],
                    old_line_numbers=[None],
                )
            ],
        )
    ]
    pub = ReviewPublisher()
    gh = FakeGH()
    r1 = await pub.publish(
        gh,  # type: ignore[arg-type]
        owner="o",
        repo="r",
        number=1,
        head_sha="abc",
        installation_id=1,
        findings=[_finding()],
        files=files,
    )
    r2 = await pub.publish(
        gh,  # type: ignore[arg-type]
        owner="o",
        repo="r",
        number=1,
        head_sha="abc",
        installation_id=1,
        findings=[_finding()],
        files=files,
    )
    assert r1 is not None
    assert r2 is None
    assert len(calls) == 1
