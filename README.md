# ReviewPilot

Multi-agent GitHub pull request reviewer. When a PR is opened or updated, ReviewPilot
fetches the diff, runs specialist agents in parallel, merges findings, and posts one
structured review with inline comments.

> **Status:** Phase 1 complete — webhook receiver, Redis enqueue, health probes, CI.

## Quickstart

```bash
# Install (Python 3.12+)
make install

# Copy env and start dependencies + API + worker
cp .env.example .env
docker compose up --build

# Or run the API locally (Redis required for /readyz and enqueue)
make dev
```

Health checks:

- `GET /healthz` — liveness
- `GET /readyz` — Redis reachable
- `POST /webhooks/github` — GitHub webhook (HMAC-SHA256 verified)

## Development

```bash
make lint        # ruff
make typecheck   # mypy --strict
make test        # pytest
make ci          # lint + typecheck + test
```

## Architecture (Phase 1)

```
GitHub --webhook--> FastAPI (/webhooks/github)
                         | verify X-Hub-Signature-256
                         | filter opened|synchronize|reopened
                         v
                      Redis queue
                         v
                      Worker (stub: logs jobs)
```

Later phases add GitHub App auth, diff chunking, four LLM agents, aggregation,
idempotent publishing, evals, and a React dashboard.

## License

MIT
