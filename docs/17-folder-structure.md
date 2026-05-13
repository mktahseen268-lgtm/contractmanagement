# 17 — Folder Structure

A **monorepo** (pnpm workspaces + Turborepo for the JS side; the Python backend lives alongside as its own package with `uv`/`poetry`). One repo = atomic cross-cutting changes (an API change + its FE client update + a shared type), shared tooling, one CI. Below: the monorepo root, then the backend layout (FastAPI, module-per-bounded-context), then the frontend layout (Next.js App Router, feature-sliced).

---

## 1. Monorepo root

```
contract-management/
├── apps/
│   ├── api/                     # FastAPI backend (Python) — see §2
│   ├── worker/                  # Celery worker entrypoints + beat (imports apps/api package) — see §2
│   ├── web/                     # Next.js app: dashboard, contracts, editor, OCR, admin… — see §3
│   ├── portal/                  # (optional separate deploy) external signer/client portal — or a route group in web
│   └── platform-admin/          # internal SaaS-ops console (separate, internal-only) — Next.js, low priority
├── packages/                    # shared JS/TS packages
│   ├── ui/                      # @cm/ui — shadcn-based design-system components + tokens + RTL + Storybook
│   ├── api-client/              # @cm/api-client — generated from openapi.json: typed client + MSW mocks
│   ├── config-ts/               # shared eslint / tsconfig / tailwind preset / prettier
│   ├── i18n/                    # message catalogs (en/, ar/), the i18n runtime helpers, pseudo-loc
│   ├── icons/                   # @cm/icons — lucide re-export + custom marks (Verified seal, AI spark, file glyphs)
│   ├── editor/                  # @cm/editor — the block editor (Tiptap/Lexical) building blocks (shared by web & platform-admin)
│   ├── doc-viewer/              # @cm/doc-viewer — pdf.js wrapper + overlay layer (fields, boxes, comments, highlights)
│   ├── workflow-canvas/         # @cm/workflow-canvas — the visual builder canvas component
│   └── utils/                   # @cm/utils — money/date/number formatting, bidi helpers, validators, types
├── libs-py/                     # shared Python (if any code is shared beyond apps/api — usually keep it in apps/api)
├── infra/
│   ├── docker/                  # Dockerfiles (api, worker, web, portal), docker-compose.dev.yml
│   ├── k8s/                     # Helm charts / Kustomize overlays (dev|staging|prod), HPA/KEDA, ingress, secrets refs
│   ├── terraform/               # cloud infra (VPC, RDS/Postgres, ElastiCache/Redis, S3, KMS, IAM, queues, DNS, WAF, CDN)
│   └── ci/                      # reusable pipeline definitions
├── docs/                        # ← this folder (the design + architecture blueprint)
├── scripts/                     # repo-wide scripts (codegen openapi→client, seed data, migration helpers, release)
├── .github/  (or .gitlab-ci.yml / bitbucket-pipelines.yml)   # CI: lint, typecheck, test, build, migrate-check, e2e, security scan, deploy
├── turbo.json   pnpm-workspace.yaml   package.json   .nvmrc   .python-version
├── .editorconfig   .gitignore   .dockerignore   .env.example
└── README.md   CONTRIBUTING.md   ARCHITECTURE.md (→ links into docs/)
```

> If the external **portal** and **platform-admin** stay simple, they can be route groups inside `apps/web` (`app/(portal)/sign/[token]/…`, `app/(admin)/…` with separate auth) rather than separate apps — fewer deploys, shared components. Promote them to their own `apps/*` only when their deploy cadence, scaling, or security isolation needs diverge.

---

## 2. Backend — `apps/api` (FastAPI, module-per-bounded-context)

```
apps/api/
├── pyproject.toml   uv.lock (or poetry.lock)
├── alembic.ini
├── src/cm/                          # the importable package (apps/worker imports it too)
│   ├── main.py                      # FastAPI app factory: mounts routers, middleware, exception handlers, lifespan
│   ├── core/                        # cross-cutting, module-agnostic
│   │   ├── config.py                # Pydantic Settings (env / secrets manager)
│   │   ├── db.py                    # async engine, session, get_session dep, RLS session-var helper, UoW
│   │   ├── deps.py                  # FastAPI dependencies: current_user, current_tenant, require_role, require_feature, step_up
│   │   ├── security.py              # JWT issue/verify, password hashing, token rotation, step-up tokens
│   │   ├── tenancy.py               # tenant resolution (subdomain/JWT) + context var + RLS binding
│   │   ├── errors.py                # the typed exception hierarchy + the FastAPI handler → problem+json
│   │   ├── events.py                # the in-process bus + outbox dispatcher interface
│   │   ├── pagination.py            # cursor helpers   ├── ratelimit.py   ├── idempotency.py
│   │   ├── logging.py               # structured JSON logging + request_id middleware
│   │   ├── telemetry.py             # OpenTelemetry + Prometheus setup
│   │   ├── cache.py                 # Redis client + cache helpers
│   │   └── celery_app.py            # the Celery app, queue routes, beat schedule
│   ├── modules/                     # ← one folder per bounded context (Doc 14 §2)
│   │   ├── identity/
│   │   │   ├── router.py            # /auth, /users, /roles, /teams, /sessions, /api-tokens, SSO, SCIM
│   │   │   ├── schemas.py           # Pydantic request/response DTOs
│   │   │   ├── service.py           # IdentityService, AuthService, RbacService (use-cases)
│   │   │   ├── domain.py            # User, Role, Session entities; permission policies
│   │   │   ├── repository.py        # SQLAlchemy repos (tenant-scoped)
│   │   │   ├── models.py            # SQLAlchemy ORM tables (users, sessions, mfa_factors, roles, …)
│   │   │   ├── tasks.py             # Celery tasks (send invite email, cleanup sessions, SCIM sync)
│   │   │   ├── events.py            # events this module emits/consumes
│   │   │   └── tests/
│   │   ├── tenancy/                 # workspaces, teams-as-org-units, plans, feature flags, custom-field schemas, branding, settings
│   │   ├── contracts/               # the contract aggregate, versions, parties, obligations, attachments, ACL, lifecycle state machine, the block-document, comments, suggestions, relations/renewals
│   │   ├── templates/               # templates + template versions/variables/default-clauses; the clause library + clause versions/fallbacks; embeddings
│   │   ├── workflows/               # definitions + versions; the engine; runs/steps/events; timers; escalation; simulate; analytics
│   │   ├── signatures/              # envelopes, recipients, fields; the ceremony (token-auth endpoints); certificates; PDF flatten/seal
│   │   ├── intelligence/            # ocr_jobs/files/pages; ai_extractions/analyses; the assistant; semantic search; provider abstractions
│   │   ├── notifications/           # preferences; dispatch; channel adapters (in-app/email/push/Slack-Teams); digests
│   │   ├── audit/                   # the append-only hash-chained log; activity-stream projector; evidence-package export
│   │   ├── reporting/               # rollups; report definitions; scheduled reports; reads the replica
│   │   ├── billing/                 # plans; usage metering; the billing-provider integration; invoices; dunning
│   │   ├── integrations/            # webhook endpoints + signed dispatch + delivery log + replay; connector adapters
│   │   ├── files/                   # the abstraction over S3: upload, presign, hash, envelope-encrypt, versions, lifecycle tiering
│   │   ├── dashboard/               # the dashboard widget aggregators (reads cache/replica)
│   │   └── health/                  # /health, /ready, self-checks
│   ├── infra/                       # concrete adapters used across modules
│   │   ├── storage/s3.py            ├── email/ (provider clients + templates) ├── sms/
│   │   ├── ocr/ (paddle.py | tesseract.py | textract.py | azure.py — behind OCRProvider)
│   │   ├── ai/  (anthropic.py | openai.py | local.py — behind LLMProvider; prompt library)
│   │   ├── signing/ (crypto.py, pdf_flatten.py, timestamp_authority.py)
│   │   ├── search/ (pg_fts.py, pgvector.py — behind SearchIndex)   ├── push/   ├── slack_teams/
│   │   └── pdf/ (render.py — block-document → PDF, Arabic-aware)
│   ├── api/                         # the router aggregation: builds /api/v1 from each module's router; OpenAPI customization
│   └── cli.py                       # admin CLI (create-tenant, run-migrations, seed, reindex, rotate-keys, etc.)
├── migrations/                      # Alembic versions/  +  data migrations (separate, idempotent, batched)
├── tests/                           # cross-module + integration + e2e-ish tests (testcontainers Postgres, RLS on)
└── seeds/                           # default starter template/clause packs, the permission catalog, demo data
```

`apps/worker/` is tiny: a `celery_worker.py` and `celery_beat.py` that import `cm.core.celery_app` and the modules' `tasks.py` — deployed as separate processes, one deployment **per queue group** (`ocr` workers, `ai` workers, `pdf`+`email`+`notifications` workers, `imports`+`reports`+`low` workers, beat ×1) so each scales independently (Doc 18).

---

## 3. Frontend — `apps/web` (Next.js App Router, feature-sliced)

```
apps/web/
├── next.config.mjs   tailwind.config.ts (extends @cm/config-ts preset)   tsconfig.json
├── middleware.ts                    # tenant subdomain → header; locale/dir negotiation; auth gate (redirect to /login)
├── public/                          # static assets, fonts, manifest.json (PWA), service worker
├── src/
│   ├── app/                         # routes (App Router) — thin: layout + data fetch + compose features
│   │   ├── layout.tsx               # <html lang dir>, providers (theme, i18n, query client, toaster), fonts
│   │   ├── (auth)/                  # no-shell layout
│   │   │   ├── login/page.tsx   login/mfa/page.tsx   forgot/page.tsx   reset/[token]/page.tsx
│   │   │   └── accept-invite/[token]/page.tsx
│   │   ├── (app)/                   # the main 3-pane shell layout (icon rail + sidebar + content + drawer)
│   │   │   ├── layout.tsx
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── contracts/page.tsx   contracts/new/page.tsx
│   │   │   │   └── [id]/  page.tsx (overview)  document/  approvals/  signatures/  prepare-signature/  insights/  files/  activity/  access/  versions/[vid]/  renew/
│   │   │   ├── workflows/page.tsx   [id]/page.tsx (builder)   [id]/runs/page.tsx   [id]/runs/[runId]/page.tsx
│   │   │   ├── templates/page.tsx   [id]/page.tsx     clauses/page.tsx   [id]/page.tsx
│   │   │   ├── intelligence/page.tsx   upload/page.tsx   jobs/[id]/page.tsx   jobs/[id]/review/page.tsx   assistant/page.tsx
│   │   │   ├── reports/page.tsx   [key]/page.tsx   builder/[id]/page.tsx
│   │   │   ├── audit/page.tsx
│   │   │   ├── inbox/page.tsx   (notifications|approvals|signatures sub-tabs)
│   │   │   ├── search/page.tsx
│   │   │   ├── settings/  organization/  branding/  users/  roles/  teams/  security/  integrations/  custom-fields/  notifications/  billing/  data/  localization/  audit-retention/  (each page.tsx)
│   │   │   └── account/page.tsx
│   │   ├── (portal)/                # external — no app shell, tenant branding
│   │   │   └── sign/[token]/  page.tsx  ceremony/  done/        portal/[token]/page.tsx
│   │   ├── api/                     # Next route handlers ONLY for FE-owned concerns (auth cookie set/clear, webhooks-from-3rd-parties, BFF proxying if used); the real API is FastAPI
│   │   └── (marketing)/             # optional: landing/pricing/login-finder (or a separate site)
│   ├── features/                    # ← the meat: one folder per feature, owns its components/hooks/server-actions/state
│   │   ├── auth/   contracts/   contract-detail/   contract-editor/   creation-wizard/   dashboard/
│   │   ├── ocr/   ai-insights/   ai-assistant/   workflows-builder/   workflow-runs/   signatures-prepare/
│   │   ├── signing-ceremony/   templates/   clauses/   reports/   audit/   notifications/   inbox/
│   │   ├── search/   settings/   users-roles/   billing/   activity/   onboarding/
│   │   └── (each: components/  hooks/  api.ts (calls @cm/api-client)  store.ts (zustand/jotai if needed)  schemas.ts  index.ts)
│   ├── components/                  # app-level shared composites NOT in @cm/ui (the AppShell, IconRail, ContextSidebar, RightDrawer, TopBar, CommandPalette, ProgressTray, EmptyState variants, PageHeader, DataTable wired with our filters/saved-views)
│   ├── lib/                         # query client config, fetch wrapper (token refresh, error→toast), feature-flag client, analytics, formatters re-exports, permissions helper (can(user, 'contracts.edit', resource))
│   ├── hooks/                       # cross-feature hooks (useTenant, useCurrentUser, usePermissions, useRealtime (the WS stream), useProgressTray, useCommandPalette, useTheme, useDirection)
│   ├── styles/                      # globals.css (token CSS vars for light/dark), tailwind layers
│   └── i18n/                        # next-intl config; loads catalogs from @cm/i18n; locale routing/negotiation
├── e2e/                             # Playwright (the day-in-the-life flows from Doc 05 §9, LTR + RTL, mobile viewport)
└── .storybook/  → uses @cm/ui's stories  (or @cm/ui owns Storybook and web just consumes the package)
```

**Conventions:** routes (`app/`) are thin — fetch data (server components / server actions where it fits, otherwise the typed `@cm/api-client` from client components), pick the layout, render a feature's top-level component; **features** own their UI/logic/state and only import from `@cm/ui`, `@cm/api-client`, `@cm/utils`, `@cm/i18n`, `@cm/icons`, and other features' *public* `index.ts` (no deep imports); **data fetching** via TanStack Query (cache, optimistic updates, background refetch) over the generated client; **forms** via React Hook Form + Zod schemas (often generated from the OpenAPI request schemas); **state** that isn't server data via a light store (Zustand/Jotai) only where genuinely needed (command palette, progress tray, editor local state); **server components** for data-heavy read pages (less JS shipped), **client components** for the editor/canvas/signing/anything interactive; **code-split** by route automatically + lazy-load the heavy packages (`@cm/editor`, `@cm/doc-viewer`, `@cm/workflow-canvas`) only on the routes that use them; **all CSS** via Tailwind logical utilities + the token CSS vars (theme & dir swap with zero JS reflow); **i18n** everywhere (no hardcoded strings), **both directions** in every Storybook story; **accessibility** baked into `@cm/ui` (Radix primitives) and checked in CI (axe). The **mobile experience** (Doc 12) is the same components with responsive variants — the shell swaps to the bottom-tab layout under `sm`, heavy desktop-only surfaces show "best on desktop".
