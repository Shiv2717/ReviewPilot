# ReviewPilot

Multi-agent GitHub pull request reviewer. When a PR is opened or updated, ReviewPilot
fetches the diff, runs four specialist LLM agents in parallel, aggregates findings, and
posts **one** structured review with inline comments and a summary.

## Architecture

```mermaid
flowchart LR
  GH[GitHub webhook] --> API[FastAPI /webhooks/github]
  API -->|verify HMAC| Q[(Redis queue)]
  Q --> W[Worker]
  W --> Diff[Diff processor]
  Diff --> A1[Security]
  Diff --> A2[Performance]
  Diff --> A3[Correctness]
  Diff --> A4[Style]
  A1 --> Agg[Aggregator]
  A2 --> Agg
  A3 --> Agg
  A4 --> Agg
  Agg --> Pub[Publisher]
  Pub --> GH2[GitHub review]
  W --> DB[(PostgreSQL)]
  API --> Dash[React dashboard]
  API --> Prom[/metrics]
```

## Quickstart

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# infrastructure
docker compose up --build -d postgres redis
alembic upgrade head

# API + worker (separate terminals)
make dev
make worker   # or: python -m app.services.worker

# dashboard
cd web && npm install && npm run dev
```

Or all-in-one:

```bash
docker compose up --build
```

## GitHub App setup

1. Create a GitHub App with permissions: Pull requests (read/write), Contents (read).
2. Subscribe to `Pull request` events.
3. Set the webhook URL to `https://<host>/webhooks/github` and configure the secret.
4. Download the private key; set:
   - `GITHUB_APP_ID`
   - `GITHUB_APP_PRIVATE_KEY_PATH`
   - `GITHUB_WEBHOOK_SECRET`
   - `GITHUB_APP_INSTALLATION_ID` (optional default)
5. Configure LLM credentials: `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `GITHUB_WEBHOOK_SECRET` | HMAC secret for webhooks |
| `REDIS_URL` / `DATABASE_URL` | Infrastructure |
| `CONFIDENCE_THRESHOLD` | Drop low-confidence findings |
| `MAX_COMMENTS_PER_PR` | Cap inline comments |
| `TOKEN_BUDGET_PER_CHUNK` | Diff chunking budget |
| `AGENT_CONCURRENCY` | Parallel agent calls |

Per-repo overrides live in `.reviewpilot.yml` (ignored paths, severity threshold, enabled agents).

## Development

```bash
make lint
make typecheck
make test
make eval          # FakeLLM by default
make ci
python scripts/load_test.py --count 50
```

## Eval results

Run `make eval` to regenerate `evals/report.md`. Baseline gate fails CI if overall
precision drops more than 5 points below `evals/baseline.json`.

| agent | role |
| --- | --- |
| security | injection, secrets, authz |
| performance | N+1, blocking async, wasteful work |
| correctness | logic bugs, races, error handling |
| style | naming, dead code, missing tests |

## Observability

- `GET /healthz`, `GET /readyz`
- `GET /metrics` (Prometheus)
- Grafana dashboard JSON: `docker/grafana-dashboard.json`
- Dashboard UI: PR list, severity filters, latency/token charts, accept/dismiss, CSV export

## Limitations

- GitHub pagination beyond 100 files per PR is not fetched yet.
- Position mapping uses RIGHT-side new lines; comment-only / deleted-line reviews are limited.
- Without LLM credentials the worker uses `FakeLLM` (empty findings) for local smoke tests.
- Dashboard needs a migrated Postgres with review runs to show data.

## Roadmap

- Multi-installation routing from webhook payloads only
- Suggestion batches / fix PRs
- Learning from accept/dismiss feedback
- Streaming agent progress on the dashboard

## License

MIT
