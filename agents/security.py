"""Security review agent."""

from __future__ import annotations

from agents.base import BaseAgent


class SecurityAgent(BaseAgent):
    name = "security"
    prompt_file = "security_v1.md"
    category_hint = "security"
