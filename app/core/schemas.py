"""Shared Pydantic schemas used across API and services."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    """A single review finding produced by an agent."""

    file_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: Severity
    category: str
    title: str
    explanation: str
    suggested_fix: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    agent_name: str


class PullRequestRef(BaseModel):
    """Minimal PR identity carried on review jobs."""

    owner: str
    repo: str
    number: int
    head_sha: str
    installation_id: int | None = None


class ReviewJob(BaseModel):
    """Job payload enqueued after an accepted webhook event."""

    job_id: str
    delivery_id: str
    action: str
    pr: PullRequestRef
    received_at: str


class DiffHunk(BaseModel):
    """One unified-diff hunk with old/new line numbering."""

    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]
    # Maps 0-based index in `lines` -> new-file line number (None for deletions)
    new_line_numbers: list[int | None]
    old_line_numbers: list[int | None]


class DiffFile(BaseModel):
    """A single changed file from the PR."""

    filename: str
    status: str
    previous_filename: str | None = None
    patch: str | None = None
    hunks: list[DiffHunk] = Field(default_factory=list)
    ignored: bool = False
    ignore_reason: str | None = None


class DiffChunk(BaseModel):
    """Token-budgeted slice of a diff sent to agents."""

    chunk_id: str
    file_path: str
    status: str
    hunks: list[DiffHunk]
    estimated_tokens: int
    content: str


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, Any] = Field(default_factory=dict)


class FeedbackAction(StrEnum):
    ACCEPT = "accept"
    DISMISS = "dismiss"


class FindingFeedback(BaseModel):
    finding_id: int
    action: FeedbackAction
    note: str | None = None
