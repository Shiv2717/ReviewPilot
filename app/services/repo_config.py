"""Per-repo ReviewPilot configuration (.reviewpilot.yml)."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field


class RepoConfig(BaseModel):
    ignored_paths: list[str] = Field(default_factory=list)
    severity_threshold: str = "low"
    enabled_agents: list[str] = Field(
        default_factory=lambda: ["security", "performance", "correctness", "style"]
    )
    confidence_threshold: float | None = None
    max_comments: int | None = None


DEFAULT_CONFIG = RepoConfig()

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def parse_repo_config(raw: str | bytes | dict[str, Any] | None) -> RepoConfig:
    if raw is None or raw == "":
        return DEFAULT_CONFIG.model_copy(deep=True)
    if isinstance(raw, dict):
        data = raw
    else:
        loaded = yaml.safe_load(raw)
        data = loaded if isinstance(loaded, dict) else {}
    return RepoConfig.model_validate(data)


def path_is_ignored(path: str, config: RepoConfig) -> bool:
    for pattern in config.ignored_paths:
        if pattern.endswith("/**") and path.startswith(pattern[:-3]):
            return True
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            return True
        if path == pattern or path.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def severity_at_least(severity: str, threshold: str) -> bool:
    try:
        return SEVERITY_ORDER.index(severity) <= SEVERITY_ORDER.index(threshold)
    except ValueError:
        return True
