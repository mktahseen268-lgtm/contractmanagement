# 08 — Modules, Part 3: Admin & Trust

Covered here: **18 Audit Logs · 19 Reports & Analytics · 20 Notification Center · 21 External Client Portal · 22 Tenant Management · 23 Subscription & Billing · 24 User & Roles Management · 25 Activity Timeline · Settings hub** (and a note on the **Platform Admin** surface, which is internal-only).

---

## Module 18 — Audit Logs

**Purpose:** an immutable, tamper-evident, exportable record of *everything* — for compliance, disputes, and security investigations. The product's trust spine made visible.

**Layout** (`/audit` — List archetype, read-only):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Audit log                            [Export ▾ (CSV / signed evidence package)]    │
│ ┌ FilterBar: [Search] Actor▾ Action▾ Object type▾ Object▾ Date range  Severity▾  IP▾│
│ │ 1,204,883 entries · showing 1–50 · [show only sensitive actions ☐]               │
│ ├──────────────────────────────────────────────────────────────────────────────────┤│
│ │ Time (UTC)         Actor        Action               Object            IP/Device  ⋮│
│ │ 2026-05-12 14:02:11 J.Doe        contract.submitted   MSA — Acme #0481  10.x · Win  │
│ │   ▾ before→after: status draft→in_review · workflow=Procurement std · 🔗hash …a1f  │
│ │ 2026-05-12 13:58:40 A.Khan(ext)  contract.viewed      MSA — Acme #0481  93.x · iOS  │
│ │ 2026-05-12 11:20:03 Admin S.     role.changed         user M.Khan       10.x · Mac ⚠│  ← sensitive
│ │   ▾ before→after: role Author→Manager · 🔗hash …b7c · ⚠ step-up auth confirmed     │
│ │ 2026-05-12 09:11:55 system       ai.analysis.completed MSA — Acme #0481  —    · job  │
│ │ ...                                                                               │
│ └──────────────────────────────────────────────────────────────────────────────────┘│
│  Each entry: 🔗 hash (chained to the previous entry) · [verify chain ▸] proves no    │
│  insertions/deletions. Entries are append-only — never edited, never deleted by app. │
│  Retention: {N} years (per /settings/audit-retention); auto-archive to cold storage. │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**What's logged:** auth events (login, logout, MFA, SSO, failed attempts, password changes, session revocations, step-up auth), contract lifecycle (created, edited (with version refs), submitted, approved/rejected/changes-requested, prepared, sent, viewed, signed, declined, voided, activated, renewed, terminated, archived, deleted), workflow events, signature ceremony events (each recipient action with IP/device/geo/hash), sharing (link created/used/revoked, access granted/removed), OCR/AI events (jobs, extractions, human overrides), settings changes (roles, security policy, integrations, billing, branding, retention), data events (exports, bulk imports, deletions), admin actions (user create/deactivate, impersonation, retention changes), API events (token created/used/revoked, webhook deliveries), and any "sensitive action" flag. Each entry: `id`, `tenant_id`, `timestamp`, `actor` (user / external / system / service-account), `action` (verb namespace, e.g. `contract.signed`), `object_type` + `object_id` + display label, `metadata` (before→after diff where relevant, request id, job id), `ip`, `user_agent`/device fingerprint, `geo`, `severity`, and the **hash** = `H(prev_hash + entry_canonical_json)` (a hash chain → any tampering breaks the chain; "verify chain" recomputes and confirms; periodically the head hash is anchored externally — e.g., emailed to admins / written to a separate store / optionally notarized — for stronger non-repudiation).

**Export — the "evidence package":** a signed ZIP/PDF bundle for legal/dispute use: the filtered audit entries + their hash chain + a verification statement + (if scoped to a contract) the contract versions, the signature certificate of completion, and the access log — all sealed and hash-stamped. Generated as a Celery job, appears in the `ProgressTray`, downloadable for a limited window.

**Access:** Owner/Admin/Auditor see the full log; others see only the per-contract slice (the Lifecycle Timeline, Module 15) for contracts they can access. Viewing/exporting the audit log is itself audited. No one — not even Owner — can edit or delete entries through the application; raw DB tampering breaks the hash chain and is detectable.

**States:** loading (skeleton) · normal · filtered · empty-after-filter · large (server-paged, virtualized, "jump to date") · chain-verified ✓ / chain-broken ✗ (a loud banner + "contact security" if a mismatch is ever detected) · export-in-progress / export-ready.

**Edge cases:** GDPR "right to be forgotten" vs an immutable audit log → personal identifiers can be *pseudonymized/redacted* in display (the redaction is itself logged), but the entry and chain remain; legal hold extends retention regardless of policy; very high event volume (partition by month, hot/warm/cold tiering, async export); clock integrity (entries use a trusted time source; signature events also record a timestamp-authority token).

**RTL/Mobile:** mirrors; on mobile it's a read-only feed with expandable entries and a bottom-sheet filter; export is desktop-recommended (large files).

---

## Module 19 — Reports & Analytics

**Purpose:** answer the executive/ops questions — *how much, how fast, how risky, what's coming* — with drill-downs, and let users build & schedule their own reports. (Dashboard widgets in Module 3 are the "glance"; this is the "dig in".)

**Layout** (`/reports` hub → Dashboard/Analytics archetype per report):
```
┌── sidebar ──┐┌──────────────────────── content ─────────────────────────────────┐
│ REPORTS     ││ Reports › Cycle Time          [dept: all ▾][type: all ▾][last 12mo ▾]│  ← global
│ ▸ Overview  ││ ┌ KPIs ─────────────────────────────────────────────────────────┐ │     filters
│ ▸ Contracts ││ │ Avg create→signed: 8.4d (▼1.2 vs prior) · Approval portion 4.1d │ │     cascade
│ ▸ Cycle time││ │ · Signature portion 2.3d · p90: 21d · Slowest type: MSA 14d   │ │     to all
│ ▸ Risk      ││ ├────────────────────────────────────────────────────────────────┤ │     charts
│ ▸ Renewals  ││ │ [Funnel] Draft→Review→Approved→Sent→Signed (counts + drop-off) │ │
│ ▸ Workflow  ││ │ [Bar] Avg days per stage, split by workflow / department       │ │
│ ▸ Spend     ││ │ [Heatmap] Bottlenecks: which workflow step × which week is slow │ │
│ ▸ Usage     ││ │ [Line] Cycle time trend, 12 months                             │ │
│ ▸ My reports││ │ [Table] Slowest 20 contracts right now (who's blocking, how long)│ │
│ [+ New]     ││ └────────────────────────────────────────────────────────────────┘ │
│             ││  [Export PDF/CSV] [Schedule ▾ (weekly email to …)] [Save as report] │
└─────────────┘└───────────────────────────────────────────────────────────────────┘
```

**Standard reports (each = a curated set of charts + a drill-down table):**
- **Overview** — all the dashboard KPIs, bigger, with trends and breakdowns by department/type/owner.
- **Contracts** — volume created/signed/active/expired over time; by type, department, owner, counterparty, value band; new vs renewal.
- **Cycle time** — create→signed and each sub-stage; funnel with drop-off; per-stage durations; bottleneck heatmap; slowest-now table; the brief's "approval bottlenecks".
- **Risk** — risk-level distribution; new high/critical flags over time; most-common flagged clauses; contracts with unresolved high risks; "risk by department/type"; AI-flag acceptance rate.
- **Renewals** — pipeline of upcoming expirations by bucket; auto-renew exposure; renewal rate; revenue retained vs lost; upcoming opt-out deadlines; the brief's "expiring contracts" deep view.
- **Workflow** — runs per workflow; SLA-breach rate; rejection rate; escalations; avg time per step; "which approver is the bottleneck".
- **Spend / value** — total contract value active/signed; by type/department/counterparty; payment-term distribution; upcoming obligations value.
- **Usage** (admins) — active users, contracts/OCR/AI usage vs plan limits, storage, API calls, seats — feeds billing.
- **My reports** — saved custom reports.

**Report builder** (`/reports/builder/:id`): pick a dataset (contracts / workflow runs / signature envelopes / OCR jobs / audit / obligations), choose dimensions (group by type/dept/owner/month/…), measures (count, sum value, avg cycle time, % SLA-met, …), filters, a chart type per panel, layout; save (private or shared), schedule (daily/weekly/monthly email — PDF + CSV — to recipients/teams), export anytime. Built on the analytics read-replica + pre-computed rollups so it never strains the primary DB.

**States:** loading (skeleton charts) · normal · filtered · no data ("no contracts match these filters / not enough history yet") · computing (large aggregate → "crunching 12 months…") · scheduled-report sent (confirmation) · export-ready (`ProgressTray`).

**Edge cases:** brand-new tenant (most reports say "needs more history"); huge tenants (rollups updated incrementally by a beat job; reports read rollups, not raw rows); multi-currency value reports (a base-currency conversion with a "rates as of" note); permission scoping (a Manager's reports are scoped to their teams; only Admin/Auditor see workspace-wide).

**RTL/Mobile:** mirrors; charts' axes/legends flip, numbers stay LTR; on mobile, reports are vertical card stacks with simplified charts and tappable drill-downs; scheduling/building is desktop-recommended. See Doc 12.

---

## Module 20 — Notification Center

**Purpose:** one place for everything that wants the user's attention — and granular control over the noise. Also the home of "My Approvals" / "My Signatures" (the action inbox).

**Layout** (`/inbox` — tabs; plus the top-bar bell with a dropdown preview):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Inbox   [ Notifications ] [ My Approvals (3) ] [ My Signatures (1) ]    [Mark all read]│
│ ── NOTIFICATIONS ──────────────────────────────────────────────────────────────────│
│ │ ● Today                                                                          ││
│ │   🔵 A.Smith requested your approval on "Renewal — Northstar"   2m   [Review]    ││
│ │   🟣 "Vendor NDA — Globex" is ready for your signature          1h   [Sign]      ││
│ │   🟠 "Lease — Tower 7" expires in 14 days                       3h   [Renew]     ││
│ │   ⚪ M.Khan mentioned you in a comment on §9 of "MSA — Acme"     5h   [Open]      ││
│ │   🔵 OCR finished: 12 docs from "Procurement Q2" — 4 need review 6h  [Review]    ││
│ │ ● Earlier this week  …                                                           ││
│ │  filters: [all ▾] [unread] [approvals] [signatures] [mentions] [renewals] [AI]   ││
│ └──────────────────────────────────────────────────────────────────────────────────┘│
│  ── MY APPROVALS tab: a focused queue — each card shows the contract, the AI summary,│
│     risk flags, who else is on the chain, time waiting, and [Approve][Request changes]│
│     [Reject] inline (no need to open the contract, though "open" is one click).      │
│  ── MY SIGNATURES tab: contracts awaiting your signature — [Sign] launches the       │
│     ceremony; shows due date and sender.                                            │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Channels:** in-app (the center + the bell badge + transient toasts for live events), **email** (digestible — single-action emails with a deep "Review/Sign" button that survives auth, plus optional daily/weekly digests), **push** (web push + mobile push for approvals, signatures, mentions, urgent expirations), and optional **Slack/Teams** (a connected channel gets approval/signature/expiry cards with action buttons). Each notification type is independently toggleable per channel, per user (`/account` and `/settings/notifications`), with org-level defaults and "required" types an admin can lock on (e.g., "approval requests must email").

**Notification types:** approval requested / approval reminder / escalated to you · signature requested / signature reminder / fully executed · comment / mention / reply · contract: shared with you / status changed / changes requested back to you · expiry: 90/60/30/7-day warnings / opt-out deadline / auto-renew confirmation · OCR job done / failed / has items to review · AI: high/critical risk found / recommendation · workflow: SLA breach you should know about · admin: new user joined / role changed / security alert (new device, password change) / billing (trial ending, payment failed, limit reached) · system: maintenance, new feature.

**States:** unread badge count (per tab) · read/unread toggle · grouped by day · filtered · empty ("you're all caught up ✨") · "snooze" a notification (resurface later) · "mute this contract/thread" · real-time arrival (a toast for live ones, the badge updates without refresh) · digest preview ("here's what your weekly digest will look like").

**Edge cases:** notification storms (a bulk import generates 200 OCR-done events → collapse into one "200 documents processed — review" item); a user on PTO ("delegate my approvals to X until {date}" — reroutes + notifies the delegate, audited); email deliverability (bounces tracked, fall back to in-app, warn the user); a notification whose object the user lost access to (it gracefully says "no longer available").

**RTL/Mobile:** mirrors; toasts to bottom-left in RTL; on mobile, the bell is in the top bar, "Inbox" is a bottom-nav tab, approvals/signatures are swipe-actionable (swipe to approve/sign with a confirm), push notifications deep-link straight to the action. See Doc 12.

---

## Module 21 — External Client Portal

**Purpose:** let counterparties (vendors, clients, partners) review, comment on, and sign contracts — **without needing an account** — in a branded, trustworthy, mobile-perfect, accessible surface. Borrows extra polish from Direction C (Doc 02). Flow diagram: Doc 05 §7.

**Layout** (`/sign/:token`, `/portal/:token` — standalone, no main shell, the tenant's branding):
```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  [Acme's-counterparty sees → {Org}'s logo & colors]            🔒 Secure · {Org}     │
│  ─────────────────────────────────────────────────────────────────────────────────  │
│  "Hello — {Org} has shared an agreement with you to review and sign."                │
│  Master Services Agreement   ·   sent by J.Doe ({Org})   ·   due Fri, May 16          │
│  ┌ what you need to do ─────────────────────────────────────────────────────────────┐│
│  │  ① Verify your email/phone (a code was sent to a••@acme.com)   [enter code]      ││
│  │  ② Review the document                                                          ││
│  │  ③ Sign (3 fields)                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────────┘│
│  ┌ DOCUMENT (large, paper-like; download a watermarked copy; comment if allowed) ───┐│
│  │  … the contract …  [page 1/12 ‹ ›]  [↓ download draft copy]  [💬 add a comment]  ││
│  └──────────────────────────────────────────────────────────────────────────────────┘│
│  ☑ I agree to use electronic records and signatures  [disclosure ▾]                  │
│  [ Decline ▾ ]   [ Ask a question ▾ ]                              [ Review & sign ▸]│
│  ───────────────────────────────────────────────────────────────────────────────────│
│  After signing: "✓ Done. You'll receive the fully-executed copy by email."  [VerifiedSeal]│
│  Optional: "Want to manage all your agreements with {Org}? [Create a free account]"  │
│  Footer: {Org} contact · powered by {Platform} · privacy · this link expires {date}  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Capabilities for the external user:** open via secure link (expiring, revocable, optionally passcode-protected); light identity verification (email/SMS OTP, or ID-verification for high-assurance contracts); read the document (DocViewer, page nav, search, download a watermarked draft copy); **comment / ask questions** (if the sender enabled collaboration — threaded, the sender is notified; otherwise just "contact sender"); **sign** (the full ceremony, Module 14 — adopt signature, fill fields, consent, finish — records IP/device/geo/timestamp/hash); **decline** (with a reason); after execution, receive an email with a link to download the **signed copy + certificate of completion** (that link also self-expires); optionally **create a free account** to see all agreements with this org (the "magic" upsell).

**What the external user does NOT see:** the main app, other contracts, internal comments, the audit log, anything outside the specific contract(s) shared with them, any other tenant's data. Their access is a narrow, time-boxed grant scoped to view/comment/sign per the share settings; every action they take is in the tenant's audit log.

**States:** valid link (the above) · expired/revoked link ("this link is no longer active — contact {sender}" + a "request a new link" button that emails the sender) · needs-OTP · OTP-failed (retry/lockout) · ready · partially-signed (revisiting shows their progress) · already-signed-by-them (shows their signed state + "download what you signed") · declined · fully-executed (download the final copy) · accessibility mode (full keyboard, screen-reader narration, high contrast — counterparties may have any assistive tech) · branded vs. unbranded (default platform branding if the tenant hasn't set up white-label).

**Edge cases:** the counterparty forwards the link to a colleague (the link is per-recipient; the colleague can't act — "this link was sent to {name} — ask {sender} to add you"); a counterparty who is also a customer of ours under a different tenant (kept entirely separate); a counterparty in a different language (the portal offers EN/AR and renders the contract in its own language); bulk-send (each counterparty gets their own envelope/link); a counterparty who needs to attach a document (an attachment-request field in the ceremony).

**RTL/Mobile:** the portal is RTL when the counterparty picks Arabic (or the contract is Arabic); **mobile is the primary design target** for the portal (a lot of counterparties open the link on a phone) — one-handed, big "Review & sign", bottom-anchored actions, OS keyboard for typed signature, touch for drawn, OTP autofill. See Doc 12. The branded, polished completion screen with the VerifiedSeal is the brand-halo moment.

---

## Module 22 — Tenant Management

**Purpose:** the workspace owner/admin's control over the *organization* — identity, branding, security posture, structure, data. (Not to be confused with the internal Platform Admin, below.)

**Layout** (`/settings/*` — Settings archetype: settings sidebar + form-section cards + a save bar):
```
┌── settings nav ─┐┌────────────────────── content ──────────────────────────────────┐
│ ORGANIZATION    ││ Settings › Organization                                          │
│ ▸ Profile       ││ ┌ Workspace profile ──────────────────────────────────────────┐ │
│ ▸ Branding      ││ │ Name [Acme Holdings____]  Subdomain [acme].app.example.com    │ │
│ ▸ Teams         ││ │ Logo [⬆ upload]  Primary color [#…]  Legal entity name […]   │ │
│ ── PEOPLE ──    ││ │ Default language [English ▾ / العربية]  Timezone […]  Hijri ☐ │ │
│ ▸ Users         ││ │ Date format […]  Number format […]  Default currency [USD ▾] │ │
│ ▸ Roles         ││ │ Industry [Logistics ▾]  Address […]  Primary contact […]     │ │
│ ── SECURITY ──  ││ └──────────────────────────────────────────────────────────────┘ │
│ ▸ Authentication││ ┌ Legal entities ─────────────────────────────────────────────┐ │
│ ▸ Sessions/Dev. ││ │ (companies you sign as): Acme Holdings LLC · Acme Logistics  │ │
│ ▸ IP allowlist  ││ │ FZE · … [+ add] — used as "the {us} party" on contracts      │ │
│ ── PLATFORM ──  ││ └──────────────────────────────────────────────────────────────┘ │
│ ▸ Integrations  ││           [ Discard changes ]                      [ Save ]      │
│ ▸ API & webhooks││                                                                  │
│ ▸ Custom fields ││                                                                  │
│ ── DATA ──      ││                                                                  │
│ ▸ Retention     ││                                                                  │
│ ▸ Export / del. ││                                                                  │
│ ▸ Data residency││                                                                  │
│ ── BILLING ──   ││                                                                  │
│ ▸ Plan & usage  ││                                                                  │
│ ▸ Invoices      ││                                                                  │
└─────────────────┘└───────────────────────────────────────────────────────────────────┘
```

**Sections:** **Organization profile** (name, subdomain, logo, locale defaults, timezone, Hijri toggle, date/number/currency formats, industry, address, contacts) · **Legal entities** (the companies you sign *as* — picked as "the {us} party" on contracts) · **Branding / white-label** (logo, colors, email branding, the signing/portal page brand, custom domain, "remove platform branding" on a plan that allows it) · **Teams** (departments — used for routing, permissions, reporting; a tree) · **Security — Authentication** (SSO: SAML/OIDC config + JIT provisioning + domain claiming; MFA policy: required / optional / required-for-admins, allowed factors; password policy; SCIM provisioning token) · **Security — Sessions & devices** (max session length, idle timeout, "sign out all sessions", a list of active sessions/devices org-wide, trusted-device policy) · **Security — IP allowlist** (restrict access to ranges; with a "don't lock yourself out" guard) · **Integrations** (Slack/Teams, Google Drive/SharePoint, HRIS/ERP connectors, e-sign legal-vendor add-ons) · **API & webhooks** (API keys with scopes, webhook endpoints + secrets + delivery logs + replay) · **Custom fields** (define the contract metadata schema: field name, type, options, which contract types use it, required) · **Data — Retention** (per-data-type retention periods, legal-hold management) · **Data — Export/Delete** (export all workspace data; delete the workspace, with a cooling-off period + confirmation + final export) · **Data — Residency** (which region S3 + DB live in, for tenants on a plan that allows it) · **Localization** (default language, RTL preview, available languages, Hijri calendar, translation overrides) · **Notifications** (org defaults + locked-on types) · **Billing** (→ Module 23) · **Audit retention** (→ feeds Module 18).

**States:** clean / dirty (the save bar appears) · saving / saved / save-failed · permission-gated (only Owner/Admin; some sections — billing-ownership, delete-workspace, SSO — Owner-only and may require step-up auth) · validation (e.g., subdomain taken, SSO metadata invalid, IP allowlist would lock out the current admin → blocked with a warning) · destructive confirmations (delete workspace → type the name, acknowledge consequences, cooling-off period, final data export offered).

**Edge cases:** changing the subdomain (old one redirects for a grace period; existing links updated); enabling SSO mid-life (existing users link their accounts; an "SSO-only" toggle that disables passwords once everyone's linked); domain claiming (verify a DNS record → all users with that email domain auto-join with a default role); turning on IP allowlist while the admin is on an off-list IP (require adding their current IP first); white-label on a downgrade (reverts to platform branding).

**RTL/Mobile:** settings mirror; mostly desktop-class admin work, but key toggles (MFA policy, sign-out-all, view sessions) are mobile-usable; the RTL preview is itself a feature here.

---

## Module 23 — Subscription & Billing

**Purpose:** plans, usage, seats, invoices, payment — Stripe-Dashboard-clean, no surprises.

**Layout** (`/settings/billing` — Settings archetype):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Settings › Billing                                                                 │
│ ┌ Current plan ───────────────────────────────────────────────────────────────────┐│
│ │ Business · $X/mo · billed annually · renews 2027-01-01      [Change plan][Cancel]││
│ │ Includes: 50 seats · unlimited contracts · 5,000 OCR pages/mo · AI analysis ·    ││
│ │ SSO · API · 3 workspaces ·  white-label                                          ││
│ ├ Usage this period (resets in 18 days) ──────────────────────────────────────────┤│
│ │ Seats        ▓▓▓▓▓▓▓░░  37 / 50          [manage users]                          ││
│ │ OCR pages    ▓▓▓▓▓▓▓▓▓░ 4,210 / 5,000    ⚠ approaching limit — [add a pack]      ││
│ │ AI requests  ▓▓▓░░░░░░  1,120 / 10,000                                           ││
│ │ Storage      ▓▓░░░░░░░  84 GB / 1 TB                                             ││
│ │ API calls    ▓▓▓▓░░░░░  220k / 1M                                                ││
│ ├ Payment method ─────────────────────────────────────────────────────────────────┤│
│ │ Visa ···· 4242  exp 09/27   [update]   ·   Billing email [ar@acme.com] [edit]    ││
│ │ Billing address / tax ID / VAT […]  [edit]                                       ││
│ ├ Invoices ───────────────────────────────────────────────────────────────────────┤│
│ │ 2026-01-01  $X  Paid  [PDF]    2025-01-01  $X  Paid  [PDF]   …                   ││
│ └──────────────────────────────────────────────────────────────────────────────────┘│
│  Banners as needed: "Trial ends in 5 days — add a payment method" · "Payment failed —│
│  update your card by {date} to avoid interruption" · "You're over the OCR limit —    │
│  pages now queue / billed at $X each — upgrade?"                                      │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Concepts:** **Plans** (e.g., Starter / Business / Enterprise — differ on seats, OCR pages/mo, AI requests/mo, storage, API limits, workspaces, white-label, SSO/SCIM, advanced analytics, real-time collaboration, support tier; Enterprise is custom-quoted) · **Seats** (active users; adding a user beyond the seat count prompts an upgrade or per-seat add) · **Usage meters** (OCR pages, AI requests/tokens, storage, API calls — metered server-side, shown live, with "approaching limit" and "over limit" behaviors: queue / soft-cap / overage billing / upgrade prompt — configurable per plan) · **Trial** (time-boxed, full features or limited, banner countdown, smooth conversion) · **Add-on packs** (extra OCR pages, extra AI, extra storage) · **Payment** (card / invoice billing for enterprise / regional methods; tax/VAT handling; billing email & address; dunning on failure) · **Invoices** (history, downloadable PDFs, line items) · **Plan changes** (upgrade = immediate + proration; downgrade = at period end, with warnings if usage exceeds the new plan; cancel = access until period end + data export reminder). Built on a billing provider (Stripe Billing or similar) with our usage-metering feeding it; the **Platform Admin** can override/comp/extend for specific tenants.

**States:** trialing / active / past-due (grace period, dunning) / canceled (period-end access) / paused · within limits / approaching limit / over limit · plan-change-pending · payment-method-missing / -valid / -failed · invoice-paid / -open / -overdue.

**Access:** Owner + a dedicated Billing Admin role; viewing usage is broader (Admins); changing the plan / payment method may require step-up auth; all billing actions audited.

**Edge cases:** downgrading below current usage (block until they reduce, or allow with a warning + grace); a failed payment on a workspace with active contracts in flight (never lose data; restrict new actions, keep read access, dunning emails, then suspend after grace); regional tax/currency; multiple workspaces under one billing account (consolidated invoice or per-workspace); enterprise contracts with custom terms (the Platform Admin sets a custom plan; the UI shows "Enterprise — managed by your account team").

**RTL/Mobile:** mirrors; numbers/currency stay LTR; mobile shows plan + usage + invoices read-only and "update payment" works; plan changes are desktop-recommended.

---

## Module 24 — User & Roles Management

**Purpose:** who's in the workspace, what they can do, and how that's defined. The RBAC matrix made editable. (Role list & permission model: Doc 04 §5 and Doc 19.)

**Layout** (`/settings/users` and `/settings/roles` — List + a matrix editor):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Settings › Users                            [Invite people ▾]  [Export CSV]         │
│ ┌ FilterBar: [Search] Role▾ Team▾ Status▾  ·  37 users (3 pending, 1 deactivated)   │
│ ├──────────────────────────────────────────────────────────────────────────────────┤│
│ │ Name           Email              Role       Teams        Status   Last active  ⋮ ││
│ │ J.Doe          j@acme.com         Manager    Procurement  Active    2m ago      ⋮ ││
│ │ A.Smith        a@acme.com         Author     Procurement  Active    1h ago      ⋮ ││
│ │ legal@acme.com legal@acme.com     Reviewer   Legal        Pending   invited 2d  ⋮ ││
│ │ ex@old.com     ex@old.com         —          —            Deactiv.  —           ⋮ ││
│ │  row ⋮ : change role · change teams · deactivate/reactivate · resend invite ·     ││
│ │          force password reset · sign out all sessions · view audit · delegate     ││
│ └──────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                    │
│ Settings › Roles                                          [+ New role]              │
│ ┌ Permission matrix (rows = permission, cols = roles; ✓ / partial / —) ────────────┐│
│ │ Permission                     Owner Admin Mgr Author Apprvr Rev Viewer Auditor   ││
│ │ contracts.view                  ✓     ✓    team own  routed shrd shrd   all       ││
│ │ contracts.create                ✓     ✓    ✓   ✓      —     —    —      —          ││
│ │ contracts.edit                  ✓     ✓    team own   —     —    —      —          ││
│ │ contracts.submit                ✓     ✓    ✓   ✓      —     —    —      —          ││
│ │ contracts.approve               ✓     ✓   assigned   assigned —   —      —         ││
│ │ contracts.send_for_signature    ✓     ✓    ✓   ✓      —     —    —      —          ││
│ │ contracts.delete                ✓     ✓    —    —     —     —    —      —          ││
│ │ templates.manage                ✓     ✓    ✓    —     —     —    —      —          ││
│ │ workflows.manage                ✓     ✓    ✓    —     —     —    —      —          ││
│ │ users.manage                    ✓     ✓    —    —     —     —    —      —          ││
│ │ settings.security               ✓     ✓    —    —     —     —    —      —          ││
│ │ billing.manage                  ✓     —    —    —     —     —    —      —          ││
│ │ audit.view_all / export         ✓     ✓    —    —     —     —    —      ✓          ││
│ │ ai.use                          ✓     ✓    ✓   ✓      ✓     ✓    —      —          ││
│ │ … (full matrix in Doc 19) … cells editable for custom roles; system roles locked  ││
│ └──────────────────────────────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Capabilities:** invite users (by email, with a role + teams; bulk-invite via CSV; SCIM/JIT auto-provision from the IdP); manage a user (change role/teams, deactivate (revokes all access, keeps their history & attributions), reactivate, resend invite, force password reset, force MFA enrollment, sign out all their sessions, view their audit trail, set a delegate (their approvals reroute while away)); **roles** (a set of system roles — Owner, Admin, Manager, Author, Approver, Reviewer, Viewer, Auditor, Billing Admin — plus custom roles a tenant defines by toggling permissions in the matrix); the **permission matrix** (every permission × every role; system roles are locked, custom roles are editable; permissions are also *scoped* — "team" = within the user's teams, "own" = resources they own, "routed/assigned" = where they're in the workflow, "shared" = explicitly shared with them, "all" = workspace-wide); transfer ownership (Owner only, step-up auth, the old owner becomes Admin).

**States:** active / invited (pending) / deactivated · seat-limit (inviting beyond the plan prompts upgrade) · SSO-managed users (role/teams may be pushed from the IdP via SCIM — those fields show "managed by SSO" and are read-only here) · self-edit guard (you can't remove your own last admin permission or deactivate yourself if you're the sole Owner) · custom-role-in-use (can't delete a role that users have — reassign them first).

**Edge cases:** the "last Owner" problem (always require ≥1 active Owner; transferring is the only way out); a deactivated user who owned active contracts (ownership must be reassigned — prompt on deactivation); SSO group → role mapping (configure which IdP group maps to which role); a contractor with time-boxed access (set an expiry on the membership); external users (managed separately, via share grants, not here — but listed read-only under a "guests" filter so admins can see/revoke).

**RTL/Mobile:** mirrors; the matrix is wide → on mobile it becomes a per-role view (pick a role → see its permissions as a list) or is desktop-recommended; inviting/deactivating works on mobile.

---

## Module 25 — Activity Timeline

This is the **right-drawer "Activity" tab** that appears on virtually every object (contracts, workflows, templates, clauses, even settings) plus the per-contract **Lifecycle Timeline** (Module 15) and the workspace-wide **Team Activity** widget (Module 3). It's one component (`ActivityFeed`) reused at three scopes: object-level (this contract's events), area-level (recent activity in Workflows / Templates), workspace-level (the dashboard feed). Each entry: actor avatar + action + object + timestamp (grouped by day / "x ago") + expandable detail (diff, comment thread, access record); filterable by event type; the workspace-level feed is filterable by team/person/type and is the social pulse of the workspace ("see what changed while I was away"). It reads from the activity stream (a denormalized, fast-to-query projection of relevant domain events + the audit log), not the raw audit table, so it's snappy. Read-only — actions live on the relevant object. RTL mirrors; on mobile it's a clean vertical feed (the drawer becomes a bottom-sheet). Audit-grade entries carry the hash chip and link to the full audit log (Module 18) for those with permission.

---

## (Internal) Platform Admin surface

**Not a customer module — for our SaaS operations team only**, on a separate subdomain/app with its own auth (and ideally separate infrastructure boundaries). It provides: a **tenant list** (search, status, plan, usage, created, owner, region) → tenant detail (override plan/limits/feature flags, extend trial, comp credits, view (not edit) their audit log, see health/usage, suspend/restore, **impersonate** a tenant admin — heavily audited, time-boxed, with a banner on the impersonated session and a notification to the tenant); **feature flags** (global + per-tenant rollout of new features); **usage & billing operations** (metering dashboards, dunning status, manual invoice adjustments); **system health** (queue depths, job success rates, OCR/AI throughput & cost, error rates, SLO dashboards, incident tooling); **content** (manage the default starter template/clause packs shipped to new tenants, manage in-app help articles, manage the AI prompt library/model config); **support tooling** (look up a user/contract by id for a support ticket — read-only, audited); **deployment/ops** (kept in infra tooling, but linked here). Everything in this surface is audited to a separate, equally immutable log; access requires our internal SSO + MFA + step-up for destructive/impersonation actions. This is mentioned here for completeness of the IA — its detailed design is an internal-tools effort, lower priority than the customer product.
