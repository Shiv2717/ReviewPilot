"""Performance review agent."""

from __future__ import annotations

from agents.base import BaseAgent


class PerformanceAgent(BaseAgent):
    name = "performance"
    prompt_file = "performance_v1.md"
    category_hint = "performance"
