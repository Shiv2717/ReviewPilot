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


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, Any] = Field(default_factory=dict)
