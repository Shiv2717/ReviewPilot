"""GitHub App JWT -> installation access token with caching and refresh."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt

from app.core.logging import get_logger
from app.core.retry import with_backoff
from app.core.settings import Settings

logger = get_logger(__name__)


@dataclass
class CachedToken:
    token: str
    expires_at: float


class GitHubAppAuth:
    """Mint and cache installation tokens for a GitHub App."""

    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        http: httpx.AsyncClient,
        skew_seconds: int = 60,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._http = http
        self._skew = skew_seconds
        self._cache: dict[int, CachedToken] = {}

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient) -> GitHubAppAuth:
        key = ""
        if settings.github_app_private_key_path:
            key = Path(settings.github_app_private_key_path).read_text(encoding="utf-8")
        return cls(app_id=settings.github_app_id, private_key=key, http=http)

    def create_jwt(self, *, now: float | None = None) -> str:
        if not self._app_id or not self._private_key:
            raise RuntimeError("GitHub App credentials are not configured")
        issued = int(now if now is not None else time.time()) - 60
        payload = {
            "iat": issued,
            "exp": issued + 9 * 60,
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        cached = self._cache.get(installation_id)
        now = time.time()
        if cached and cached.expires_at - self._skew > now:
            return cached.token

        token = await self._fetch_token(installation_id)
        self._cache[installation_id] = token
        logger.info(
            "installation_token_refreshed",
            installation_id=installation_id,
            expires_at=token.expires_at,
        )
        return token.token

    async def _fetch_token(self, installation_id: int) -> CachedToken:
        app_jwt = self.create_jwt()

        async def _call() -> httpx.Response:
            return await self._http.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )

        response = await with_backoff(_call, retries=3, retry_on=(httpx.TransportError,))
        if response.status_code == 403 and "rate limit" in response.text.lower():
            await asyncio_sleep_from_reset(response)
            response = await _call()
        response.raise_for_status()
        data = response.json()
        # GitHub returns expires_at as ISO8601; keep a conservative 50-minute TTL if absent.
        expires_at = time.time() + 50 * 60
        return CachedToken(token=str(data["token"]), expires_at=expires_at)


async def asyncio_sleep_from_reset(response: httpx.Response) -> None:
    import asyncio

    reset = response.headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        delay = max(0.0, float(reset) - time.time())
        await asyncio.sleep(min(delay, 30.0))
    else:
        await asyncio.sleep(1.0)
