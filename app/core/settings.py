"""Typed application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for ReviewPilot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    request_timeout_seconds: float = Field(default=30.0, alias="REQUEST_TIMEOUT_SECONDS")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    database_url: str = Field(
        default="postgresql+asyncpg://reviewpilot:reviewpilot@localhost:5432/reviewpilot",
        alias="DATABASE_URL",
    )

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_job_queue: str = Field(default="reviewpilot:jobs", alias="REDIS_JOB_QUEUE")
    redis_dlq: str = Field(default="reviewpilot:dlq", alias="REDIS_DLQ")

    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    github_app_id: str = Field(default="", alias="GITHUB_APP_ID")
    github_app_private_key_path: str = Field(default="", alias="GITHUB_APP_PRIVATE_KEY_PATH")
    github_app_installation_id: str = Field(default="", alias="GITHUB_APP_INSTALLATION_ID")

    llm_api_base: str = Field(default="", alias="LLM_API_BASE")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")

    confidence_threshold: float = Field(default=0.5, alias="CONFIDENCE_THRESHOLD")
    max_comments_per_pr: int = Field(default=40, alias="MAX_COMMENTS_PER_PR")
    agent_timeout_seconds: float = Field(default=90.0, alias="AGENT_TIMEOUT_SECONDS")
    agent_concurrency: int = Field(default=4, alias="AGENT_CONCURRENCY")
    token_budget_per_chunk: int = Field(default=6000, alias="TOKEN_BUDGET_PER_CHUNK")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
