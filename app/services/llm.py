"""LLM client wrapper with timeout, backoff, circuit breaker, and token accounting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.logging import get_logger
from app.core.retry import with_backoff
from app.core.settings import Settings

logger = get_logger(__name__)


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    model: str = ""


class CircuitOpenError(RuntimeError):
    """Raised when the LLM circuit breaker is open."""


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, reset_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.time() - self.opened_at >= self.reset_seconds:
            self.opened_at = None
            self.failures = 0
            return
        raise CircuitOpenError("LLM circuit breaker is open")

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.time()
            logger.warning("llm_circuit_opened", failures=self.failures)


class LLMClient(Protocol):
    async def complete(self, *, system: str, user: str) -> LLMResponse: ...

    @property
    def total_usage(self) -> LLMUsage: ...


class HttpLLMClient:
    """OpenAI-compatible chat completions client."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._owns_http = http is None
        self.breaker = CircuitBreaker()
        self._usage = LLMUsage()

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpLLMClient:
        return cls(
            api_base=settings.llm_api_base or "https://api.openai.com/v1",
            api_key=settings.llm_api_key,
            model=settings.llm_model or "gpt-4o-mini",
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    @property
    def total_usage(self) -> LLMUsage:
        return self._usage

    async def complete(self, *, system: str, user: str) -> LLMResponse:
        self.breaker.before_call()

        async def _call() -> LLMResponse:
            response = await self._http.post(
                f"{self._api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self._timeout,
            )
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "server error",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            data = response.json()
            content = str(data["choices"][0]["message"]["content"])
            usage_raw: dict[str, Any] = data.get("usage") or {}
            usage = LLMUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
                completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            )
            return LLMResponse(content=content, usage=usage, model=self._model)

        try:
            result = await with_backoff(
                _call,
                retries=self._max_retries,
                retry_on=(httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError),
            )
        except Exception:
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        self._usage.prompt_tokens += result.usage.prompt_tokens
        self._usage.completion_tokens += result.usage.completion_tokens
        return result

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


class FakeLLM:
    """Deterministic LLM stub for tests and evals."""

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.delay = delay
        self.calls: list[tuple[str, str]] = []
        self._usage = LLMUsage()

    @property
    def total_usage(self) -> LLMUsage:
        return self._usage

    async def complete(self, *, system: str, user: str) -> LLMResponse:
        import asyncio

        self.calls.append((system, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        content = '{"findings":[]}' if not self.responses else self.responses.pop(0)
        self._usage.prompt_tokens += max(1, len(system + user) // 4)
        self._usage.completion_tokens += max(1, len(content) // 4)
        return LLMResponse(content=content, usage=LLMUsage(1, 1), model="fake")
