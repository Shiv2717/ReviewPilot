"""Prometheus metrics for ReviewPilot."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest

JOBS_TOTAL = Counter(
    "reviewpilot_jobs_total",
    "Review jobs processed",
    ["status"],
)
JOB_DURATION = Histogram(
    "reviewpilot_job_duration_seconds",
    "End-to-end review job duration",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
AGENT_LATENCY = Histogram(
    "reviewpilot_agent_latency_seconds",
    "Per-agent review latency",
    ["agent"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
LLM_TOKENS = Counter(
    "reviewpilot_llm_tokens_total",
    "LLM tokens consumed",
    ["direction"],
)
FINDINGS_TOTAL = Counter(
    "reviewpilot_findings_total",
    "Findings produced",
    ["severity"],
)


def metrics_payload() -> bytes:
    return generate_latest()
