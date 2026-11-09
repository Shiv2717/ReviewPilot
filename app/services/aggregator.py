"""Deduplicate, rank, threshold, and cap findings."""

from __future__ import annotations

from app.core.schemas import Finding, Severity

SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Keep the highest-confidence finding among overlapping same-file/category groups."""
    kept: list[Finding] = []
    for finding in sorted(findings, key=lambda f: f.confidence, reverse=True):
        duplicate = False
        for existing in kept:
            if (
                existing.file_path == finding.file_path
                and existing.category == finding.category
                and ranges_overlap(
                    existing.line_start,
                    existing.line_end,
                    finding.line_start,
                    finding.line_end,
                )
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(finding)
    return kept


def rank_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK[f.severity], -f.confidence, f.file_path, f.line_start),
    )


def aggregate_findings(
    findings: list[Finding],
    *,
    confidence_threshold: float,
    max_comments: int,
) -> list[Finding]:
    filtered = [f for f in findings if f.confidence >= confidence_threshold]
    deduped = dedupe_findings(filtered)
    ranked = rank_findings(deduped)
    return ranked[:max_comments]
