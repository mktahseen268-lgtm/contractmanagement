# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project shape

Multi-tenant E-Contract / E-Agreement lifecycle management SaaS. Two apps in one repo:

- [apps/api/](apps/api/) — FastAPI + SQLAlchemy + Alembic + Celery. Target DB is PostgreSQL (with Row-Level Security); SQLite is accepted only for a zero-setup dev look.
- [apps/web/](apps/web/) — Next.js 14 App Router + React 18 + TypeScript + Tailwind. Tiptap for the document editor.
- [docs/](docs/) — 27 design/architecture markdown docs. **This is the single source of truth for product/UX/architecture intent.** Code in `apps/` is a runnable subset ("the spine") of what `docs/` describes; cross-reference the relevant doc when adding non-trivial features.
- [docker-compose.yml](docker-compose.yml) — postgres + redis + minio + api + worker + web. The standard way to run everything.
- [infra/k8s/](infra/k8s/) — Kustomize manifests (namespace, deployment, HPA, PDB, NetworkPolicy, backup CronJob). [infra/scripts/](infra/scripts/) — backup/restore.

## Run, build, test

**Full stack (recommended):** `docker compose up --build` → web on `:3000`, API on `:8000`, MinIO console on `:9001`, Postgres on `:5432`, Redis on `:6379`. The API container runs `alembic upgrade head`, creates the `cm-files` bucket, and seeds a demo workspace on first start.

**API standalone (terminal 1):**
```bash
cd apps/api
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```
- Migrations: `cd apps/api && alembic upgrade head` (auto-runs on startup when `RUN_MIGRATIONS_ON_STARTUP=true`).
- New migration: `cd apps/api && alembic revision -m "name"` (review the generated file — the existing versions hand-write Postgres-only RLS DDL).
- Celery worker (optional — only needed when `CELERY_TASK_ALWAYS_EAGER=false`): `cd apps/api && celery -A app.celery_app worker --loglevel=info -Q ocr,default`.
- API docs: `http://localhost:8000/docs`.

**Web standalone (terminal 2):**
```bash
cd apps/web
npm install
copy .env.local.example .env.local
npm run dev      # next dev
npm run build    # next build (also acts as TS type-check)
npm run lint     # next lint
```

**CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs: `ruff check apps/api/app`, `mypy --ignore-missing-imports app` (advisory), `next lint` + `next build` for the web, a Postgres-backed import-smoke test for the API, `bandit`, `semgrep p/owasp-top-ten`, `gitleaks`, `pip-audit`/`safety`, `npm audit`, and a Trivy scan of the API image. **There is no real pytest suite yet** — the `test-api` job currently just imports `app.main`. When you add tests, ratchet that job to `pytest apps/api`.

**Demo credentials** (auto-seeded by [apps/api/app/seed.py](apps/api/app/seed.py)): `demo@acme.io` / `demo1234` (owner), plus `manager@`/`approver@`/`author@acme.io` with the same password. To skip seeding, set `AUTO_SEED=false`.

## Architecture you need to know before editing

### Multi-tenancy is enforced in the database (PostgreSQL RLS)

The single most important invariant in this codebase: **every tenant-scoped table has Row-Level Security enabled with FORCE**, gated by the session GUC `app.cm_tenant`. See [apps/api/migrations/versions/0002_rls.py](apps/api/migrations/versions/0002_rls.py) and the docstring at the top of [apps/api/app/database.py](apps/api/app/database.py).

Flow per request:
1. [deps.get_current_user](apps/api/app/deps.py) decodes the JWT (or resolves an API key), reads `tid`, calls `set_request_tenant(tenant_id)` which stores it in a `ContextVar`.
2. A SQLAlchemy `engine.begin` event listener ([database.py:49](apps/api/app/database.py)) emits `SELECT set_config('app.cm_tenant', :tid, true)` on **every** transaction so even post-commit queries stay scoped.
3. Policies are *permissive when the GUC is unset* so the unauthenticated `/auth/login` and `/auth/refresh` endpoints still work.
4. Repository code **also** filters by `tenant_id` — defence in depth. Don't remove these filters when "RLS will handle it"; keep both.

On SQLite (`DATABASE_URL=sqlite:///./cm.db`) the listener is a no-op and the RLS migration is auto-skipped. **Anything you add that depends on cross-tenant isolation must be tested against Postgres**, not SQLite.

When writing new tenant-scoped tables: add the column `tenant_id`, add a Postgres-only `ALTER TABLE … ENABLE ROW LEVEL SECURITY; FORCE …; CREATE POLICY tenant_isolation …` clause to the migration, and filter by `tenant_id` in the repository layer.

### Auth model

- **Access token**: short-lived JWT (30 min default) returned in the response body. The web app keeps it **in memory only** (see [apps/web/src/lib/api.ts](apps/web/src/lib/api.ts)) — never in `localStorage`. Re-obtained on boot via `/auth/refresh`.
- **Refresh token**: opaque server-side token in an httpOnly cookie (`cm_refresh`), rotated on every use, with **reuse detection** — presenting an already-rotated refresh token revokes the entire session chain. Logic lives in [auth_service.py](apps/api/app/auth_service.py).
- **MFA**: TOTP enrolment with recovery codes + email-OTP fallback. The TOTP secret column is encrypted at rest via the `EncryptedString` SQLAlchemy type ([models.py](apps/api/app/models.py)) backed by Fernet/MultiFernet ([secrets_box.py](apps/api/app/secrets_box.py)). `MFA_ENCRYPTION_KEYS` (newline-separated Fernet keys, first = current, others = read-only for rotation) **must** be set outside dev.
- **API keys**: long-lived bearer tokens prefixed `cm_` — minted at Settings → API keys, stored as SHA-256 hash only, resolved in [deps.get_current_user](apps/api/app/deps.py). The plaintext is shown once at creation.

### Backend layering

[apps/api/app/](apps/api/app/) — flat module layout (not feature-sliced):

- `main.py` — app factory; middleware order is **outer→inner: Logging → RateLimit → CORS → SecurityHeaders**. Starlette adds them in reverse, so the order of `add_middleware` calls is reversed from the runtime order — see the comment at [main.py:68](apps/api/app/main.py).
- `routers/*.py` — thin HTTP layer. One router per resource.
- `*_service.py` — the engines: `workflow_service` (approval workflows), `signing_service` (e-signature envelopes + the public `/sign/{token}` portal), `renewal_service` (sweep + clone-to-successor), `auth_service`, `webhook_service`.
- `lifecycle.py` — the contract state machine (`TRANSITIONS` dict). Touch this when you add a status — invalid transitions return 409.
- `models.py` — SQLAlchemy 2.0 typed models. All in one file by design.
- `schemas.py` — Pydantic request/response models.
- `audit.py` — append-only audit log helper; **call `add_audit_entry` for every state-changing action**, that's the contract for tamper evidence (the chained-hash design in docs/19 is on the roadmap).
- `tasks.py` — Celery tasks: OCR pipeline (`queue: ocr`), contract-PDF render, `seal_envelope` (executed PDF + Certificate of Completion), `sweep_renewals` (hourly beat), `email.flush_outbox` (60s beat).
- `storage.py` — S3-compatible (`boto3`) when `S3_BUCKET` is set, local-filesystem fallback under `apps/api/storage/` otherwise. Per-tenant key prefix `tenants/<id>/…`.
- `email.py` + `email_outbox` table — `send_email()` writes a row, attempts immediate delivery (console backend in dev / SMTP in prod), records status; the outbox-flush beat retries up to 5 attempts.
- `pdf.py` — ReportLab renderers. Three outputs: draft contract PDF (with watermark), executed PDF (with Signatures page + per-tab coordinate stamping via pypdf + ReportLab), Certificate of Completion.

### Frontend layering

[apps/web/src/](apps/web/src/) — Next.js App Router with **route groups** for layout sharing:

- `app/(auth)/` — login, MFA step, register (no app chrome).
- `app/(app)/` — the signed-in shell (dashboard, contracts, inbox, workflows, reports, intelligence, audit, settings, team, templates).
- `app/(portal)/sign/[token]/` — the **unauthenticated** public signing portal. Don't add anything that needs auth here.
- `components/` — flat (not feature-sliced). `shell.tsx` = 3-pane chrome; `block-editor.tsx` = Tiptap; `workflow-builder.tsx`, `contract-form.tsx`, `lifecycle.tsx`, `security-panel.tsx`, `ui.tsx` (primitives), `widgets.tsx`.
- `lib/api.ts` — the **only** HTTP client. Uses `credentials: include` for the refresh cookie; de-dupes concurrent `/auth/refresh` calls via a shared promise; calls `setAccessToken(null)` on hard 401.
- Branding is a single CSS variable `--color-accent` in `app/globals.css`, populated from the tenant's `settings.accent_color`. Don't hard-code brand colors elsewhere.

### Background jobs and queues

Celery is configured in [apps/api/app/celery_app.py](apps/api/app/celery_app.py). Named queues: `ocr` (OCR pipeline) and `default` (everything else). `task_routes={"ocr.*": {"queue": "ocr"}}` — name OCR tasks `ocr.<something>` and they'll be routed automatically. `CELERY_TASK_ALWAYS_EAGER=true` (the local-dev default) runs tasks inline in the caller — `docker-compose` sets it `false` and runs a real worker. Long-running jobs should also write a `background_jobs` row so the web **Progress Tray** can surface them.

### Lifecycle state machine

[apps/api/app/lifecycle.py](apps/api/app/lifecycle.py) defines `TRANSITIONS: dict[str, set[str]]`. The spine is `draft → in_review → approved → out_for_signature → signed → active → expiring`. Side states: `changes_requested`, `rejected`, `declined`, `voided`, `terminated`, `renewed`, `expired`. **When an approval workflow run is active, generic status actions are blocked** — go through the workflow's `decide` endpoint instead.

### Production-config tripwire

[main.py](apps/api/app/main.py) calls `settings.validate_for_production()` on startup. When `ENV != "dev"` the app refuses to boot if `SECRET_KEY` is still the dev default (or shorter than 32 bytes), `COOKIE_SECURE` is false, `MFA_ENCRYPTION_KEYS` is empty, CORS still contains localhost, or `DATABASE_URL` is SQLite. Don't bypass this — if a dev/test env trips it, set `ENV=dev` or `ENV=test`.

## Things to know that bite

- **Migrations contain hand-written Postgres DDL** (RLS policies, encrypted columns). Don't run `alembic revision --autogenerate` and blindly accept the output — it won't see the policies. Hand-merge or use `--autogenerate` then audit.
- **`from app.tasks import …` triggers Celery app construction** (via [celery_app.py:29](apps/api/app/celery_app.py) `from . import tasks`). Avoid importing tasks at module-import time in code paths that should work without Redis.
- **Frontend access token in memory** means a full page reload **before** `/auth/refresh` completes will look unauthenticated for a beat — the boot flow in `lib/auth.tsx` handles this; don't add code that reads the token synchronously at module load.
- **Coordinates for signature tabs are 0..1 fractions with `y` measured from the top** (so on-page math matches the screen), but ReportLab's coordinate origin is bottom-left — the stamping code in `pdf.py` does the flip. If you add a new tab kind, mirror that convention.
- **The README's "What works" section is the single best feature index** — read it before adding behaviour that might already exist (renewals sweep, obligations, inbox, signature tabs, sent-waiting-on-others, etc.).
- **`docs/` is normative for unbuilt features.** Before designing something new (Arabic/RTL, workflow parallel groups, billing, real-time presence, PAdES signing, …), check the relevant `docs/NN-*.md` first — there is almost certainly a spec.

## Implementation status and the RFI gap

The canonical compliance/gap document is [docs/RFI-COMPLIANCE.md](docs/RFI-COMPLIANCE.md) (single-page dossier indexing docs 19–26 and 28 architectural decisions). Read it once; treat what follows as the **code-level operational summary** for working sessions.

### Maturity snapshot (as of 2026-05-19, post-hardening pass)

The codebase is a v1 **spine** at ~55–60% feature-completeness against enterprise/government RFI requirements. The 0013_hardening pass closed the three credibility-risk hotspots and most of the contained "other live risks" — the gap to v1 is now dominated by *features that need external infrastructure* (real OCR/AI providers, SSO IdP, NIFT signer, OTel collector), not by code-level shortcuts.

- Security readiness: **76/100** (+18 from baseline) — added: signing-token hashing+expiry, webhook secret encryption-at-rest, password policy (length + classes + blocklist + identity-echo), audit-log HMAC chain, Redis-backed rate-limit, S3 SSE on every PUT, K8s worker probes, real pytest. Still capped by: no SSO, no SoD enforcement, no CAPTCHA, no AV-on-upload, OCR/AI stub.
- Enterprise readiness: **52/100** (+10) — no SSO/SCIM, no clause library, no SLA engine, no parallel-approval groups, full-text search is `ILIKE` not `tsvector`, no real OCR/AI, no co-editing, mobile-responsive only.
- Government readiness: **48/100** (+20) — added: tamper-evident audit chain (HMAC per-tenant), encrypted signing-token storage. Still missing: NIFT/PAdES signer, RFC 3161 timestamps, separation-of-duties enforcement, compliance-mode toggle.

### What 0013_hardening closed (don't worry about these any more)

1. ✅ **Signing-portal access token is no longer plaintext** — [apps/api/app/models.py](apps/api/app/models.py) `SignatureRecipient` stores `access_token_hash` (SHA-256, indexed for /sign/{token} lookup) + `access_token_secret` (Fernet/AES-256-GCM ciphertext, decrypted server-side only for reminders) + `access_token_expires_at` (14-day default). Look-up by `recipient_by_token(db, raw)` hashes-then-queries; expired tokens return None (don't leak existence). See [apps/api/app/signing_service.py](apps/api/app/signing_service.py) `_mint_token_for`, `decrypt_token_for`, `_clear_token`.
2. ✅ **Webhook HMAC secret encrypted at rest** — `WebhookEndpoint.secret` is now `EncryptedString` (same Fernet chain as MFA). The router & service code didn't change — the `TypeDecorator` is transparent at the SQLA layer.
3. ✅ **Password strength policy** — [apps/api/app/security.py](apps/api/app/security.py) `validate_password_strength()` enforces: min 12 chars in production (8 in dev), ≥3 of {lower, upper, digit, symbol}, blocklist (30+ common passwords), rejects email-local-part / name substrings, rejects trivial sequences/repeats. Wired into `/auth/register` and `/auth/change-password`.
4. ✅ **Rate-limit is Redis-backed (fail-open)** — [apps/api/app/middleware/rate_limit.py](apps/api/app/middleware/rate_limit.py) `_RedisStore` runs an atomic Lua refill+consume so multi-replica state stays consistent. Set `RATE_LIMIT_STORE=redis`. Falls back to in-memory if Redis unreachable + warns to SIEM.
5. ✅ **Audit-log hash chain (tamper evidence)** — every row stores `prev_hash` + `row_hash` = `HMAC-SHA256(audit_chain_key, prev_hash || canonical(row))`. Per-tenant chain with Postgres `pg_advisory_xact_lock` to serialize concurrent inserts. `audit.verify_chain(db, tenant_id)` is the auditor's recompute-and-detect tool. Pre-chain rows (created before 0013) are skipped (empty hashes).
6. ✅ **S3 SSE on every PUT** — [apps/api/app/storage.py](apps/api/app/storage.py) honors `s3_sse` (`AES256` | `aws:kms`) + `s3_sse_kms_key_id`. Defence-in-depth on top of bucket-default SSE.
7. ✅ **Composite indexes + Postgres JSONB** — 0013_hardening adds `(tenant_id,status)`, `(tenant_id,owner_id,status)`, `(envelope_id,sequence)`, `(tenant_id,contract_id,status)`, `(tenant_id,at)` etc. and converts the queried-by JSON columns to JSONB + GIN on Postgres (no-op on SQLite/MSSQL).
8. ✅ **K8s worker liveness/readiness probes** — [infra/k8s/deployment-api.yaml](infra/k8s/deployment-api.yaml) uses `celery inspect ping` (round-trip through broker) for both probes + startupProbe + 60s graceful termination.
9. ✅ **Real pytest suite** — [apps/api/tests/](apps/api/tests/) covers signing-token storage (no plaintext persisted, lookup by hash, expiry, decrypt round-trip, clear), audit-chain integrity (chain links, edit detection, deletion detection, per-tenant isolation), refresh-token reuse detection (whole chain burned on reuse), lifecycle state machine, password policy. CI ratcheted from import-smoke to `pytest -v` against the Postgres + Redis service containers.

### Credibility-risk hotspots still open

1. **OCR/AI is a deterministic stub presenting as real** — [apps/api/app/tasks.py](apps/api/app/tasks.py) `ocr.*` tasks return random-seeded fake extraction. UI shows confidence scores from the stub. Roadmap **T-5** swaps the implementation behind the existing interface to Textract/Document Intelligence/GPT-class. Until that lands, sales/RFI material must call out that AI features are scaffolded, not live.
2. **MSSQL "portable" claim silently degrades to app-layer isolation** — the RLS migration in [apps/api/migrations/versions/0002_rls.py](apps/api/migrations/versions/0002_rls.py) is Postgres-only. On MSSQL, RLS is not created and only the repository-layer `tenant_id` filter holds the line. [docs/25-database-portability.md](docs/25-database-portability.md) documents this; the *only* honest deployment story right now is Postgres-first.
3. **No SSO / SCIM / WebAuthn** — biggest single procurement blocker. Designed (docs/19) but not wired. Roadmap T-3.
4. **No NIFT / PAdES / RFC 3161 signing provider** — biggest government-readiness gap. Pluggable signer slot exists (designed in docs/19). Roadmap T-4.
5. **No CAPTCHA / no antivirus on upload** — both currently operator/gateway concerns, not app-implemented. Roadmap items T-9 (AV) and external (CAPTCHA at WAF/CDN).
6. **`audit_log` is unpartitioned** — the hash chain is in, but at scale (>10M rows) the table needs PG declarative partitioning by month. Operator step.

### Roadmap — pick work from here, not from intuition

P0 (operator must do before first production deploy) and P1–P3 (engineering quarters) are listed in [docs/RFI-COMPLIANCE.md §9](docs/RFI-COMPLIANCE.md). The remaining shortlist after 0013_hardening, ordered by risk-closed per unit of engineering effort:

1. **T-1 OpenTelemetry + `/metrics`** — wires the monitoring story the RFI dossier promises. Highest-leverage operability item.
2. **T-3 SSO/OIDC + SAML + SCIM** — biggest single procurement unblocker; pluggable identity slot is already designed (see [docs/19-security-trust.md](docs/19-security-trust.md) and [docs/16-api-architecture.md](docs/16-api-architecture.md)).
3. **T-4 Pluggable signing provider (NIFT / Adobe / DocuSign trust services / eIDAS PAdES-LT)** — single biggest government-readiness unlock.
4. **T-5 Real OCR/AI provider behind the existing interface** — closes the lone remaining credibility risk.
5. **T-11 `tsvector` full-text search on contract body** — upgrade from current `ILIKE`. Postgres-only first; MSSQL FTS is the parallel implementation in the same seam. JSONB+GIN groundwork is already in place from 0013.
6. **`audit_log` declarative partitioning** — needed at scale; the hash chain in 0013_hardening is per-row so it survives partition splits.
7. **Step-up auth on sensitive actions** — re-prompt for password/MFA on role-change, webhook secret reveal, signature voiding (T-8).

### What this means for sessions

- If a feature touches one of the **credibility-risk hotspots**, fix the underlying issue in the same PR — don't extend the broken pattern.
- If a feature is in the **deferred roadmap** ([docs/RFI-COMPLIANCE.md §8](docs/RFI-COMPLIANCE.md) T-1…T-13), check the relevant `docs/` doc first; the interface design is usually already done.
- If a feature is **not in the dossier or docs/**, it's outside the v1 spec — surface that to the user before designing it.
