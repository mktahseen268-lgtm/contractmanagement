# 01 — Analysis & Strategy

## 1. Reference analysis

### 1.1 What was actually attached vs. referenced

The brief promised: logo/branding, scope document, competitor screenshots, reference systems, UI inspirations, workflow references. **What is concretely available right now is one UI inspiration image** — a Dropbox-style file-management dashboard — plus an explicit list of "feel like" products. This document analyzes that image in detail and treats the named products as the reference set. When the real branding/scope/competitor assets land, only **Doc 03 (Design System tokens)** and **Doc 02 (which concept is picked)** need revision; the architecture docs are asset-independent.

### 1.2 The attached inspiration image — what to take, what to drop

The reference is a SaaS file/storage dashboard (Dropbox/Drive/OneDrive aggregator). Reading it as a designer:

**Worth stealing:**
- **3-pane shell**: persistent icon rail (far left) → contextual sidebar (storage sources, shortcuts) → main content → right "activity / details" drawer. This maps *perfectly* onto a CLM: rail = product areas, sidebar = saved views/folders/filters, main = contract list/detail, right drawer = activity feed + AI panel + signers.
- **"Quick Access" tile row**: large, friendly category tiles (Images, Videos, Music…). Our analogue: **"Quick Create"** tiles — *New from template*, *Upload & scan (OCR)*, *Blank contract*, *Import bulk*, *Request signature* — at the top of the dashboard.
- **Storage-source cards with radial progress**: visually light KPI cards with a single donut metric. We reuse the *shape* for **Contracts by stage**, **Approvals SLA health**, **Signature completion rate**.
- **Live "Uploading 3 items 78%" toast** with per-file rows, Failed/Retry states: this is exactly the pattern for **batch OCR ingestion** and **bulk import** — a dockable, minimizable progress tray.
- **Soft, low-contrast surface**: lots of white, gentle blue accent, generous radii, very light shadows. This is the right *baseline* temperature for a trust product.
- **Activity rail with grouped time buckets** ("1 minute ago", "13:34", "11:03") and avatar stacks: our **contract activity timeline** and **audit feed** look like this.

**Worth dropping / fixing for an enterprise CLM:**
- It's a *consumer* file manager — low information density, decorative thumbnails, playful copy. Enterprise CLM users live in **tables, filters, bulk actions, and statuses**. We keep the calm surface but raise density and add a real data grid.
- No notion of *state machine* (draft→review→signed→active→expired), *roles*, *legal trust signals*, or *audit*. Those are the spine of our product and must be visually first-class (status pills, lifecycle bars, "verified" seals).
- Accent-only blue with no semantic system. We need a full **status color system** (draft / in review / approved / out for signature / signed / active / expiring / expired / terminated / rejected) plus risk severity scale.
- No dark mode, no RTL. Both are hard requirements here.

### 1.3 Reading the named "feel like" set — what each contributes

| Product | What we take | Where it shows up |
|---|---|---|
| **DocuSign / Adobe Sign / Dropbox Sign** | Drag-to-place signature/initial/date fields on a document, recipient ordering, signing ceremony, certificate of completion, legal disclosures | Signature placement UI, signing experience, audit certificate |
| **PandaDoc** | Document-as-blocks editor, content library, pricing tables, "send & track" analytics, template variables | Contract editor, templates, send-tracking on contract detail |
| **Stripe Dashboard** | Dense-but-calm data, restrained color, world-class tables/filters, empty states, the "this is serious money infrastructure" tone, great API docs feel | Overall structural design language, settings, billing, dev/API area |
| **Notion** | Block editor, slash menu, inline databases, calm typography, "/" everything, comments | Contract editor, clause library as a database, internal notes |
| **Linear** | Speed, keyboard-first, command palette (⌘K), crisp dark mode, issue-list ergonomics, opinionated minimalism | Performance bar, ⌘K command menu, list views, keyboard shortcuts |
| **ClickUp** | Visual automation builder, multiple view types (list/board/timeline), bulk editing | Workflow builder, contract views (list / board by stage / calendar by expiry) |
| **Monday.com** | Friendly status columns, color-coded pulses, drag-drop, "anyone can configure this" approachability | Workflow builder, custom fields, board view |
| **Deel** | Enterprise + global + compliance tone, contract-centric onboarding, country/entity awareness, document vault polish | Tenant onboarding, compliance surfaces, external party portal |

**Synthesis:** the product should *structurally* behave like **Stripe + Linear** (dense, fast, keyboard, restrained), *editorially* like **Notion + PandaDoc** (blocks, slash, content library), *operationally* like **ClickUp/Monday** (visual workflows, multiple views), and *ceremonially* like **DocuSign** (signing is a deliberate, trustworthy ritual). The attached Dropbox reference contributes the **calm 3-pane shell + live progress tray + friendly quick-actions** layer that softens the enterprise rigor.

---

## 2. Product positioning

**One line:** *The contract system of record that reads, routes, signs, and watches your agreements — for teams that can't afford to miss a clause or a renewal.*

**Who it's for** (from the brief): enterprises, government, legal firms, real estate, HR, logistics, procurement — i.e. *anyone whose obligations live in PDFs*. These buyers care about: audit defensibility, access control, Arabic support, on-prem/private-cloud friendliness, and *not* paying per-seat-per-feature like the incumbents.

**Why we win** (the three wedges):
1. **Intelligence built-in, not bolted-on.** OCR + AI extraction + risk + obligations are core, multilingual (Arabic-first OCR is rare and valuable in this region), and surfaced as *trust-calibrated* (confidence scores, "verify this" affordances) rather than magic-black-box.
2. **Workflow + lifecycle in one place.** Most tools do *signing* OR *CLM*. We do create → negotiate → approve → sign → store → renew → report as one continuous spine, with a visual builder a non-engineer can run.
3. **True bilingual / RTL enterprise UX.** Not a translated string file — a genuinely mirrored, Arabic-typography-aware product. This is a moat for MENA/GCC government & enterprise.

**Non-goals (v1):** we are not a CPQ engine, not an HRIS, not a full DMS for all company files. We are *contracts* — deep, not wide.

---

## 3. Design strategy

### 3.1 Design principles (the rules we'll defend in reviews)

1. **Calm by default, intelligent on demand.** 90% of screens are neutral, dense, trustworthy. The AI/OCR surfaces are visually distinct (tinted "intelligence" panels, confidence chips, subtle glow) so users *know* when a machine is talking — and trust it more because it's labeled.
2. **The document is the hero.** Whether drafting, reviewing, signing, or auditing, the contract content is the largest, highest-contrast object. Chrome shrinks; content grows.
3. **State is always visible.** Every contract everywhere shows: lifecycle stage, who's blocking, what's next. No hunting. The lifecycle bar is the product's heartbeat.
4. **Minimum clicks to the verb.** Every screen answers "what can I *do* here?" with 1–2 primary actions, top-right, always in the same place. Bulk actions appear on selection. ⌘K does everything.
5. **Trust is a visual language.** Verified seals, tamper-evident hashes, "locked" states, audit chips, signed-by avatars with timestamps — security is *shown*, not just enforced.
6. **Progressive disclosure.** Wizards for first-time complex tasks (create contract, build workflow), power-density for repeat tasks. Never make the expert click through a wizard they've done 50 times.
7. **Bilingual is a first-class layout constraint, not a post-process.** Every component is designed in LTR and RTL from day one. Logical CSS properties only. Icons that imply direction get mirrored; brand marks and document content do not.
8. **Empty states sell the feature.** Every list's empty state explains the feature, shows a sample, and offers the primary action. (Stripe/Linear do this; the Dropbox ref doesn't — we will.)
9. **Errors are recoverable and specific.** "OCR failed on page 4 — low resolution. [Re-upload page] [Skip page] [Enter manually]." Never a dead end.
10. **Performance is a feature.** Sub-100ms interactions, optimistic UI, skeletons not spinners, virtualized tables, route-level code splitting. Slow = untrustworthy for a system of record.

### 3.2 Visual language summary (full tokens in Doc 03)

- **Surface:** light-first, near-white canvas (`#FBFCFD`), white cards, hairline borders (`#E6E8EB`), shadows that are *barely there* (one soft layer). Dark mode is a true peer (deep slate `#0C0F14`, not pure black).
- **Brand accent:** a **friendly azure blue** (`#3E7BFA`-family) — matching the shared dashboard reference's branding (decided 2026-05-12; later changeable on client request). It's a single `--color-accent` token (Doc 03 §0/§2): the solid primary button, active nav/rail, links, focus rings, KPI donuts. *(Earlier drafts of this doc set referenced an indigo→violet brand accent; that's superseded — see Doc 02's DECISION section and Doc 03 §0.)*
- **Intelligence accent:** a distinct **violet ↔ cyan "aurora"** tint reserved *only* for OCR/AI panels, confidence meters, and the AI assistant — deliberately *not* the brand blue, so machine-generated content is always instantly recognizable and stays distinct from the workhorse UI.
- **Status system:** 10 lifecycle states + 4-step risk severity, each with a fill, a text tone, and an icon — consistent everywhere (lists, detail, timeline, badges).
- **Type:** `Inter` (or `Geist`) for UI; `IBM Plex Sans Arabic` (or `Noto Sans Arabic` / `Cairo`) for Arabic; a serif (`Lora` / `Source Serif`) *only* inside the contract document body to feel "legal/printed". Tabular numerals everywhere numbers align.
- **Radius:** 8px default, 12px cards, 6px inputs, 999px pills. **Motion:** 150–250ms, ease-out, spring on drag; respects `prefers-reduced-motion`.
- **Density:** "comfortable" default with a "compact" toggle for power users on tables.

### 3.3 Component strategy

Build on **shadcn/ui** primitives (Radix under the hood — accessible, unstyled, headless) → wrap in a thin in-house `@cm/ui` package that bakes in our tokens, RTL behavior, and a few CLM-specific compound components: `LifecycleBar`, `StatusPill`, `ConfidenceChip`, `SignerRow`, `RiskBadge`, `AuditEntry`, `DocViewer` (PDF + overlay layer), `BlockEditor`, `WorkflowCanvas`, `KpiCard`, `EmptyState`, `ProgressTray`. Everything composable, everything keyboardable, everything documented in a Storybook.

---

## 4. UX strategy & thinking

### 4.1 The user roster (personas → what they need from the UI)

| Persona | Primary jobs | UX implications |
|---|---|---|
| **Contract Author** (legal ops, procurement specialist) | Draft from template, run negotiation, send for approval/signature | Best-in-class editor, clause library, redlines/comments, "send" flow |
| **Approver** (manager, finance, legal counsel) | Review what's blocking *them*, approve/reject with comment, escalate | A focused "My approvals" inbox; approve from email/mobile in 2 taps; clear "why am I seeing this" |
| **Signer — internal** | Sign quickly, see what they're signing | Mobile-first signing ceremony, signature/initials presets |
| **Signer — external** (client, vendor, counterparty) | Receive link, verify identity, review, sign — *without* an account | Branded, no-login (or light-OTP) external portal; mobile-perfect; accessible |
| **Workflow Designer / Admin** | Build approval routes, custom fields, templates, roles | Visual builder, no-code conditions, simulate/test mode |
| **Tenant Admin / Owner** | Manage users, roles, SSO, billing, security policy | Settings hub, RBAC matrix UI, audit export, SSO config |
| **Legal / Compliance Auditor** | Reconstruct "what happened, when, by whom" | Immutable audit log with filters, export, certificate of completion, evidence package |
| **Executive / Department Head** | "Are we exposed? What's expiring? Where are we slow?" | Dashboard: risk, expiry, approval-bottleneck analytics, scheduled reports |
| **Platform Operator** (our SaaS team) | Manage tenants, plans, feature flags, usage | Internal admin (separate surface), tenant list, impersonate-with-audit |

### 4.2 The "spine" — the lifecycle the whole product orbits

```
DRAFT ──▶ IN REVIEW ──▶ APPROVED ──▶ OUT FOR SIGNATURE ──▶ SIGNED ──▶ ACTIVE ──┬──▶ EXPIRING ──▶ EXPIRED
  │           │            │                 │                                 │
  └─ rejected ┘            └─ sent back       └─ declined / voided               └──▶ RENEWED (→ new ACTIVE)
                                                                                 └──▶ TERMINATED
```
Every screen, badge, filter, automation trigger, and analytic references this. The `LifecycleBar` component renders it inline on the contract detail and as a compact dot-track in lists.

### 4.3 Navigation & IA thinking (details in Doc 04)

- **Three-pane shell** (from the Dropbox ref, enterprise-ized): **icon rail** (Home/Dashboard · Contracts · Workflows · Templates & Clauses · Intelligence/OCR · Reports · Audit · Settings) → **contextual sidebar** (saved views, folders, filters, teams) → **content** → **right drawer** (activity, AI assistant, signers, comments — tabbed).
- **⌘K command palette** is the real navigation for power users: jump to any contract, run any action, switch tenant, toggle theme/language.
- **Breadcrumbs + persistent contract header** so you never lose context inside a deep contract.
- **One "+" creation entry** (top of sidebar, also ⌘K) → opens the create chooser (template / upload-OCR / blank / import).

### 4.4 Interaction patterns we standardize

- **Optimistic everything** with toast + undo where reversible.
- **Side-sheets over full-page navigations** for quick edits (edit metadata, add signer, comment) — keeps context.
- **Bulk bar** slides up from the bottom on multi-select (assign, change stage, add tag, export, delete).
- **Inline editing** in tables for safe fields (tag, owner, due date); side-sheet for risky ones.
- **Sticky action bar** at the bottom of long forms/wizards (Back · Save draft · Continue).
- **Real-time presence** (avatars) on contracts being co-edited / co-reviewed.
- **The Progress Tray** (Dropbox ref's killer pattern): a dockable, minimizable bottom-right panel that tracks any long async job — OCR batches, bulk imports, PDF generation, mass-send — with per-item status + retry. One pattern, reused everywhere Celery is involved.

### 4.5 Trust & security UX (full spec in Doc 19)

- A **"Verified" seal** with a popover showing the document hash, signing certificate, timestamp authority, and "this document has not been altered since signing."
- **Tamper indicator**: if a stored file's hash doesn't match, the contract header turns into a red "Integrity warning" state.
- **Access transparency**: contract detail → "Access" tab shows everyone who *can* see it and everyone who *did* (with device/IP/location), exportable.
- **Secure share links**: expiry, view/download/sign permission, optional passcode, optional email-verification, revocable, all link events audited.
- **Session & device management** in user settings (sign out other sessions, see logins).
- **Sensitive actions** (export audit, change roles, delete contract, disable MFA) require **re-auth / step-up MFA** and produce a high-visibility audit entry.

### 4.6 Accessibility commitments

WCAG 2.2 AA: visible focus rings, 4.5:1 text contrast, full keyboard operability (incl. the workflow canvas and signature placement — arrow-key nudging), `prefers-reduced-motion`, `prefers-color-scheme`, screen-reader labels on every icon button, ARIA live regions for async progress and toasts, no color-only status (always icon + text), 44px min touch targets, resizable text to 200%.

---

## 5. Architecture strategy (the "why" — details in Docs 14–19)

### 5.1 Shape of the system

**A modular monolith backend behind an API gateway, with the heavy/slow stuff pushed onto a Celery worker fleet, plus a thin set of separately-scalable specialist services (OCR, AI inference).** Frontend is a Next.js app (App Router, server components for data-heavy pages, client components for the editor/canvas/signing). Everything containerized, K8s-ready, S3 for blobs, PostgreSQL as the system of record, Redis as broker + cache.

Why not full microservices on day one? Because the domain (contracts) is cohesive, the team is finite, and distributed transactions across "contract / approval / signature" would be self-inflicted pain. We **modularize hard inside the monolith** (clear module boundaries, no cross-module DB reads, internal service interfaces) so that *when* OCR/AI/notifications need independent scaling or independent deploy cadence, they lift out cleanly. OCR and AI are the obvious first extractions and are designed as services from the start (they already are — they live behind a queue).

### 5.2 Layering (backend)

```
HTTP (FastAPI routers)  ─▶  validates I/O (Pydantic schemas), authn/authz, returns DTOs
        │
Application services    ─▶  use-cases / orchestration ("CreateContract", "SubmitForApproval",
        │                    "AdvanceWorkflow", "PlaceSignature"); transactions live here
Domain                  ─▶  entities, value objects, state-machine rules, domain events
        │
Infrastructure          ─▶  repositories (SQLAlchemy), S3 client, Redis, email, OCR/AI clients,
                             search index, signing/crypto, webhook dispatcher
```
Routers never touch the ORM. Services never touch `Request`. Domain never imports infrastructure. Background tasks call the *same* application services as HTTP handlers.

### 5.3 Async & jobs

Anything that can take >1–2s or fail transiently goes to **Celery** (Redis broker, separate result backend if needed): OCR pipeline, AI analysis, PDF render/flatten, bulk import, mass-send, email/SMS, webhook delivery (with retry/backoff + DLQ), scheduled jobs (expiry scans, renewal reminders, report generation, audit retention). Jobs are **idempotent**, carry a **tenant id**, write progress to a `jobs` table (so the Progress Tray and any UI can poll/subscribe), and emit domain events on completion. Queues are **named and prioritized** (`ocr`, `ai`, `pdf`, `email`, `webhooks`, `default`, `low`) so a flood of bulk imports never starves an interactive PDF render. Beat schedules the cron-like work.

### 5.4 Multi-tenancy

**Shared database, shared schema, `tenant_id` on every tenant-scoped row, enforced by PostgreSQL Row-Level Security** as a hard backstop *and* a mandatory `tenant_id` filter in the repository layer (defense in depth). A request's tenant is resolved from the JWT (and/or subdomain) and pinned into a context var → set as a Postgres session variable → RLS policies key off it. Per-tenant **isolated S3 prefixes** and **per-tenant encryption keys** (envelope encryption via KMS) for blob storage. Heavy tenants can later be promoted to a **dedicated schema or dedicated database** without app changes (the repository abstracts the connection). Plans/quotas/feature-flags are tenant attributes checked centrally.

### 5.5 Data strategy

- **PostgreSQL** for everything transactional + the source of truth.
- **Contract versioning**: contracts have immutable `contract_versions` (full content snapshot + diff metadata); the "current" pointer moves; nothing is destroyed.
- **Audit log**: append-only, hash-chained (each entry includes the hash of the previous → tamper-evident), partitioned by month, never updated or deleted by application code, exportable as a signed evidence package.
- **OCR/AI results**: stored as structured JSONB (extractions, bounding boxes, confidence) linked to the document + page, versioned per re-run.
- **Search**: PostgreSQL full-text + `pg_trgm` for v1 (good enough, one less system); pluggable to OpenSearch/Meilisearch when scale demands. AI "semantic search" uses `pgvector` embeddings of clauses/contracts.
- **Partitioning** on the big append-only tables (audit, activity, notifications, jobs) by time; `tenant_id` always in the leading index.
- **Read replicas** for reporting/analytics queries so dashboards never hit the primary hard.

### 5.6 Events & integration

Internal **domain events** (`ContractSubmitted`, `ApprovalGranted`, `SignatureCompleted`, `ContractExpiringSoon`, …) drive: notifications, webhooks (outbound, signed payloads, retried), analytics rollups, and workflow advancement. Outbound **webhooks** + an **API** make the platform a hub (HRIS, ERP, e-sign legal vendors, storage). Inbound **integrations** (SSO/SAML/OIDC, SCIM provisioning, email-to-contract, Slack/Teams notifications) are pluggable adapters. A lightweight in-process event bus on day one; swap to Redis Streams / a real broker if/when fan-out grows.

### 5.7 Security & compliance posture

JWT access tokens (short-lived) + rotating refresh tokens (httpOnly cookie, refresh-token reuse detection), RBAC + resource-level ACLs, MFA (TOTP + email/SMS OTP, WebAuthn-ready), SSO/SAML/OIDC for enterprise, SCIM for provisioning, encryption in transit (TLS everywhere) and at rest (DB-level + envelope-encrypted blobs with per-tenant keys), secrets in a vault, full audit trail, rate limiting + WAF, CSP/security headers, signed URLs for downloads, PII minimization, configurable data residency (S3 region per tenant), retention policies, and a documented mapping toward SOC 2 / ISO 27001 / GDPR / regional data-protection laws. E-signature legal model (intent, consent, attribution, integrity, retention) is explicit (Doc 19).

### 5.8 Observability & ops

Structured JSON logs with `tenant_id` / `request_id` / `user_id` correlation, OpenTelemetry traces across HTTP→service→DB→queue, Prometheus metrics (request latency, queue depth/age, job success rate, OCR pages/min, AI tokens, error rates), Grafana dashboards, alerting on SLOs (API p95, queue age, error budget), Sentry for exceptions, audit-grade access logs, per-tenant usage metering. Health/readiness probes, graceful shutdown (drain queues), blue-green or rolling deploys, DB migrations gated in CI, automated backups + tested restores, infra-as-code.

---

## 6. Scalability strategy (the "how it grows")

| Dimension | Day-1 design that makes it cheap later |
|---|---|
| **Traffic / API** | Stateless FastAPI behind an LB → horizontal pod autoscaling on CPU + request latency. Sessions in Redis/JWT, nothing on the pod. |
| **Heavy work spikes** (someone bulk-imports 5,000 PDFs) | Named, priority queues + KEDA-style autoscaling of workers on queue *age* (not just depth). Interactive queues (`pdf`, `email`) always have headroom; bulk lands on `low`. |
| **OCR / AI cost & throughput** | These are separate, independently scalable services behind their own queues; can run on GPU node pools or burst to managed APIs; results cached and reused; confidence-gated re-runs only. Pluggable provider interface (Tesseract/PaddleOCR/textract/Azure/Google; OpenAI/Anthropic/local) so we optimize cost without app changes. |
| **Database** | `tenant_id`-leading composite indexes everywhere; time-partitioning on append-only tables; read replicas for analytics; connection pooling (PgBouncer); the big tenant escape hatch = dedicated schema/DB via the repo abstraction; archival of old audit/activity to cold storage. |
| **Storage** | S3 (or compatible) — effectively infinite; per-tenant prefixes; lifecycle policies (hot→infrequent→glacier for old versions); CDN for static + signed-URL streaming for documents. |
| **Real-time / collaboration** | Editor & presence via a separate WS/CRDT service (Yjs-style) so collab load never touches the API tier; can scale independently or be feature-gated by plan. |
| **Search** | Start on Postgres FTS; the search interface is abstracted → drop in OpenSearch/Meilisearch + `pgvector`-or-dedicated-vector-DB when corpus size demands, without touching callers. |
| **Tenancy** | Shared-everything by default (cheap), with row-level isolation; promote noisy/large/regulated tenants to dedicated schema → dedicated DB → dedicated cluster, each step a config change not a rewrite. |
| **Multi-region / residency** | Stateless app + S3-region-per-tenant + DB-per-region (tenant pinned to a home region) is the target; day-1 single-region but no design choices that block it (no cross-region foreign keys, tenant id is the shard key). |
| **Frontend** | Next.js: route-level code splitting, server components for data-heavy pages (less JS shipped), edge caching of static/marketing, ISR where applicable, the heavy bits (editor, PDF, canvas) lazy-loaded only when entered. |
| **Cost levers** | OCR/AI provider choice + caching; cold-storage tiering of old versions; read-replica offload; queue priority to avoid over-provisioning workers; per-plan feature gating (real-time collab, advanced AI, white-label) so the expensive features are paid for. |

**Bottom line:** the architecture is "boring on purpose" where boring is safe (monolith, Postgres, REST) and *deliberately decoupled* exactly at the seams that will be put under load first (OCR, AI, notifications, search, real-time, big tenants). Nothing here forces a rewrite to 10× — each scaling step is an isolated, planned move.

---

## 7. What to do next (recommended sequencing)

1. **Lock the brand** (logo, color, name) → finalize Doc 03 tokens. Until then, the indigo/violet placeholder system in Doc 03 is production-safe.
2. **Pick the design direction** → Doc 02 recommends **Direction B ("Trust Workspace")**.
3. **Stand up the skeleton**: monorepo (Doc 17), FastAPI app + Postgres + Alembic + auth + tenancy + RLS, Next.js shell + design system package + Storybook, Docker compose for local, CI.
4. **Build the spine first**: contract CRUD + lifecycle state machine + the 3-pane shell + contract list + contract detail + audit log. Everything else hangs off this.
5. **Then the editor**, **then OCR/AI ingestion**, **then workflow builder**, **then signing**, **then renewals/reports**, **then admin/billing**. (This order maximizes demoability at each step.)
6. **Wire the Progress Tray + jobs table early** — it's needed the moment OCR exists and it's reused everywhere.
