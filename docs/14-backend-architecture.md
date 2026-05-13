# 14 — Backend Architecture

**FastAPI · Python 3.12+ · SQLAlchemy 2.x (async) · Alembic · PostgreSQL · Celery · Redis · S3.** Shape: a **modular monolith** behind an API gateway, with heavy/slow work on a **Celery worker fleet**, and OCR + AI as **separately-scalable specialist workers** (already isolated behind queues so they lift out cleanly later). API-first, multi-tenant, event-driven internally.

---

## 1. Layering

```
┌─ API layer (FastAPI) ──────────────────────────────────────────────────────────────┐
│  routers/  — HTTP endpoints; validate I/O with Pydantic v2 schemas; authn/authz     │
│              (deps); rate limiting; map domain errors → HTTP; serialize DTOs.        │
│              NEVER touches the ORM or business logic directly.                       │
├─ Application layer (use-cases / services) ─────────────────────────────────────────┤
│  services/ — one class/module per use-case area: ContractService, ApprovalService,  │
│              WorkflowEngine, SignatureService, OCRService, AIService, BillingService │
│              … Orchestrates: opens a DB transaction (Unit of Work), calls            │
│              repositories + the domain, emits domain events, enqueues jobs.          │
│              Called by BOTH routers AND Celery tasks (same code path).               │
├─ Domain layer ────────────────────────────────────────────────────────────────────┤
│  domain/   — entities, value objects, the contract LIFECYCLE STATE MACHINE          │
│              (allowed transitions, guards), policies (can-this-role-do-this),        │
│              domain events. Pure Python. No imports of FastAPI/SQLAlchemy/Celery.    │
├─ Infrastructure layer ────────────────────────────────────────────────────────────┤
│  repositories/ (SQLAlchemy), db/ (engine, session, RLS), storage/ (S3),             │
│  cache/ (Redis), email/, sms/, search/ (pg FTS / pgvector — abstracted),            │
│  ocr/ (OCRProvider impls), ai/ (LLMProvider impls), signing/ (crypto, PDF flatten,  │
│  timestamp authority), webhooks/ (signed dispatch + retry), events/ (bus), pdf/      │
│  (rendering), notifications/ (channel fan-out), audit/ (append-only + hash chain).   │
└────────────────────────────────────────────────────────────────────────────────────┘
```
**Hard rules:** routers ⇒ services ⇒ domain + repositories; no skipping; no router touches the ORM; no service touches `Request`/`Response`; the domain imports nothing from infra; repositories are the only place SQL lives; every repository method is tenant-scoped (takes/uses the tenant context — defense in depth on top of RLS). Dependency injection via FastAPI `Depends` (request-scoped session, current user/tenant, services wired from a small container).

## 2. Modules (bounded contexts inside the monolith)

`identity` (users, sessions, MFA, RBAC, roles) · `tenancy` (workspaces, teams, plans, feature flags, custom-field schemas, branding) · `contracts` (contract aggregate, versions, metadata, lifecycle state machine, the block-document, attachments, relations/renewals) · `templates` (templates, clause library) · `workflows` (definitions, versions, the engine, runs, steps, timers, escalation) · `signatures` (envelopes, recipients, fields, the ceremony, certificates, sealing) · `intelligence` (OCR jobs, OCR results, AI extractions/analysis, the assistant, semantic search) · `notifications` (preferences, dispatch, channels: in-app/email/push/Slack-Teams) · `audit` (the immutable hash-chained log, evidence-package export) · `reporting` (rollups, report definitions, scheduled reports — reads the replica) · `billing` (plans, usage metering, the provider integration, invoices) · `integrations` (webhooks out, SSO/SCIM in, connectors) · `files` (the abstraction over S3 — upload, presign, hash, encrypt, versions, lifecycle). Each module: its own `routers/ services/ domain/ repositories/ schemas/ tasks/ events/`. **Cross-module communication is via published events or a thin internal service interface — never a direct DB read into another module's tables.** This boundary discipline is what makes OCR/AI/notifications/billing extractable to services later (Doc 18 §scalability).

## 3. Async & concurrency

- FastAPI is **async**; the DB driver is **asyncpg** via SQLAlchemy 2.x async; all I/O (DB, S3, Redis, HTTP to OCR/AI/email) is `await`ed; CPU-bound bits (PDF flatten, hashing big files, image preprocessing) run in a thread/process pool or — better — on Celery workers, never blocking the event loop.
- **Request-scoped DB session**, committed/rolled-back by a dependency; the **Unit of Work** pattern in services for multi-step transactions; optimistic concurrency (a `version`/`updated_at` check) on contracts to catch concurrent edits; `SELECT … FOR UPDATE` only where genuinely needed (e.g., advancing a workflow run, claiming a job).
- **Idempotency:** mutating API endpoints accept an `Idempotency-Key` header (stored → replays return the original result); all Celery tasks are idempotent (keyed on a natural id; "already processed?" check first); webhook deliveries carry a delivery id; events carry an event id consumers dedupe on.

## 4. Background jobs (Celery + Redis)

- **Broker:** Redis (or RabbitMQ if/when ordering/priority needs outgrow Redis); a result backend only where a result is read back (most jobs write to the `jobs` table instead).
- **Named, prioritized queues** so interactive work never starves: `ocr` · `ai` · `pdf` (render/flatten — interactive, kept fast) · `email` · `sms` · `webhooks` (with retry/backoff + a dead-letter queue) · `notifications` · `imports` (bulk) · `reports` · `default` · `low` (anything batchy/best-effort). Workers are deployed per-queue (or per-queue-group) so each scales independently (Doc 18).
- **What runs on jobs:** OCR pipeline, AI analysis, contract PDF render & signed-PDF flatten + certificate generation, bulk import, mass-send of envelopes, email/SMS/push send, webhook delivery, evidence-package export, report generation, search reindex, embedding generation, image preprocessing, data exports, account/workspace deletion.
- **Scheduled (Celery beat):** nightly expiry/renewal scan, reminder cadences (approval/signature/expiry), workflow SLA-timer scans (or per-timer `eta` tasks), report schedules, audit retention/archival, usage-meter rollups, embedding/reindex refresh, session/token cleanup, dunning runs, health self-checks.
- **Job tracking:** every job writes a row to `jobs` (id, tenant_id, type, status, progress %, items[], result_ref, error, timestamps) → the **Progress Tray** and any UI poll/subscribe to it; long jobs report incremental progress; on completion they emit a domain event (→ notification + tray "ready").
- **Reliability:** retries with exponential backoff + jitter; max-retry → DLQ + an alert; `acks_late` + `reject_on_worker_lost` so a crashed worker's task is re-run (safe because idempotent); per-task soft/hard time limits; graceful shutdown drains in-flight tasks.

## 5. Multi-tenancy (backend mechanics)

- A request resolves its **tenant** from the JWT (`tenant_id` claim) and/or subdomain → set into a **context var** → at the start of the DB session, `SET app.current_tenant = '<uuid>'` (a Postgres session variable) → **Row-Level Security policies** on every tenant-scoped table key off `current_setting('app.current_tenant')::uuid` → even a bug that forgets a `WHERE tenant_id = …` can't leak across tenants. *And* the repository layer still always includes the tenant filter (belt and braces). System/cross-tenant operations (Platform Admin, beat jobs that scan all tenants) run with a privileged role that bypasses RLS — explicitly, narrowly, audited.
- **Connection pooling** via PgBouncer (transaction pooling); RLS session vars are set per transaction so pooling is safe.
- **S3:** per-tenant key prefixes (`tenants/<id>/contracts/<id>/…`); per-tenant encryption keys (envelope encryption — a tenant data-key wrapped by a KMS master key); presigned URLs scoped and short-lived.
- **Plans/quotas/feature-flags:** tenant attributes; a central `require_feature("ai_analysis")` / `check_quota("ocr_pages", n)` dependency/decorator; over-quota behavior per plan (queue / soft-cap / overage-bill / block-with-upsell).
- **Escape hatch for big tenants:** the repository/session layer abstracts the connection → a heavy or regulated tenant can be moved to its **own schema** (search_path per tenant) or **own database** (a tenant→DSN map) with no application changes; further, to its own cluster/region. Day-1 is shared-everything (cheapest); each step up is a planned config change, not a rewrite.

## 6. Events & integration

- **Domain events** (`ContractCreated`, `ContractSubmitted`, `ApprovalGranted`, `ApprovalRejected`, `ChangesRequested`, `EnvelopeSent`, `RecipientSigned`, `EnvelopeCompleted`, `ContractActivated`, `ContractExpiringSoon`, `ContractRenewed`, `ContractTerminated`, `OCRCompleted`, `AIAnalysisCompleted`, `WorkflowRunAdvanced`, `RiskFlagged`, `ObligationDue`, …) are emitted by services *after commit* (transactional outbox pattern: write the event to an `outbox` table in the same transaction; a dispatcher publishes it → at-least-once, no lost events on crash).
- **Consumers:** the notification engine (→ in-app/email/push/Slack), the webhook dispatcher (→ signed POST to tenant endpoints, with retries + delivery log + replay), the reporting rollup updater, the workflow engine (some events advance runs), the search/embedding indexer, the activity-stream projector, the audit logger.
- **Bus:** day-1 an in-process pub/sub fed by the outbox dispatcher (simple, ordered-enough); swap to **Redis Streams** (or Kafka/NATS at real scale) when fan-out/throughput demands — the publish/subscribe interface stays the same.
- **Inbound integrations:** SSO (SAML 2.0 + OIDC) and SCIM provisioning as pluggable adapters in `identity`; email-to-contract (an inbound address per tenant → parse attachments → OCR pipeline); Slack/Teams (OAuth app → action-card delivery + slash commands); storage connectors (Google Drive / SharePoint — import & link); e-sign legal-vendor add-ons (some tenants/jurisdictions want a specific qualified-signature provider — wrap behind the `signing` module's provider interface). **Outbound:** the public REST API + webhooks make the platform a hub (HRIS/ERP sync of contract data, etc.).

## 7. Caching & performance

- **Redis** caches: tenant config/feature-flags/branding, user permission sets, session lookups, rate-limit counters, idempotency keys, rendered-PDF refs, OCR/AI result refs (keyed by content hash + version — see Doc 09), expensive aggregates' short-TTL caches, the dashboard widget payloads (short TTL, invalidated on relevant events).
- **DB:** `tenant_id`-leading composite indexes on every list query; partial indexes for common filtered views (e.g., `WHERE status = 'in_review'`); GIN indexes on JSONB metadata and `tsvector` for full-text and `pg_trgm` for fuzzy; `pgvector` HNSW index for embeddings; **read replicas** for all reporting/analytics/dashboard-aggregate reads (the API points those at the replica); time-partitioning on `audit_log`, `activity_events`, `notifications`, `jobs`, `workflow_run_events` (monthly partitions, auto-created, old ones detached to cold storage).
- **Pagination:** cursor-based (`?after=<opaque-cursor>&limit=`) for stable, fast deep paging; total counts are estimated for huge tables (or shown as "1,000+") to avoid full counts.
- **N+1 guards:** eager-load relations explicitly per use-case; a query-count assertion in tests on hot endpoints.
- **Hot paths** (contract list, contract detail, dashboard, inbox) are profiled and have SLOs (p95 latency budgets — Doc 18); they read from cache/replica and never trigger heavy aggregates synchronously.

## 8. Cross-cutting

- **Config:** Pydantic `Settings` from env vars / a secrets manager (Vault/AWS Secrets Manager); no secrets in code or images; per-environment overrides; feature flags via a flag service (or a DB table) checkable at runtime.
- **Migrations:** Alembic; every schema change is a reviewed, reversible migration; CI runs migrations against a fresh DB and against a copy of prod-shape; zero-downtime patterns (add-then-backfill-then-switch-then-drop) for big changes; data migrations as separate, idempotent, batched scripts.
- **Errors:** a typed exception hierarchy in the domain/services (`NotFound`, `Forbidden`, `Conflict`, `ValidationError`, `QuotaExceeded`, `IntegrityError`, `ExternalServiceError`) → a single FastAPI exception handler maps them to RFC-7807-style problem responses (Doc 16); unexpected errors → 500 + Sentry + a correlation id the user can quote to support; never leak stack traces.
- **Logging/telemetry:** structured JSON logs with `request_id` / `tenant_id` / `user_id` / `job_id` correlation; OpenTelemetry traces spanning HTTP → service → DB → queue → worker; Prometheus metrics (request latency/error rate, queue depth & age, job success rate & duration by type, OCR pages/min, AI tokens, DB pool usage, cache hit rate, webhook delivery rate); Sentry for exceptions; audit-grade access logs separate from app logs. (Full ops in Doc 18.)
- **Testing:** unit tests on the domain (state machine, policies — fast, no DB); service/integration tests against a real Postgres (testcontainers) with RLS on (so tenant-isolation bugs surface); API contract tests (the OpenAPI schema is the contract; consumer-driven where integrations exist); job tests (run tasks synchronously, assert idempotency); load tests on hot paths; security tests (authz matrix, RLS, rate limits, common-vuln scans) in CI; the frontend's MSW mocks generated from the OpenAPI schema so FE/BE stay in sync.
- **API versioning & docs:** versioned under `/api/v1` (Doc 16); FastAPI auto-generates OpenAPI; a published, browsable API reference + a playground; deprecations announced with a sunset header and a timeline.
- **Service accounts & API tokens:** scoped tokens (per-tenant, per-permission-set, expiring, revocable, rate-limited, audited) for the public API and integrations; no UI for service accounts beyond issuing/revoking tokens in settings.
