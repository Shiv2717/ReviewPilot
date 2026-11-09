"""End-to-end review pipeline for a single job."""

from __future__ import annotations

import time
from typing import Any

from agents.runner import default_agents, review_chunks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.metrics import (
    AGENT_LATENCY,
    FINDINGS_TOTAL,
    JOB_DURATION,
    JOBS_TOTAL,
    LLM_TOKENS,
)
from app.core.schemas import DiffFile, ReviewJob
from app.core.settings import Settings
from app.db import repository as repo
from app.services.aggregator import aggregate_findings
from app.services.diff_processor import process_pull_files, should_ignore_file
from app.services.github_client import GitHubClient
from app.services.llm import LLMClient
from app.services.publisher import ReviewPublisher
from app.services.repo_config import parse_repo_config, path_is_ignored, severity_at_least

logger = get_logger(__name__)


class ReviewPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        github: GitHubClient,
        llm: LLMClient,
        publisher: ReviewPublisher,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        repo_config_raw: str | None = None,
    ) -> None:
        self.settings = settings
        self.github = github
        self.llm = llm
        self.publisher = publisher
        self.session_factory = session_factory
        self.repo_config = parse_repo_config(repo_config_raw)

    async def run(self, job: ReviewJob) -> dict[str, Any]:
        started = time.perf_counter()
        pr = job.pr
        installation_id = pr.installation_id or int(self.settings.github_app_installation_id or "0")
        try:
            if self.session_factory is not None:
                async with self.session_factory() as session:
                    existing = await repo.find_run_by_commit(
                        session,
                        owner=pr.owner,
                        repo=pr.repo,
                        number=pr.number,
                        head_sha=pr.head_sha,
                    )
                    if existing and existing.published:
                        JOBS_TOTAL.labels(status="idempotent").inc()
                        return {"status": "idempotent", "run_id": existing.id}

            files = await self.github.list_pull_files(
                pr.owner, pr.repo, pr.number, installation_id=installation_id
            )
            files = self._apply_repo_ignores(files)
            chunks = process_pull_files(files, token_budget=self.settings.token_budget_per_chunk)
            logger.info(
                "chunks_ready",
                job_id=job.job_id,
                files=len(files),
                chunks=len(chunks),
            )

            agents = default_agents(self.llm, self.repo_config.enabled_agents)
            agent_started = time.perf_counter()
            raw_findings = await review_chunks(
                chunks,
                agents,
                concurrency=self.settings.agent_concurrency,
                timeout_seconds=self.settings.agent_timeout_seconds,
            )
            agent_ms = (time.perf_counter() - agent_started) * 1000
            for agent in agents:
                AGENT_LATENCY.labels(agent=agent.name).observe(agent_ms / max(len(agents), 1))

            conf = (
                self.repo_config.confidence_threshold
                if self.repo_config.confidence_threshold is not None
                else self.settings.confidence_threshold
            )
            cap = (
                self.repo_config.max_comments
                if self.repo_config.max_comments is not None
                else self.settings.max_comments_per_pr
            )
            findings = aggregate_findings(raw_findings, confidence_threshold=conf, max_comments=cap)
            findings = [
                f
                for f in findings
                if severity_at_least(f.severity.value, self.repo_config.severity_threshold)
            ]
            for f in findings:
                FINDINGS_TOTAL.labels(severity=f.severity.value).inc()

            usage = self.llm.total_usage
            LLM_TOKENS.labels(direction="prompt").inc(usage.prompt_tokens)
            LLM_TOKENS.labels(direction="completion").inc(usage.completion_tokens)

            published = False
            if installation_id and not self.publisher.already_posted(
                pr.owner, pr.repo, pr.number, pr.head_sha
            ):
                await self.publisher.publish(
                    self.github,
                    owner=pr.owner,
                    repo=pr.repo,
                    number=pr.number,
                    head_sha=pr.head_sha,
                    installation_id=installation_id,
                    findings=findings,
                    files=files,
                )
                published = True

            run_id = None
            if self.session_factory is not None:
                async with self.session_factory() as session:
                    db_pr = await repo.get_or_create_pr(
                        session,
                        owner=pr.owner,
                        repo=pr.repo,
                        number=pr.number,
                        installation_id=pr.installation_id,
                    )
                    run = await repo.save_review_run(
                        session,
                        pr=db_pr,
                        job_id=job.job_id,
                        head_sha=pr.head_sha,
                        findings=findings,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        agent_latency_ms={a.name: agent_ms for a in agents},
                        published=published,
                    )
                    run_id = run.id

            JOBS_TOTAL.labels(status="ok").inc()
            JOB_DURATION.observe(time.perf_counter() - started)
            return {
                "status": "ok",
                "findings": len(findings),
                "chunks": len(chunks),
                "published": published,
                "run_id": run_id,
            }
        except Exception:
            JOBS_TOTAL.labels(status="error").inc()
            JOB_DURATION.observe(time.perf_counter() - started)
            raise

    def _apply_repo_ignores(self, files: list[DiffFile]) -> list[DiffFile]:
        out: list[DiffFile] = []
        for f in files:
            ignored, reason = should_ignore_file(f.filename, f.patch)
            if not ignored and path_is_ignored(f.filename, self.repo_config):
                ignored, reason = True, "repo_config"
            out.append(f.model_copy(update={"ignored": ignored, "ignore_reason": reason}))
        return out
