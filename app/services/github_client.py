"""Async GitHub API client with retries and rate-limit handling."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.core.retry import with_backoff
from app.core.schemas import DiffFile
from app.core.settings import Settings
from app.services.github_auth import GitHubAppAuth, asyncio_sleep_from_reset

logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """Thin async wrapper around the GitHub REST API for PR review flows."""

    def __init__(
        self,
        *,
        auth: GitHubAppAuth,
        http: httpx.AsyncClient,
        timeout: float = 30.0,
    ) -> None:
        self._auth = auth
        self._http = http
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> tuple[GitHubClient, httpx.AsyncClient]:
        http = httpx.AsyncClient(
            base_url=GITHUB_API,
            timeout=settings.request_timeout_seconds,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        auth = GitHubAppAuth.from_settings(settings, http)
        return cls(auth=auth, http=http, timeout=settings.request_timeout_seconds), http

    async def _headers(self, installation_id: int) -> dict[str, str]:
        token = await self._auth.get_installation_token(installation_id)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        installation_id: int,
        json: dict[str, Any] | None = None,
    ) -> Any:
        async def _call() -> httpx.Response:
            headers = await self._headers(installation_id)
            return await self._http.request(method, path, headers=headers, json=json)

        response = await with_backoff(
            _call,
            retries=3,
            retry_on=(httpx.TransportError, httpx.TimeoutException),
        )
        if response.status_code == 403 and "rate limit" in response.text.lower():
            logger.warning("github_rate_limited", path=path)
            await asyncio_sleep_from_reset(response)
            response = await _call()
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def get_pull_request(
        self, owner: str, repo: str, number: int, *, installation_id: int
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}",
            installation_id=installation_id,
        )
        return dict(data)

    async def list_pull_files(
        self, owner: str, repo: str, number: int, *, installation_id: int
    ) -> list[DiffFile]:
        raw = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}/files?per_page=100",
            installation_id=installation_id,
        )
        files: list[DiffFile] = []
        for item in raw or []:
            files.append(
                DiffFile(
                    filename=str(item["filename"]),
                    status=str(item.get("status", "modified")),
                    previous_filename=item.get("previous_filename"),
                    patch=item.get("patch"),
                )
            )
        return files

    async def create_review(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        installation_id: int,
        commit_id: str,
        body: str,
        comments: list[dict[str, Any]],
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        payload = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
            "comments": comments,
        }
        data = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            installation_id=installation_id,
            json=payload,
        )
        return dict(data)
