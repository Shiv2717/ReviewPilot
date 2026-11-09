"""Load test: enqueue 50 concurrent PR review jobs against a running API/Redis."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import time
import uuid

import httpx


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def payload(n: int) -> dict[str, object]:
    return {
        "action": "opened",
        "pull_request": {"number": n, "head": {"sha": uuid.uuid4().hex}},
        "repository": {"name": "loadtest", "owner": {"login": "acme"}},
        "installation": {"id": 1},
    }


async def fire_one(client: httpx.AsyncClient, url: str, secret: str, n: int) -> int:
    body = json.dumps(payload(n)).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sign(secret, body),
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": str(uuid.uuid4()),
    }
    resp = await client.post(url, content=body, headers=headers)
    return resp.status_code


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/webhooks/github")
    parser.add_argument("--secret", default="change-me-webhook-secret")
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        codes = await asyncio.gather(
            *[fire_one(client, args.url, args.secret, i + 1) for i in range(args.count)]
        )
    elapsed = time.perf_counter() - started
    ok = sum(1 for c in codes if c == 202)
    print(f"sent={args.count} accepted={ok} elapsed_s={elapsed:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
