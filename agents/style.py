"""Style / maintainability review agent."""

from __future__ import annotations

from agents.base import BaseAgent


class StyleAgent(BaseAgent):
    name = "style"
    prompt_file = "style_v1.md"
    category_hint = "style"
