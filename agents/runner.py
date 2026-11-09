"""Run specialist agents concurrently over diff chunks."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from app.core.logging import get_logger
from app.core.schemas import DiffChunk, Finding
from app.services.llm import LLMClient

from agents.base import ReviewAgent
from agents.correctness import CorrectnessAgent
from agents.performance import PerformanceAgent
from agents.security import SecurityAgent
from agents.style import StyleAgent

logger = get_logger(__name__)


def default_agents(llm: LLMClient, enabled: Sequence[str] | None = None) -> list[ReviewAgent]:
    all_agents: list[ReviewAgent] = [
        SecurityAgent(llm),
        PerformanceAgent(llm),
        CorrectnessAgent(llm),
        StyleAgent(llm),
    ]
    if enabled is None:
        return all_agents
    allow = {n.lower() for n in enabled}
    return [a for a in all_agents if a.name.lower() in allow]


async def review_chunks(
    chunks: list[DiffChunk],
    agents: Sequence[ReviewAgent],
    *,
    concurrency: int,
    timeout_seconds: float,
) -> list[Finding]:
    sem = asyncio.Semaphore(concurrency)
    findings: list[Finding] = []

    async def _one(agent: ReviewAgent, chunk: DiffChunk) -> list[Finding]:
        async with sem:
            try:
                return await asyncio.wait_for(agent.review(chunk), timeout=timeout_seconds)
            except TimeoutError:
                logger.warning(
                    "agent_timeout",
                    agent=agent.name,
                    chunk_id=chunk.chunk_id,
                    timeout=timeout_seconds,
                )
                return []
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "agent_failed",
                    agent=agent.name,
                    chunk_id=chunk.chunk_id,
                    error=str(exc),
                )
                return []

    tasks = [_one(agent, chunk) for chunk in chunks for agent in agents]
    results = await asyncio.gather(*tasks)
    for batch in results:
        findings.extend(batch)
    return findings
