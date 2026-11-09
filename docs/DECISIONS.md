# Design Decisions

## 2026-03-23 — Phase 1 scaffold

- **In-memory queue for tests:** Webhook tests inject `InMemoryJobQueue` via the app
  factory so CI does not require Redis. Production uses `RedisJobQueue` (LPUSH/BRPOP).
- **Ignored events still return 202:** GitHub retries on 4xx/5xx. Non-PR or unsupported
  PR actions are acknowledged with `{"status":"ignored"}` so deliveries are not retried.
- **Signature verified before JSON parse:** Body bytes are verified first so malformed
  JSON cannot bypass auth; invalid signatures always return 401.
- **Worker is a stub:** Phase 1 only logs dequeued jobs. Diff fetch and agents arrive in
  Phases 2–3.
