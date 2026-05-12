# 04 — Information Architecture

How the product is organized: the navigation model, the module map, the sitemap, URL structure, and which permissions gate what.

---

## 1. Navigation model — the 3-pane shell

Inherited from the attached Dropbox reference, enterprise-ized:

```
┌────────┬──────────────────┬─────────────────────────────────────┬──────────────────┐
│ ICON   │ CONTEXTUAL       │ CONTENT                             │ RIGHT DRAWER     │
│ RAIL   │ SIDEBAR          │ (page header + body)                │ (tabbed,         │
│ (56px) │ (260px,          │                                     │  collapsible)    │
│        │  collapsible)    │                                     │                  │
│ Home   │  — depends on    │  [PageHeader: title · status ·      │ [Activity]       │
│ Contr. │    the active    │   breadcrumbs · actions · tabs]     │ [AI Assistant]   │
│ Wflows │    rail item —   │                                     │ [Signers]        │
│ T&C    │   e.g. for       │  ┌─────────────────────────────┐    │ [Comments]       │
│ Intel. │   Contracts:     │  │ DataTable / Detail / Editor │    │ [Details]        │
│ Reps   │   • All          │  │ / Wizard / Dashboard ...    │    │                  │
│ Audit  │   • My open      │  └─────────────────────────────┘    │                  │
│ ──     │   • Saved views  │                                     │                  │
│ Help   │   • Folders      │                                     │                  │
│ Avatar │   • Tags         │                                     │                  │
│ (acct, │   • Teams        │                                     │                  │
│  tenant│  [+ New]         │  [ProgressTray docks bottom-end ▸]  │                  │
│  swtch)│                  │                                     │                  │
└────────┴──────────────────┴─────────────────────────────────────┴──────────────────┘

Top bar (56px, spans content+drawer): ⌘K search · workspace switcher · notifications bell · help · theme toggle · language (EN/ع) · avatar menu
```

- **Icon rail** — top-level product areas; collapsed = icons + tooltips, expandable to icons + labels (preference, persisted). Active area highlighted with the brand accent. The `+ New` global create lives at the top of the sidebar (and in ⌘K).
- **Contextual sidebar** — changes per rail area; for Contracts it's saved views / folders / tags / teams; for Settings it's the settings sections list; for Reports it's report categories; collapsible to give the content full width.
- **Content** — `PageHeader` (title, lifecycle status if applicable, breadcrumbs, primary/secondary actions top-end, optional tabs row) + the body (table / detail / editor / wizard / dashboard / canvas).
- **Right drawer** — tabbed, contextual, collapsible, resizable: **Activity** (timeline), **AI Assistant** (the chat/insight panel — intelligence surface), **Signers** (on contracts in/after signature), **Comments**, **Details/Metadata**. On narrow viewports it becomes a slide-over.
- **⌘K command palette** — the real power-user nav: find any contract/template/person, run any action, switch workspace, toggle theme/language, go to any settings page. Recents pinned.
- **In RTL:** rail + sidebar mirror to the right edge, drawer to the left, everything flips per Doc 13.
- **Mobile:** rail → bottom tab bar (5 items: Home, Contracts, Inbox/Approvals, Scan, More); sidebar → a slide-over; drawer tabs → bottom-sheet tabs; see Doc 12.

---

## 2. Module map (30 modules → where they live)

| Rail area | Modules it contains |
|---|---|
| **Home / Dashboard** | 3 Enterprise Dashboard · 25 Activity Timeline (snippet) · 29 AI Assistant Panel (entry) |
| **Contracts** | 4 Contract Listing · 5 Contract Details · 6 Contract Creation Wizard · 7 Rich-Text Contract Editor · 13 Signature Placement UI · 14 Digital Signing Experience · 15 Contract Lifecycle Timeline · 26 Contract Expiry Tracking · 27 Renewal Management · 28 Smart Search (the ⌘K + advanced search) |
| **Workflows** | 12 Approval Workflow Builder (+ run history, escalation rules) |
| **Templates & Clauses** | 16 Template Management · 17 Clause Library |
| **Intelligence** | 8 OCR Upload · 9 OCR Processing · 10 OCR Extracted Data · 11 AI Analysis · 29 AI Assistant (full) |
| **Reports** | 19 Reports & Analytics |
| **Audit** | 18 Audit Logs (+ access transparency, evidence export) |
| **Inbox** (cross-cutting, also a mobile tab) | 20 Notification Center · "My Approvals" · "My Signatures" |
| **Settings** | 22 Tenant Management · 23 Subscription & Billing · 24 User & Roles Management · org profile · branding/white-label · security (SSO/MFA/sessions/IP allowlist) · integrations/webhooks/API keys · custom fields · notification preferences · data & retention · localization |
| **External Client Portal** | 21 — separate surface, no main shell (own minimal chrome); see Doc 08 |
| **Auth** | 1 Authentication & Login · 2 MFA / OTP — pre-shell |
| Cross-cutting UI primitives | 30 Mobile Responsive Experience (Doc 12) · the right drawer's Activity/Comments/Signers/Details everywhere |
| **Platform admin** (our SaaS team, separate app/surface) | tenant list, plans/feature flags, usage metering, impersonation-with-audit, system health — *not* part of the customer-facing IA |

---

## 3. Sitemap & URL structure

Tenant is resolved from **subdomain** (`acme.app.example.com`) and/or the JWT; URLs below are within a tenant. Pattern: nouns plural, IDs as slugs/UUIDs, sub-resources nested, actions as `?` modes or trailing segments where it's a distinct screen.

```
/                                   → redirect to /dashboard (or onboarding if new tenant)
/login   /login/mfa   /login/sso/callback   /forgot   /reset/:token
/accept-invite/:token               → set password / SSO link
/onboarding                         → first-run wizard (workspace setup)

/dashboard

/contracts                          → list (DataTable; ?view=, ?stage=, ?owner=, ?q=, ?page=)
/contracts/new                      → creation wizard (?from=template:<id> | ?from=upload | ?from=blank | ?from=import)
/contracts/:id                      → detail · Overview tab
/contracts/:id/document             → the editor (draft) or the rendered/viewed document
/contracts/:id/approvals
/contracts/:id/signatures           → signer list + status
/contracts/:id/prepare-signature    → signature *placement* UI (drag fields onto doc)
/contracts/:id/insights             → AI analysis (summary, clauses, risks, obligations) — intelligence surface
/contracts/:id/files                → attachments, versions, exports, certificate
/contracts/:id/activity             → full activity log for this contract
/contracts/:id/access               → who can/did access (transparency)
/contracts/:id/versions/:vid        → a specific version (read-only or "restore")
/contracts/:id/renew                → renewal wizard
/sign/:token                        → external signer entry (no shell) → /sign/:token/ceremony → /sign/:token/done

/workflows                          → list of workflow definitions
/workflows/new   /workflows/:id     → the visual builder
/workflows/:id/runs                 → run history (which contracts, where they are, bottlenecks)
/workflows/:id/runs/:runId

/templates                          → list
/templates/new   /templates/:id     → template editor (same BlockEditor, "template mode")
/clauses                            → clause library (inline-database view)
/clauses/:id                        → clause detail (variants, language pairs, usage, approval status)

/intelligence                       → OCR/AI home: upload zone + recent jobs + extraction queue
/intelligence/upload                → OCR upload experience
/intelligence/jobs/:jobId           → OCR processing screen (live) → on done →
/intelligence/jobs/:jobId/review    → OCR extracted-data review (side-by-side)
/intelligence/assistant             → full AI Assistant workspace (also available as the drawer tab)

/reports                            → analytics home (KPI overview)
/reports/contracts   /reports/cycle-time   /reports/risk   /reports/renewals   /reports/workflow   /reports/usage
/reports/builder/:id                → saved custom report
(scheduled reports configured under settings or here)

/audit                              → audit log (filters, export)
/audit/export/:id                   → an evidence-package export job/result

/inbox                              → notifications + my approvals + my signatures (tabs)
/inbox/notifications   /inbox/approvals   /inbox/signatures

/search                             → advanced/smart search results (full-page; ⌘K is the quick version)

/settings                           → redirect to /settings/organization
/settings/organization              → name, logo, locale, contact, legal entity
/settings/branding                  → white-label: colors, logo, email branding, signing-page brand
/settings/users                     → user list, invites, deactivate
/settings/roles                     → role definitions + permission matrix editor
/settings/teams                     → teams/departments
/settings/security                  → SSO (SAML/OIDC), MFA policy, password policy, session/IP allowlist, device list
/settings/integrations              → connected apps (Slack/Teams, Drive/SharePoint, HRIS/ERP), API keys, webhooks
/settings/custom-fields             → define contract custom fields/metadata schema
/settings/notifications             → org + personal notification preferences
/settings/billing                   → plan, usage, invoices, payment method, seats
/settings/data                      → retention policies, export all data, data residency, delete workspace
/settings/localization              → default language, date/number format, Hijri toggle, RTL preview
/settings/audit-retention           → audit log retention & export schedule
/account                            → personal: profile, password, MFA, sessions, language, theme, notification prefs

/help   /help/:articleSlug          → in-app help (or links to docs)
/dev    /dev/api   /dev/webhooks    → API docs / playground / webhook logs (if exposed in-app)
```

**URL conventions:** plural nouns, kebab-case segments, UUIDs (or short slugs) for IDs, list filters in query params (shareable/bookmarkable), wizards are real routes (so back/forward and deep links work), modal states use `?modal=` or a route segment for ones worth deep-linking. RTL doesn't change URLs.

---

## 4. Page archetypes (every screen is one of these)

| Archetype | Layout | Examples |
|---|---|---|
| **List/Index** | FilterBar + DataTable + bulk bar + empty state; sidebar = saved views | Contracts, Templates, Clauses, Workflows, Users, Audit |
| **Detail** | PageHeader (title + LifecycleBar + actions) + tabs + body; right drawer active | Contract detail, Workflow detail, Clause detail |
| **Wizard** | Stepper (top or side) + step body + sticky footer (Back/Save draft/Continue) | Create contract, Onboarding, Renewal, Workflow-from-scratch |
| **Editor/Canvas** | Full-bleed editing surface + minimal floating toolbars + right drawer | Contract editor, Template editor, Workflow builder, Signature placement |
| **Dashboard/Analytics** | KPI cards + chart grid + feed/recommendation cards; responsive grid | Home dashboard, Reports pages |
| **Viewer** | DocViewer center + side panels (fields/comments/insights) | Document viewing, signing ceremony, OCR review |
| **Settings** | Settings sidebar + form sections (cards) + save bar | All of `/settings/*`, `/account` |
| **Auth/Standalone** | Centered card on brand gradient, no shell | Login, MFA, invite accept, external signer portal |

This keeps the app learnable: once you know the 8 archetypes, every new screen is familiar.

---

## 5. Permissions surface (which roles see what — full RBAC in Doc 19)

| Role (default set; customizable per tenant) | Sees / can |
|---|---|
| **Owner** | everything incl. billing, delete workspace, transfer ownership |
| **Admin** | everything except billing-ownership; manage users/roles/security/integrations |
| **Manager** (dept/team lead) | full contracts within their team(s) + workflows + templates + team reports; approve where assigned |
| **Author/Editor** | create/edit own & shared contracts, use templates/clauses, run OCR, send for approval/signature |
| **Approver** | view contracts routed to them; approve/reject/comment; their inbox |
| **Reviewer/Commenter** | view + comment on shared contracts; no edit, no send |
| **Viewer** | read-only on shared contracts/reports |
| **Auditor** | read-only across all contracts + full audit log + exports; no edit |
| **External (signer/collaborator)** | only the specific contract(s) shared with them, only via the portal/links; scoped to view/comment/sign per the share grant |
| **Billing admin** | billing/plan/invoices only |
| **API/Service account** | scoped tokens, no UI |

Visibility is the *intersection* of (role permissions) ∩ (resource ACL: owner, team, explicitly shared, public-in-org) ∩ (tenant feature flags/plan). The nav rail hides areas the role can't use; lists show only resources the user can see; sensitive actions (export audit, change roles, delete, disable MFA) require step-up auth and emit high-visibility audit entries.

---

## 6. Search & findability layers

1. **⌘K command palette** — instant fuzzy across contracts, templates, clauses, people, settings, + run actions. The everyday tool.
2. **In-context search** — every list has a search box scoped to that list (server-side, debounced).
3. **`/search` advanced** — full-page: query + structured filters (party, type, value range, dates, tags, custom fields, clause-contains, risk level) + sort; results grouped by type; saveable as a view.
4. **Semantic / AI search** ("find contracts with an unusual indemnification cap", "leases expiring this year over $50k") — natural-language → the AI layer parses to filters + does embedding similarity over clauses/contracts (`pgvector`); results show *why* each matched (matched clause snippet, confidence). Lives in `/search` and the AI Assistant.
5. **Search-in-document** — inside the DocViewer/editor, find within the current contract.

---

## 7. Onboarding IA (first run)

`/onboarding` wizard for a brand-new tenant: ① workspace name + logo + locale (EN/AR, timezone, date format, Hijri toggle) → ② invite teammates (emails + role) → ③ pick a starter template pack (NDA / MSA / Lease / Employment / Vendor — bilingual versions) and seed the clause library → ④ choose a default approval workflow (or "I'll build later") → ⑤ "try it" — guided creation of a first contract or a sample OCR upload → land on the dashboard with a checklist card ("Complete your setup: 3 of 6"). Skippable; resumable; per-user product tour overlay on first dashboard visit.
