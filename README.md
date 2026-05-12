# Contract Management Platform

An AI-powered E-Agreement / E-Contract lifecycle management SaaS — **multi-tenant, API-first**.

This repo contains:

| Path | What |
|---|---|
| [`docs/`](./docs) | The full product **design & architecture blueprint** (20 docs: design system, all 30 module designs, OCR/AI experience, workflow builder, editor, mobile, Arabic/RTL, backend/DB/API/infra/security). Start at [`docs/README.md`](./docs/README.md). |
| [`apps/api`](./apps/api) | **Backend** — FastAPI · SQLAlchemy · **PostgreSQL** (Alembic migrations · **Row-Level-Security multi-tenancy**) · JWT access tokens + **rotating refresh tokens in httpOnly cookies with reuse detection** · RBAC · **MFA (TOTP) + recovery codes + email OTP** · contract lifecycle state machine · dashboard · append-only audit log · **Celery + Redis** background jobs (OCR pipeline · **contract-PDF rendering**) · **S3-compatible object storage** (MinIO / local-filesystem fallback) for file uploads, the OCR pipeline & generated PDFs. A runnable subset of the blueprint ("the spine"). |
| [`apps/web`](./apps/web) | **Frontend** — Next.js (App Router) · TypeScript · Tailwind, in the locked "Trust Workspace" skin (friendly azure blue, airy, soft-rounded). 3-pane shell, dashboard, contracts list/detail (with a **Tiptap rich block editor** on the Document tab)/create/edit, OCR/AI workspace (drag-and-drop upload), audit log, settings + a **Security panel** (2FA, sessions, password), an **MFA sign-in step**. Access token kept in memory; cookie-based session bootstrap. |
| [`docker-compose.yml`](./docker-compose.yml) | Runs the whole stack: **Postgres + Redis + MinIO + API + Celery worker + web**. |

> **Status:** a working, dynamic full-stack app — real PostgreSQL with Alembic migrations, database-enforced tenant isolation (RLS), real CRUD, a real lifecycle state machine, a real append-only audit log, a real Celery/Redis-backed async OCR job, and real file uploads stored in S3-compatible object storage. It's the *core spine* of the blueprint, built so the remaining modules slot in. It is **not** fully production-hardened yet (see "Going to production" below).

---

## Run it with Docker (recommended — one command)

```bash
docker compose up --build
```

Brings up **Postgres** (`:5432`), **Redis** (`:6379`), **MinIO** (S3-compatible object storage — API on `:9000`, console on `:9001`, login `minioadmin`/`minioadmin`), the **API** (`:8000` — runs Alembic migrations + creates the `cm-files` bucket + seeds a demo workspace on first start), a **Celery worker** (processes the OCR queue), and the **web app** (`:3000`). Email (for MFA OTP) uses a **console backend by default** — the code is logged to the API container's stdout, so nothing else is needed; set `EMAIL_BACKEND=smtp` + `SMTP_*` for real delivery.

Open <http://localhost:3000> → sign in with the demo credentials (pre-filled on the login screen): **`demo@acme.io`** / **`demo1234`** (also `manager@acme.io`, `approver@acme.io`, `author@acme.io`, same password). API docs: <http://localhost:8000/docs>.

> If `5432` / `6379` / `8000` / `3000` are already in use on your machine, edit the `ports:` mappings in `docker-compose.yml`.

---

## Run it locally (without Docker)

You need **Python 3.11+**, **Node 18+**. For the full PostgreSQL experience also run a Postgres + Redis (the easiest way is `docker compose up -d db redis` from the repo root — that gives you Postgres on `:5432` and Redis on `:6379`).

### Backend (terminal 1)

```bash
cd apps/api
python -m venv .venv
# Windows:  .venv\Scripts\activate          macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
# .env defaults to postgresql://cm:cm@localhost:5432/cm — make sure Postgres is up
# (docker compose up -d db redis), or switch DATABASE_URL to the sqlite line in .env for a zero-setup look.
uvicorn app.main:app --reload --port 8000
```

On start the API runs `alembic upgrade head` (creates the schema + RLS policies on Postgres) and seeds a demo workspace (28 sample contracts, 4 users, audit history). `CELERY_TASK_ALWAYS_EAGER=true` in `.env` means OCR jobs run inline, so **you don't need a separate worker for the local path** — but if you want the real async behaviour, set it to `false` and run a worker:

```bash
# terminal 1b (optional — real async OCR via Redis)
cd apps/api && celery -A app.celery_app worker --loglevel=info -Q ocr,default
```

### Frontend (terminal 2)

```bash
cd apps/web
npm install
cp .env.local.example .env.local          # Windows: copy .env.local.example .env.local
npm run dev
```

Open <http://localhost:3000>.

> **Port already in use?** Run the API on another port (`uvicorn app.main:app --reload --port 8001`) and point the web app at it: set `NEXT_PUBLIC_API_URL=http://localhost:8001` in `apps/web/.env.local`, then `npm run dev -- -p 3001`.

> **No Postgres / no Docker at all?** Set `DATABASE_URL=sqlite:///./cm.db` in `apps/api/.env` (the RLS migration is automatically skipped on SQLite). Everything else works.

---

## What works

- **Auth & multi-tenancy** — register a workspace (you become Owner) or sign in. **JWT access tokens** (short-lived, kept in browser memory only) + **rotating refresh tokens in an httpOnly cookie** with **reuse detection** (presenting an already-rotated refresh token revokes the whole session chain). **MFA**: enrol a TOTP authenticator (QR-key + recovery codes), then sign-in requires a second step — verifiable by your authenticator code, a one-time **email OTP**, or a single-use **recovery code**. Manage active sessions, sign out other devices, change password (which revokes other sessions). **Tenant isolation is enforced at the database level by PostgreSQL Row-Level Security** (every tenant-scoped table — `contracts`, `audit_log`, `sessions`, `otp_codes`, `recovery_codes`, `file_objects`, … — has a `tenant_isolation` policy keyed off a per-request `app.cm_tenant` session GUC set from the JWT) *plus* a `tenant_id` filter in the repository layer (defence in depth). Verified: a contract/file created in workspace B is invisible (404) to workspace A's token, and vice-versa; each workspace's dashboard/audit only shows its own data.
- **PostgreSQL + Alembic** — schema is owned by Alembic migrations (`0001_initial` materialises the model state; `0002_rls` adds the RLS policies, Postgres-only); `alembic upgrade head` runs on startup (toggle with `RUN_MIGRATIONS_ON_STARTUP`).
- **Dashboard** — KPI cards (total / pending approvals / awaiting signature / expiring ≤30d / open risks / active value), Quick Create tiles, "Needs your attention", contracts-by-stage distribution, AI recommendations, team activity feed — all live from the API.
- **Contracts** — list with search + status/type/risk filters + sort + pagination + sidebar saved views; create (metadata form); edit metadata (when `draft`/`changes_requested`); detail page with the lifecycle bar, key terms, AI summary, **a rich block editor for the document** (Tiptap — toolbar with headings / bold / italic / lists / quote / code / divider / undo-redo + an "Insert variable" menu for merge fields `{{counterparty}}`, `{{value}}`, `{{effective_date}}`, … which resolve to the contract's values in the PDF and the read-only view; saves Markdown; editable when `draft`/`changes_requested`, read-only otherwise), per-contract activity, comments, **Files** (generated PDFs), **Versions** (a new version every save/restore — view any version's content read-only, restore one), delete.
- **Lifecycle state machine** — `draft → in_review → approved → out_for_signature → signed → active → expiring`, plus `changes_requested / rejected / declined / renewed / terminated / voided`. Invalid transitions are rejected (409). Each move is audited and notifies the owner. Light role gates (only approvers/managers/admins can approve).
- **Audit log** — append-only record of everything, searchable, paginated; privileged roles (owner/admin/auditor) see all, others see their own actions.
- **File storage** — uploads go to **S3-compatible object storage** (MinIO in Docker; a local-filesystem fallback at `apps/api/storage/` when `S3_BUCKET` is unset), per-tenant key prefixes (`tenants/<id>/…`), with a `file_objects` table (RLS-isolated like everything else — verified). `POST /files` (multipart), `GET /files/{id}`, `GET /files/{id}/download` (streamed).
- **OCR & AI workspace** (`/intelligence`) — **drag-and-drop a real document** (stored as above) or use the demo "file name" path → the API **enqueues a Celery job** (`queue: ocr`) → the worker (or, in eager mode, inline) produces a realistic extraction (type, parties, dates, value, per-field confidence scores, detected clauses, AI summary) → the frontend polls the job (`queued → processing → completed`) → "Open uploaded document" / "Create contract from this" (makes a `draft` contract from the extraction).
- **Contract PDF generation** — `POST /contracts/{id}/pdf` renders the contract (letterhead, key terms, the document body with light markdown, a "DRAFT — not executed" watermark for non-final statuses) via a Celery task (ReportLab) → stores it in object storage as a `contract_pdf` `FileObject` → returns it. The contract detail page has a **Files tab** (list & download generated PDFs) and a **PDF** button in the header (generate + download in one click).
- **Settings** — workspace info; users & roles list; add a user (owner/admin).
- **Notifications** — bell with unread count + dropdown; "mark all read".

`/workflows` and `/settings`' deeper areas show "in the blueprint" placeholders pointing at the relevant `docs/`.

---

## Project layout

```
contractmanagement/
├── docs/                          # the design + architecture blueprint (20 markdown docs)
├── apps/
│   ├── api/                       # FastAPI backend
│   │   ├── alembic.ini
│   │   ├── migrations/            # Alembic — env.py + versions/0001_initial, 0002_rls, 0003_files, 0004_auth
│   │   ├── app/
│   │   │   ├── main.py            # app factory · CORS · routers · startup (migrations + storage + seed)
│   │   │   ├── config.py          # Pydantic settings (.env): DB url, Redis, Celery, S3, JWT, cookies, MFA/OTP, email/SMTP, CORS …
│   │   │   ├── database.py        # SQLAlchemy engine/session/Base + the RLS tenant-context plumbing
│   │   │   ├── storage.py         # object-storage abstraction — S3Backend (boto3) / LocalFsBackend
│   │   │   ├── email.py           # email sender — console backend (logs) / smtp backend
│   │   │   ├── pdf.py             # ReportLab contract-PDF renderer (letterhead · key terms · markdown body · DRAFT watermark)
│   │   │   ├── models.py          # Tenant, User(+mfa), Contract, ContractVersion, Comment, AuditLog, Notification, OcrJob, FileObject, Session, OtpCode, RecoveryCode
│   │   │   ├── schemas.py         # Pydantic request/response models
│   │   │   ├── security.py        # password hashing · JWT (access + mfa-pending) · opaque tokens / codes
│   │   │   ├── auth_service.py    # sessions (rotation + reuse detection) · TOTP · recovery codes · email OTP · cookies
│   │   │   ├── deps.py            # auth deps — get_token_payload / get_current_user (sets the RLS tenant context) / current_session_id / require_role
│   │   │   ├── lifecycle.py       # the contract state machine
│   │   │   ├── audit.py           # append-audit-entry helper (+ optional notification)
│   │   │   ├── celery_app.py      # Celery app (broker/backend = Redis; named queues)
│   │   │   ├── tasks.py           # background tasks — the OCR/AI pipeline (realistic stub)
│   │   │   ├── seed.py            # demo-data seeder
│   │   │   └── routers/           # auth (login/MFA/refresh/sessions/password) · contracts · dashboard · audit · files · misc (users/notifications/ocr)
│   │   ├── requirements.txt · Dockerfile · .env.example
│   └── web/                       # Next.js frontend
│       ├── src/app/               # (auth)/login, login/mfa, register · (app)/dashboard, contracts/*, intelligence, audit, settings, workflows
│       ├── src/components/        # ui · shell · lifecycle · widgets · contract-form · security-panel · block-editor (Tiptap)
│       ├── src/lib/               # api (cookie-based; access token in memory) · auth (context, MFA flow) · types · utils
│       └── tailwind.config.ts     # design tokens — docs/03 §0
└── docker-compose.yml             # postgres · redis · minio · api · worker · web
```

---

## Going to production (what's deliberately simplified here vs. the blueprint)

This scaffold prioritises "clone and run". Before shipping, see the relevant docs and:

- ~~**DB**: PostgreSQL + Alembic + RLS~~ ✅ **done.** Still TODO for prod: a dedicated non-owner app DB role (so RLS is `FORCE`d for the app while migrations run as the owner — currently the single `cm` role is the owner, and RLS is `FORCE`d on all tenant tables so it *is* enforced), connection pooling (PgBouncer), read replicas, table partitioning on the append-only tables (docs/14, docs/15).
- ~~**Async**: Celery + Redis~~ ✅ **done** for the OCR job — TODO: wire the real OCR engine + LLM provider behind the provider interfaces, route email/PDF/notifications/bulk-import through their own queues, add the **Progress Tray** UI (docs/09, docs/14, docs/18).
- ~~**Storage**: S3-compatible object storage + a `files` table + generated contract PDFs~~ ✅ **done** (MinIO / local-fs fallback; ReportLab PDF render via Celery). Still TODO for prod: presigned PUT/GET URLs (so the browser uploads/downloads direct to S3 instead of streaming through the API), per-tenant encryption keys, lifecycle tiering, antivirus scan on ingest, faithful block-document PDF rendering + sealed/signed copies with the audit certificate (docs/11, docs/18, docs/19).
- ~~**Auth**: rotating refresh tokens (httpOnly cookies, reuse detection) + MFA (TOTP) + OTP~~ ✅ **done.** Still TODO: encrypt the stored TOTP secret at rest (currently plaintext), **SSO (SAML/OIDC) + SCIM** provisioning, **step-up auth** (re-prompt for password/MFA on sensitive actions like role changes / workspace delete), WebAuthn/passkeys, rate-limiting on the auth endpoints, and email-verification on signup (docs/19).
- **The block editor** ✅ a first cut (Tiptap, Markdown round-trip, toolbar, merge variables that resolve in the PDF/preview, a version-history tab with view & restore). TODO: the slash (`/`) command menu, variables as styled inline node-chips (not literal `{{...}}` text), clause inserts from a library, inline comments & suggestions (redlines), a side-by-side version diff, real-time collaboration (docs/11).
- **The workflow canvas, e-signature placement & signing ceremony, reports & analytics, billing, the external client portal, real-time presence, Arabic/RTL** — all designed in `docs/`, not yet built here.
- **Hardening**: rate limiting, security headers/CSP, audit-log hash chaining, observability (OTel/Prometheus/Sentry), CI, container scanning, backups (docs/18, docs/19).

---

## License / ownership

Internal project scaffold. Branding is provisional (mirrors the shared reference) — the brand accent is a single token (`--color-accent` in `apps/web/src/app/globals.css`); swap it when the client supplies final branding.
