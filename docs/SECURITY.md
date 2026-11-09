# Security review (Phase 7)

## Webhook handling
- Signatures verified with HMAC-SHA256 and `hmac.compare_digest` (constant-time).
- Raw body bytes are verified before JSON parsing.
- Invalid signatures return 401; ignored event types return 202 (no retry storms).
- Webhook secret comes from settings / environment — never hardcoded in code paths.

## Token handling
- GitHub App private key is read from a file path in settings, not embedded in source.
- Installation tokens are cached in memory with skew-based refresh; not logged.
- LLM API keys are read from environment via `Settings`.
- Workers never execute PR code; diffs are treated as untrusted text only.

## Prompt injection
- Diff content is wrapped in explicit delimiters.
- System/user prompts instruct agents to ignore instructions found inside diffs.
- LLM JSON output is schema-validated; one repair retry then drop.

## Operational
- Dead-letter queue captures failed jobs for manual replay (`reviewpilot-replay-dlq`).
- Idempotent publish key: `(owner, repo, number, head_sha)`.
