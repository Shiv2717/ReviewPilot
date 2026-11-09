"""Tests for per-repo YAML config."""

from __future__ import annotations

from app.services.repo_config import parse_repo_config, path_is_ignored, severity_at_least


def test_parse_defaults() -> None:
    cfg = parse_repo_config(None)
    assert "security" in cfg.enabled_agents
    assert cfg.severity_threshold == "low"


def test_ignored_paths_and_severity() -> None:
    cfg = parse_repo_config(
        """
ignored_paths:
  - vendor/**
  - build/
severity_threshold: high
"""
    )
    assert path_is_ignored("vendor/lib/x.py", cfg)
    assert path_is_ignored("build/out.js", cfg)
    assert not path_is_ignored("app/main.py", cfg)
    assert severity_at_least("critical", "high")
    assert not severity_at_least("low", "high")
