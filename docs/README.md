# Contract Management Platform — Product Design & Architecture Blueprint

**Codename:** working title `Dalilee Agreements` / `CM Platform` (rename freely)
**Type:** AI-powered, multi-tenant E-Agreement / E-Contract Lifecycle Management (CLM) SaaS
**Stack:** FastAPI · Celery · Redis · PostgreSQL · S3 · Next.js (App Router) · React · TypeScript · Tailwind · shadcn/ui · Docker · Kubernetes-ready
**Languages:** English + Arabic (full RTL)
**Audience for this doc set:** product, design, frontend, backend, platform/devops, security.

This folder is the single source of truth for the *design language*, *UX architecture*, and *system architecture* of the platform. It is written so an engineering team can start building immediately.

---

## How to read this

| # | Doc | What's inside |
|---|-----|---------------|
| 01 | [Analysis & Strategy](./01-analysis-and-strategy.md) | Reference/attachment analysis, product positioning, design strategy, architecture strategy, UX principles, scalability thinking |
| 02 | [Design Concepts](./02-design-concepts.md) | 3 premium visual/UX directions, pros & cons, **the recommended direction** |
| 03 | [Design System](./03-design-system.md) | Color, typography, spacing, elevation, radii, motion, iconography, components, status systems, dark mode, RTL tokens |
| 04 | [Information Architecture](./04-information-architecture.md) | Module map, navigation model, sitemap, URL structure, permissions surface |
| 05 | [User Flows](./05-user-flows.md) | End-to-end journeys (create → approve → sign → renew), OCR flow, onboarding, external signer, mermaid diagrams |
| 06 | [Modules — Part 1 (Core)](./06-modules-part1.md) | Auth, MFA, Dashboard, Contract list, Contract detail, Creation wizard, Editor, Templates, Clause library |
| 07 | [Modules — Part 2 (Intelligence & Lifecycle)](./07-modules-part2.md) | OCR upload/processing/extraction, AI analysis, Workflow builder, Signature placement, Signing, Lifecycle timeline, Renewals, Expiry, Search, AI Assistant |
| 08 | [Modules — Part 3 (Admin & Trust)](./08-modules-part3.md) | Audit logs, Reports & analytics, Notification center, External client portal, Tenant management, Billing, Users & roles, Activity timeline, Settings |
| 09 | [OCR & AI Experience](./09-ocr-ai-experience.md) | The "intelligence layer" UX & service design — the differentiator |
| 10 | [Workflow Builder](./10-workflow-builder.md) | Visual automation canvas spec (nodes, edges, conditions, escalation) |
| 11 | [Contract Editor](./11-contract-editor.md) | Notion×Google Docs×PandaDoc editor spec (blocks, variables, AI, collaboration, versioning) |
| 12 | [Mobile Experience](./12-mobile-experience.md) | Responsive + PWA + native-feel patterns, camera OCR, push, quick actions |
| 13 | [Arabic & RTL](./13-arabic-rtl.md) | Bidi strategy, mirroring rules, typography, numerals, do's & don'ts |
| 14 | [Backend Architecture](./14-backend-architecture.md) | FastAPI service design, layering, async, Celery, caching, events, multi-tenancy |
| 15 | [Database Architecture](./15-database-architecture.md) | PostgreSQL schema (tables, relationships, partitioning, RLS), versioning, audit, ERD |
| 16 | [API Architecture](./16-api-architecture.md) | REST resource design, versioning, pagination, errors, webhooks, OpenAPI, rate limiting |
| 17 | [Folder Structure](./17-folder-structure.md) | Monorepo layout, backend module layout, frontend feature-sliced layout |
| 18 | [Infrastructure & Scalability](./18-infra-scalability.md) | Docker, K8s, autoscaling, queues, storage, observability, environments, CI/CD, cost levers |
| 19 | [Security & Trust](./19-security-trust.md) | AuthN/Z, RBAC matrix, tamper-evidence, e-sign legal model, encryption, audit, secure sharing, compliance map |

---

## TL;DR product picture

A company signs up → creates a **workspace (tenant)** → invites teammates with **roles** → either **drafts a contract in the editor** (from a template + clause library + AI assist) or **uploads a scanned PDF** → the **OCR + AI pipeline** extracts text, parties, dates, amounts, clauses, risks, and a summary → the contract runs through a **visual approval workflow** → goes out for **e-signature** (internal + external parties) → lands in a **secure vault** with a tamper-evident **audit trail** → the system **tracks expiry/renewal** and surfaces **risk & obligation alerts** on a **dashboard**. Everything is **bilingual (EN/AR, RTL)**, **API-first**, **multi-tenant**, and **queue-backed** for heavy work.

## Locked design direction (decided 2026-05-12 — see Doc 02 for the full case)

**Direction B — "Trust Workspace", skinned to the shared reference.** A calm, document-first surface with the **friendly, light, blue-accented, soft-rounded, generous-whitespace look of the attached dashboard reference** (Dropbox-style: airy 3-pane shell, colorful pastel "Quick Access"-style category tiles, big rounded cards, soft shadows, a solid-blue primary action, the live progress tray). Layered on top: a dedicated, visually distinct **"Intelligence" surface** (violet/cyan-tinted panels, confidence chips, glow-on-active) for OCR/AI moments. Light by default, first-class dark mode, RTL-native. It reads as *approachable + trustworthy* in ~90% of the app and *futuristic-AI* exactly where it should.

> **Branding is provisional.** The visual branding mirrors the shared reference for now; the **brand accent is a single design token** (`--color-accent`, currently a friendly azure blue) plus a small set of brand tokens — when the client supplies final branding (logo, colors, name), only Doc 03 §0/§2 changes. Nothing else in this doc set depends on the brand color.
