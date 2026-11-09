"""Tests for GitHub App JWT and token cache."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from app.services.github_auth import CachedToken, GitHubAppAuth
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _make_key(tmp_path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "app.pem"
    path.write_bytes(pem)
    return path


@pytest.mark.asyncio
async def test_jwt_and_token_cache(tmp_path: Path, httpx_mock: None = None) -> None:
    key_path = _make_key(tmp_path)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(201, json={"token": "ghs_test", "expires_at": "2099-01-01T00:00:00Z"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as http:
        auth = GitHubAppAuth(app_id="123", private_key=key_path.read_text(), http=http)
        token1 = await auth.get_installation_token(9)
        token2 = await auth.get_installation_token(9)
        assert token1 == "ghs_test"
        assert token2 == "ghs_test"
        # Force expiry and refresh
        auth._cache[9] = CachedToken(token="old", expires_at=time.time() - 1)
        token3 = await auth.get_installation_token(9)
        assert token3 == "ghs_test"
