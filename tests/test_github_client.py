"""GitHub client request helpers with mocked HTTP."""

from __future__ import annotations

import httpx
import pytest
from app.services.github_auth import GitHubAppAuth
from app.services.github_client import GitHubClient


@pytest.mark.asyncio
async def test_list_files_and_create_review(tmp_path: object) -> None:
    from pathlib import Path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = Path(str(tmp_path)) / "k.pem"
    path.write_bytes(pem)

    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "t"})
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "a.py",
                        "status": "modified",
                        "patch": "@@ -1 +1 @@\n-a\n+b\n",
                    }
                ],
            )
        if request.url.path.endswith("/reviews"):
            return httpx.Response(200, json={"id": 99})
        if "/pulls/" in request.url.path:
            return httpx.Response(200, json={"number": 1})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as http:
        auth = GitHubAppAuth(app_id="1", private_key=path.read_text(), http=http)
        client = GitHubClient(auth=auth, http=http)
        pr = await client.get_pull_request("o", "r", 1, installation_id=5)
        files = await client.list_pull_files("o", "r", 1, installation_id=5)
        review = await client.create_review(
            "o",
            "r",
            1,
            installation_id=5,
            commit_id="abc",
            body="hi",
            comments=[],
        )
    assert pr["number"] == 1
    assert files[0].filename == "a.py"
    assert review["id"] == 99
    assert any("/access_tokens" in c for c in calls)
