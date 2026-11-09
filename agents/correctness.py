"""Correctness review agent."""

from __future__ import annotations

from agents.base import BaseAgent


class CorrectnessAgent(BaseAgent):
    name = "correctness"
    prompt_file = "correctness_v1.md"
    category_hint = "correctness"
