# 06 — Modules, Part 1: Core

Page-by-page design + UX spec. Each module: **purpose · layout (ASCII wireframe) · key components · states · interactions · edge cases · RTL & mobile notes**. Modules covered here: **1 Auth · 2 MFA/OTP · 3 Dashboard · 4 Contract Listing · 5 Contract Details · 6 Creation Wizard · 7 Editor (→ Doc 11) · 16 Templates · 17 Clause Library**.

---

## Module 1 — Authentication & Login

**Purpose:** get the right human into the right workspace, securely, in seconds, in their language.

**Layout** (Auth archetype — centered card on brand gradient, no shell):
```
┌───────────────────────────────────────────────────────────┐
│  ▓▓▓ brand gradient backdrop (subtle, indigo→violet) ▓▓▓   │
│                                                           │
│        [logo]                          [ EN | ع ]  [◑]    │
│        ┌───────────────────────────────────────┐          │
│        │  Welcome back                          │          │
│        │  Sign in to {Workspace}                │          │
│        │                                        │          │
│        │  Email      [______________________]   │          │
│        │  Password   [______________] [👁]      │          │
│        │             ☐ Remember this device     │          │
│        │             [    Sign in    ]          │          │
│        │             ── or ──                   │          │
│        │             [  Continue with SSO  ]    │          │
│        │             [  Continue with Google ]  │          │
│        │  Forgot password?            New here? │          │
│        └───────────────────────────────────────┘          │
│        🔒 Protected by MFA · SOC 2 (badge row)            │
└───────────────────────────────────────────────────────────┘
```

**Key components:** logo, language switcher, theme toggle, `Input` (email — autocomplete `username`), `Input` (password — autocomplete `current-password`, reveal toggle), "remember device" checkbox, primary `Button`, SSO/social buttons (auto-shown if the email's domain maps to a configured IdP — "we'll redirect you to your company login"), inline error banner, trust-badge strip, links to forgot/signup, footer (terms, privacy, status page, language).

**States:** idle · loading (button spinner, inputs locked) · invalid credentials (inline, generic message, no user enumeration) · rate-limited (after N tries: cool-down message + optional captcha) · account locked / disabled (contact admin) · SSO-only domain (hide password, force SSO) · email-not-verified (resend link) · expired session redirect (banner: "you were signed out for security").

**Interactions:** Enter submits; on email blur, if domain is SSO-mapped → swap form to SSO CTA; "Continue with SSO" → IdP → `/login/sso/callback` → if no MFA-at-IdP and org requires app-MFA, continue to Module 2; success → `/onboarding` (new owner) or `/dashboard` (or the `?next=` deep link).

**Edge cases:** multiple workspaces for one email → after auth, a workspace chooser; invite link to a workspace they're not in yet → accept-invite flow; password reset token reuse → invalidate; brute force → progressive delays + lockout + alert email.

**RTL:** card mirrors (labels start-aligned RTL), language toggle and theme stay top corner (logical), gradient unaffected. **Mobile:** full-width card, large touch targets, OS password-manager friendly, "Continue with SSO/Google" prominent.

---

## Module 2 — MFA / OTP Verification

**Purpose:** a second factor with no friction theater — clear, fast, recoverable.

**Layout:**
```
┌───────────────────────────────────────────┐
│   [logo]                        [EN|ع][◑] │
│   ┌───────────────────────────────────┐   │
│   │  Verify it's you                  │   │
│   │  Enter the 6-digit code from your │   │
│   │  authenticator app.               │   │
│   │     [_][_][_]  [_][_][_]          │   │  ← 6 segmented inputs, auto-advance, paste-aware
│   │     ⏳ resend in 0:23  /  Resend   │   │  (only for SMS/email factors)
│   │     [      Verify      ]          │   │
│   │     ─────────────────────────     │   │
│   │     Try another way ▾              │   │  → TOTP app / SMS / email / WebAuthn key / recovery code
│   │     Lost access? Use a backup code │   │
│   │     ☐ Trust this device for 30 days│   │
│   └───────────────────────────────────┘   │
└───────────────────────────────────────────┘
```

**Key components:** 6-cell OTP input (numeric, auto-advance, backspace-aware, paste fills all, mobile shows numeric keypad + iOS SMS-autofill), countdown + resend, factor switcher menu, "trust device" checkbox (sets a long-lived, revocable device cookie so MFA isn't asked again on that device for N days — per org policy), recovery-code entry mode, WebAuthn "Use security key / passkey" button (browser prompt).

**States:** idle · verifying · wrong code (shake + clear + count remaining attempts) · expired code (auto-prompt resend) · locked after N fails (cool-down + "contact admin" + email alert) · factor unavailable (e.g., SMS not delivered → suggest alt) · enrollment mode (first-time setup: show QR + secret for TOTP, or capture phone, or register passkey, then confirm with a test code, then show & require download of recovery codes).

**Interactions:** auto-submit when 6 digits entered; resend respects a server cooldown; switching factor re-issues the appropriate challenge; success → continue to original destination; "trust device" persisted.

**Edge cases:** org *requires* MFA but user hasn't enrolled → forced enrollment before proceeding; recovery codes exhausted → admin-assisted reset path; clock skew on TOTP → accept ±1 window; SMS to a number that changed → admin reset.

**RTL:** OTP cells stay LTR (digits), labels/buttons mirror. **Mobile:** big cells, numeric keypad, autofill from SMS, "trust device" default-checked on personal devices (configurable).

---

## Module 3 — Enterprise Dashboard

**Purpose:** in one screen — *what needs me, what's at risk, how are we doing*. The "calm cockpit." This is the screen the brief specced in most detail; treat it as the product's front door.

**Layout** (Dashboard archetype):
```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Good morning, {name}   ·   {Workspace}              [+ New ▾] [Customize] [⟳]     │
│                                                                                  │
│ ── KPI ROW (cards; some carry a single donut, Dropbox-ref echo) ─────────────────│
│ ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐                     │
│ │Total   ││Pending ││Awaiting││Expiring││OCR     ││Open    │                     │
│ │contr.  ││approval││signat. ││ ≤30d   ││today   ││risks   │                     │
│ │ 1,284  ││  37  ◔ ││  12  ◑ ││  18  ◕ ││  46    ││  9 ▲   │                     │
│ │▲ 4% wk ││ 5 SLA⚠ ││ 2 stale││ 3 auto ││ 1 fail ││ 2 crit │                     │
│ └────────┘└────────┘└────────┘└────────┘└────────┘└────────┘                     │
│                                                                                  │
│ ── QUICK CREATE TILES (Dropbox-ref "Quick Access" pattern) ─────────────────────│
│ [📄 New from template] [🔍 Upload & scan (OCR)] [✎ Blank contract] [⇪ Import bulk]│
│ [✍ Request signature]                                                            │
│                                                                                  │
│ ┌──────────────── NEEDS YOUR ATTENTION ───────────┐ ┌── AI RECOMMENDATIONS ─────┐│  ← aurora-tinted
│ │ ▸ Approve · MSA Acme · waiting 2d · ▲Med [Approve]│ │ ⚡ 3 contracts auto-renew  ││     "intelligence"
│ │ ▸ Sign · Vendor NDA Globex · [Sign]              │ │   in 30d — review terms?  ││     surface
│ │ ▸ Expiring · Lease Tower 7 · 14d · [Renew]       │ │ ⚡ Risk spike: 5 new HIGH  ││
│ │ ▸ Changes requested · SLA Beta · [Edit]          │ │   clauses this week →     ││
│ │ ... (grouped, one-tap actions, "see all" → /inbox)│ │ ⚡ 12 obligations due this  ││
│ ├──────────────── CONTRACT VOLUME TREND ──────────┤ │   month [view]            ││
│ │  ▁▂▃▅▆▇▆▅  monthly created vs signed (toggle)   │ │ ⚡ Bottleneck: Legal step  ││
│ │  [by department ▾] [last 6 months ▾]            │ │   avg 4.2d (▲ from 2.1)   ││
│ └─────────────────────────────────────────────────┘ └───────────────────────────┘│
│ ┌──────────── TEAM ACTIVITY (Dropbox-ref activity rail) ──┐ ┌── WORKFLOW HEALTH ──┐│
│ │ • 2m ago — A.Smith sent "Renewal — Northstar" for sig   │ │ approvals SLA: 86% ◕ ││
│ │ • 14m — J.Doe approved "MSA — Acme" (avatar stack +3)   │ │ avg cycle time: 6.2d ││
│ │ • 1h — OCR finished: 12 docs from "Procurement Q2"      │ │ stuck >7d: 4 [view]  ││
│ │ • 3h — M.Khan added clause "GCC Data Residency v2"      │ │ rejections: 3 this wk││
│ │ ...                                                     │ └─────────────────────┘│
│ └─────────────────────────────────────────────────────────┘                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Widgets (all from the brief, mapped to components):**
- KPI cards: Total contracts · Pending approvals (+ SLA-at-risk count) · Awaiting signature (+ stale) · Expiring ≤30d (+ auto-renew count) · OCR processed today (+ failures) · Open risks (+ critical). Each: label, big tabular number, delta vs prior period, optional donut, click → filtered list.
- **Quick Create tiles** — the Dropbox "Quick Access" pattern repurposed: the 5 creation entry points, big and friendly, top of page.
- **Needs Your Attention** — merged personal queue (approvals + signatures + changes-requested + expiring you own), grouped, each row with the one obvious action; "see all" → `/inbox`.
- **AI Recommendations** — aurora-tinted intelligence card: auto-renew alerts, risk spikes, obligations due, workflow bottlenecks, "contracts missing standard clauses", "duplicate counterparty detected". Each is actionable (deep-links to a filtered list or a contract). Dismissible; "why am I seeing this" tooltip.
- **Contract Volume Trend** — created vs signed over time, filter by department/type/date range; the brief's "monthly trends" + "department statistics".
- **Team Activity** — the Dropbox activity rail: grouped by time, avatar stacks, expandable; the brief's "team activity".
- **Workflow Health** — approvals SLA %, avg cycle time, stuck >Nd, rejections this week, "approval bottlenecks" link → reports.
- **Risk Warnings / AI Alerts** — surfaced both as a KPI and inside AI Recommendations (the brief lists them separately; we co-locate for one glance).
- Optional widgets a user can add via "Customize": My drafts, Recently viewed, Calendar (expiries this month), Department leaderboard, Spend by contract type, A saved report.

**Per-role variants:** Approver → "Needs Your Attention" is dominant, analytics minimized. Exec/Dept head → analytics + risk + expiry dominant, personal queue minimized. Admin → adds a "Workspace health" strip (users, storage, plan usage, security alerts). Author → drafts + templates + activity.

**States:** loading (skeleton cards) · empty workspace (big illustrated empty state: "Create your first contract" + the Quick Create tiles + sample data offer) · partial (a widget errors → that card shows a retry, the rest render) · personalized layout (drag to reorder/resize/hide widgets, saved per user) · "as of" timestamp + refresh.

**Interactions:** every number/segment is clickable → drills to a pre-filtered list/report; date-range and department filters at the page level cascade to widgets that support them; "Customize" enters edit mode (drag handles, add-widget palette, reset to default); the right drawer (Activity / AI Assistant) is available here too.

**Edge cases:** brand-new tenant (onboarding checklist card replaces some widgets); huge tenant (widgets read from the analytics read-replica / pre-computed rollups, never block on heavy aggregates — show "computing…" then fill); timezone-correct "today" per user.

**RTL:** entire grid mirrors; charts' axes/legends flip; numbers stay LTR; activity feed reads right-to-left with avatars on the right. **Mobile:** single column, KPI cards become a horizontal scroll-snap carousel, "Needs Your Attention" is the hero, AI Recommendations and Activity below, charts simplified; see Doc 12.

---

## Module 4 — Contract Listing

**Purpose:** the operator's home for *finding, filtering, bulk-acting on* contracts. Stripe/Linear-grade table.

**Layout** (List archetype):
```
┌──── sidebar ────┐┌──────────────────────── content ──────────────────────────────┐
│ ALL CONTRACTS   ││ Contracts › All                         [⊞ List][▦ Board][▥ Cal]│
│  ▸ All          ││ ┌─ FilterBar ────────────────────────────────────────────────┐ │
│  ▸ My open      ││ │ [Search…] Stage▾ Type▾ Owner▾ Tag▾ Risk▾ Date▾ +Filter | 1,284│ │
│  ▸ Drafts       ││ │ Saved view: "My open" *modified  [Save] [Reset]            │ │
│  ▸ In review    ││ └────────────────────────────────────────────────────────────┘ │
│  ▸ Out for sig  ││ ☑ 3 selected → [Change stage▾][Assign▾][Add tag▾][Export][⋯]   │ │  ← bulk bar
│  ▸ Active       ││ ┌────────────────────────────────────────────────────────────┐ │
│  ▸ Expiring     ││ │☐ Title              Stage     Owner  Risk Value   Expiry  ⋮ │ │
│  ── FOLDERS ──  ││ │☐ MSA — Acme Corp   ●In review J.Doe  ▲Med $120k  2026-09 ⋮│ │  ← rows: hover
│  ▸ Procurement  ││ │  ◍◍◍○○○ (LifecycleBar dot-track)                            │ │     reveals quick
│  ▸ HR           ││ │☐ NDA — Globex      ●Signed   A.Sm.  —    —       —      ⋮│ │     actions; click
│  ▸ Real estate  ││ │☐ Lease — Tower 7   ●Expiring M.Khan ▲Hi  $48k   2026-06 ⋮│ │     row → detail;
│  ── TAGS ──     ││ │... virtualized, inline-edit tag/owner/expiry, sort any col  │ │     ⌘-click multi
│  #renewal #gov  ││ └────────────────────────────────────────────────────────────┘ │
│  ── TEAMS ──    ││  ‹ 1 2 3 … 26 ›   25/page▾                                       │
│  [+ New ▾]      ││                                                                 │
└─────────────────┘└─────────────────────────────────────────────────────────────────┘
```

**Views:** **List** (the default DataTable) · **Board** (Kanban columns = lifecycle stages, drag a card to advance — with rule checks; ClickUp/Monday vibe) · **Calendar** (by expiry/renewal date — the brief's expiry tracking, visualized) · optional **Timeline/Gantt** (term durations).

**Columns (configurable, reorderable, hideable, resizable):** Title (+ contract # + type icon), Stage (StatusPill), Lifecycle dot-track, Owner (avatar), Counterparty/Party, Risk (RiskBadge), Value/Amount, Start, End/Expiry (with "in Nd" relative), Workflow (which workflow + current step), Last updated, Created, Tags, Department/Team, Source (template/OCR/blank/import), Confidence (if OCR-sourced) — plus any tenant custom fields.

**FilterBar:** chip filters for every column dimension + free text search (server-side, matches title/#/party/tags/clause-contains); date-range pickers; "+ Filter" to add more; **Saved Views** (named, per-user or shared, with their own columns/filters/sort/density — the sidebar lists them); "modified" indicator when a saved view has unsaved tweaks; share-a-view (URL with all params).

**Bulk bar** (slides up on selection): Change stage, Assign owner, Add/remove tag, Move to folder, Add to workflow, Export (CSV/ZIP of PDFs), Share, Archive, Delete (with confirm + audit). Respects permissions (greyed if not allowed).

**Row interactions:** click → detail; hover → quick actions (open, edit metadata side-sheet, share, "remind approver" if applicable, ⋯ menu); ⌘/shift-click → multiselect; right-click → context menu; inline-edit safe fields; keyboard nav (↑↓ to move, Enter to open, x to select, e to edit).

**States:** loading (skeleton rows) · empty (no contracts → big empty state with Quick Create tiles + "import existing contracts" CTA + a sample) · empty-after-filter ("no contracts match — clear filters") · error (retry) · partial permissions (only visible contracts shown, with a "you may not see all results" note for non-admins) · large result set (virtualized + server pagination + "export all matching" option).

**Edge cases:** 100k+ contracts (server-side everything, virtualization, no client sort over the full set — sort is a server param); contracts shared from other teams (badge); archived contracts (separate filter, dimmed); contracts you can see but not act on (actions disabled with tooltip).

**RTL:** column order reverses, but numeric/date columns render their *content* LTR; the dot-track reverses; bulk bar slides from the bottom regardless. **Mobile:** table → card list (title, stage pill, owner, expiry, risk), tap → detail; filters in a bottom-sheet; bulk select via long-press; Board/Calendar available but list is the mobile default. See Doc 12.

---

## Module 5 — Contract Details

**Purpose:** the single source of truth for one contract — read it, see its state, see who's blocking, act on it, audit it. Everything orbits the `LifecycleBar` and the tabbed body.

**Layout** (Detail archetype):
```
┌──────────────────────────────────────────────────────────────────┬── drawer ──┐
│ Contracts › MSA — Acme Corp                    [Share][Download▾][⋯]│ [Activity] │
│ ┌─ CONTRACT HEADER ──────────────────────────────────────────────┐ │ [AI]       │
│ │ MSA — Acme Corp   #C-2026-0481   •In review                    │ │ [Signers]  │
│ │ Owner J.Doe · Counterparty Acme Corp · Type MSA · Value $120k  │ │ [Comments] │
│ │ Start 2026-01-01 · End 2026-12-31 (in 233d) · Risk ▲Medium     │ │ [Details]  │
│ │ ◍───◍───◍───○───○───○                                          │ │            │
│ │ Draft  Review  Approve  Sign  Active  Renew    [Submit ▸][Edit] │ │ ┌────────┐ │
│ ├────────────────────────────────────────────────────────────────┤ │ │•A.Smith│ │
│ │ [Overview][Document][Approvals][Signatures][AI Insights][Files] │ │ │ viewed │ │
│ │ ─────────────────────────────────────────────────────────────  │ │ │ 2h ago │ │
│ │  OVERVIEW:                                                     │ │ │•J.Doe  │ │
│ │  ┌ Key terms ──────────┐ ┌ AI summary (aurora) ─────────────┐  │ │ │approved│ │
│ │  │ Parties, dates,     │ │ "3-yr MSA, auto-renew, GCC data  │  │ │ │ 1d ago │ │
│ │  │ value, term, renewal│ │ residency, liability cap $500k…" │  │ │ └────────┘ │
│ │  │ (editable side-sheet)│ │ 92% conf · [full insights →]     │  │ │            │
│ │  └─────────────────────┘ └──────────────────────────────────┘  │ │            │
│ │  ┌ Obligations & dates ─────┐ ┌ Related ────────────────────┐  │ │            │
│ │  │ ▢ Deliver Q1 report 3/31 │ │ Renews → C-2025-0102        │  │ │            │
│ │  │ ▢ Renewal opt-out 11/1   │ │ Parent: Acme Frame Agmt     │  │ │            │
│ │  │ ▢ Insurance cert due 2/15│ │ Amendments: 2               │  │ │            │
│ │  └──────────────────────────┘ └─────────────────────────────┘  │ │            │
│ └────────────────────────────────────────────────────────────────┘ │            │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Tabs:**
- **Overview** — key terms card (editable via side-sheet), AI summary card (aurora, links to AI Insights), obligations & key dates checklist (each item → reminder, owner, status), related contracts graph (parent/child, renewals, amendments), tags, custom fields, watchers.
- **Document** — the `DocViewer`: if `draft`, opens the editor; if sent/signed, shows the rendered/sealed PDF with the overlay layer (comments, AI highlights, signature fields). Version selector. Download (drafts get a watermark; signed gets the sealed copy + "include certificate" option). Print.
- **Approvals** — the workflow run timeline (stages, who, when, decision, comment, duration), current blocker highlighted, actions (approve/reject/request-changes if it's you; remind/reassign/escalate if you're owner/admin), "change workflow" / "skip step" (admin, audited), pre-submit state shows "no workflow yet — submit to start".
- **Signatures** — recipient list (`SignerRow`s: order, name, role, method, status, timestamp, viewed?), envelope status, "Prepare/Place fields" (→ Module 13), "Send" / "Resend" / "Void", the Certificate of Completion link once done, the `VerifiedSeal`.
- **AI Insights** (aurora "intelligence" surface) — summary, contract classification + confidence, extracted metadata with source links, **clause detection** (list of detected clause types, each linking to its location + the matched text), **risk analysis** (flagged clauses with severity + rationale + suggested fix + "insert standard clause"/"accept risk"/"request change"), **missing-clause suggestions** ("no limitation-of-liability clause — add one?"), smart tags, obligations extraction, AI recommendations specific to this contract, "re-run analysis" button. Everything labeled "Generated by AI · {model} · {date}" with confidence and "verify".
- **Files** — attachments (uploaded supporting docs), source files (the original scan/PDF if OCR-sourced, with a link to the OCR review), version history (each version: who, when, summary of changes, "view", "compare", "restore"), exports (generated PDFs, the signed copy, the certificate, evidence packages).
- (also reachable, often as sub-routes/drawer) **Activity** (full per-contract log), **Access** (who can / who did access — transparency, exportable), **Comments** (drawer tab — threaded, @mention, resolve).

**Right drawer tabs:** Activity (timeline), AI Assistant (ask about *this* contract), Signers (quick status), Comments, Details (metadata at a glance).

**Header actions:** primary changes with stage — `Submit for approval` (draft) / `Approve` (if you're the blocker) / `Prepare for signature` (approved) / `Send for signature` / `Activate` (signed→active is usually automatic) / `Renew` (expiring/active). Secondary: Share, Download, Duplicate, Move, Add to workflow, Set reminders, Add watchers, Archive, Delete, "Compare versions", "Generate report on this contract". `⋯` for the rest.

**States:** loading (skeleton header + tabs) · draft (editable, "submit" prominent) · in-flight (read-only doc, workflow/signers panels active) · sealed/active (locked doc + VerifiedSeal, renewal-aware) · integrity warning (red `IntegrityBanner` if stored hash mismatches — overrides the normal header) · no-access (404-style "you don't have access — request access") · archived (dimmed, "unarchive" action) · expired/terminated (clearly stamped, still fully viewable & auditable) · concurrent edit (presence avatars + "X is editing" — see editor doc).

**Edge cases:** very large documents (lazy-render pages); contracts with 20+ signers (grouped, search within signers); amendments that supersede clauses (visual link, "superseded" badges on old clauses); a contract whose template/clauses changed since creation ("this clause has a newer version — review?"); legal hold (cannot delete/archive — banner + audit).

**RTL:** header, LifecycleBar, tabs, cards all mirror; document content renders in its own language regardless of UI direction (an Arabic contract reads RTL even if UI is EN, and vice-versa); drawer moves to the left. **Mobile:** header collapses (title + status pill + a "▸" for full meta); tabs become a scrollable segmented control or a select; the AI summary and "needs you" actions float to the top; the drawer becomes a bottom-sheet. See Doc 12.

---

## Module 6 — Contract Creation Wizard

**Purpose:** get a *correct, well-formed* contract started fast — choosing the right starting point and capturing the metadata the rest of the system needs. Progressive disclosure: full wizard for newcomers, "skip to editor" for experts.

**Layout** (Wizard archetype — side stepper):
```
┌── stepper ──┐┌────────────────────── step body ─────────────────────────────────┐
│ ① Source    ││  Step 2 of 5 · Details                                            │
│ ● Details   ││  ┌──────────────────────────────────────────────────────────────┐ │
│ ○ Parties   ││  │ Title*        [Master Services Agreement — Acme Corp_______]  │ │
│ ○ Terms     ││  │ Contract type*[ MSA ▾ ]   Department [ Procurement ▾ ]       │ │
│ ○ Review    ││  │ Reference #   [auto: C-2026-0482]  Language [EN][ع][both]    │ │
│             ││  │ Owner*        [ J.Doe ▾ ]   Watchers [ +add ]                │ │
│  (Source     ││  │ Tags          [#renewal × ] [+]   Folder [ Procurement ▾ ]  │ │
│   options:   ││  │ Custom fields (from tenant schema): Cost center [____] …     │ │
│   • Template ││  │ ┌ AI assist ────────────────────────────────────────────┐   │ │  ← aurora;
│   • Upload   ││  │ │ Paste a short brief and I'll pre-fill type, parties,   │   │ │     only on
│   • Blank    ││  │ │ and suggest a template:  [__________________] [Suggest]│   │ │     this assist box
│   • Import)  ││  │ └────────────────────────────────────────────────────────┘   │ │
│             ││  └──────────────────────────────────────────────────────────────┘ │
│             ││  [‹ Back]                          [Save draft]   [Continue ›]     │
└─────────────┘└───────────────────────────────────────────────────────────────────┘
```

**Steps:**
1. **Source** — choose: *From template* (searchable gallery: name, category, language, last used, preview; bilingual templates flagged) · *Upload & scan* (→ launches the OCR flow, comes back here pre-filled from the extraction) · *Blank* · *Import in bulk* (→ batch flow). "Expert mode: skip to editor" link.
2. **Details** — title, type (drives default workflow, default clauses, custom-field schema), reference # (auto, editable), language(s), owner, watchers, tags, folder, department, tenant custom fields. Optional AI-assist box: paste a brief → it pre-fills type/parties/value and recommends a template (aurora-tinted; clearly "AI suggestion — review").
3. **Parties** — internal entity (which of our legal entities) + counterparties (name, type, address, signatory contact name+email — these become signers later); add multiple; pull from a saved contacts/companies list; "this counterparty has 4 other contracts" hint.
4. **Terms** — start/end dates (or "effective on signature" + duration), value/currency, payment terms, renewal type (none / auto-renew with notice period / manual), notice period, governing law, key dates to track (each becomes an obligation/reminder). Template-driven fields render here too (the template's variables).
5. **Review** — summary of everything + a live preview of the generated document (template merged with the entered variables) + "what happens next" (which workflow it'll go to, who'll be notified) + choice: **Open in editor** (refine before submitting) or **Submit for approval now** or **Save as draft**.

**Key components:** side `Stepper` (clickable to go back to completed steps), per-step form cards, sticky footer (Back / Save draft / Continue), template gallery, contacts picker, date pickers, currency input, the AI-assist box, the live preview pane on Review.

**States:** in-progress (autosaves a draft contract on every step so nothing is lost) · validation errors (inline, blocks Continue, summary at top) · resumed (re-enter the wizard for a half-done draft from where you left) · from-OCR (steps 2–4 pre-filled with extracted values + confidence chips; user confirms/edits) · template with no variables (skip straight to a short Details+Parties then Review) · cancelled (the draft stays in "Drafts" — not lost).

**Edge cases:** changing the contract type mid-wizard (warns if it'll change the workflow/clauses/custom fields, re-validates); a template that references clauses the tenant has since updated (offer the new versions); creating from a contract ("duplicate" → wizard pre-filled from the source); bulk import drops you into a different flow (Module: bulk import — a table where you map columns/extracted fields and approve in batch).

**RTL:** stepper on the right, footer buttons mirror, form labels start-aligned, preview renders in the document's language. **Mobile:** stepper becomes a top progress bar + "Step 2/5"; one form section per screen; sticky footer; AI-assist collapsible; see Doc 12.

---

## Module 7 — Rich-Text Contract Editor

**Full spec in [Doc 11 — Contract Editor](./11-contract-editor.md).** Summary placement: the editor opens from the creation wizard ("Open in editor"), from a draft contract's Document tab, and for template authoring. It's a block-based editor (Notion × Google Docs × PandaDoc): blocks, "/" slash menu, dynamic variables/merge fields, clause insertion from the library, an AI writing assistant (draft a clause, simplify, translate EN↔AR, summarize, "make this clause more favorable to us", "check for missing standard clauses"), inline comments + suggestion mode (redlines), real-time collaboration with presence, full version history with diff/compare/restore, and a right rail (variables, clauses, comments, AI, versions). When done: "Submit for approval" / "Save draft" / "Prepare for signature" (if no approval needed). Output renders to a faithful PDF for signing.

---

## Module 16 — Template Management

**Purpose:** the reusable starting points. A template *is* a contract document (same BlockEditor) in "template mode" — with variables, conditional sections, attached default clauses, a default workflow, a custom-field schema, and a language pairing (EN + AR versions linked).

**Layout** (List archetype → Editor archetype for one template):
```
┌── sidebar ──┐┌──────────────────────── content ─────────────────────────────────┐
│ CATEGORIES  ││ Templates › All                          [+ New template ▾]       │
│ ▸ All       ││ ┌ FilterBar: [Search] Category▾ Language▾ Status▾ Owner▾ ────────┐│
│ ▸ NDA       ││ │ 64 templates                                                   ││
│ ▸ MSA       ││ ├────────────────────────────────────────────────────────────────┤│
│ ▸ Lease     ││ │ Name             Category Lang  Status   Used  Updated   ⋮      ││
│ ▸ Employment││ │ Mutual NDA       NDA      EN+ع  Published 312   2d        ⋮     ││
│ ▸ Vendor    ││ │ MSA (Standard)   MSA      EN    Published 88    1w        ⋮     ││
│ ▸ Procuremen││ │ Office Lease GCC Lease    EN+ع  Draft     —     today     ⋮     ││
│ ▸ Gov forms ││ │ ...                                                            ││
│ [+ New]     ││ └────────────────────────────────────────────────────────────────┘│
└─────────────┘└───────────────────────────────────────────────────────────────────┘

Open a template → BlockEditor in "template mode" with a right rail:
  [Variables]  define merge fields (name, type: text/number/date/currency/party/select,
               default, required, help text, validation) — inserted into the doc as chips
  [Conditional sections]  "show §7 only if {renewal_type} = auto"
  [Default clauses]  attach clauses from the library that auto-insert; mark some "locked"
  [Default workflow]  which approval workflow contracts from this template use
  [Custom fields]  the metadata schema contracts from this template inherit
  [Language pair]  link the EN and AR versions; "translate this template" (AI draft → human review)
  [Versions / publish]  draft → in review → published; only published templates appear in the wizard;
               changing a published template creates v2 (existing contracts keep their version)
  [Usage]  how many contracts, recent ones, "this template's contracts have 18% higher risk flags"
```

**States:** draft / in review / published / archived; "has a newer version" badge on contracts built from older versions; permissions (who can create/edit/publish templates — usually Manager+); preview ("see what a contract from this looks like with sample data").

**Edge cases:** a variable referenced in the doc but not defined (validation error, can't publish); a clause attached as default but later deprecated (warning); deleting a template that contracts were built from (block — archive instead; contracts keep their snapshot).

**RTL/Mobile:** template *list* mirrors normally; editing a template is a desktop-class task (the editor is desktop-first; mobile is view-only / can't author templates) — see Doc 11/12.

---

## Module 17 — Clause Library

**Purpose:** the reusable building blocks — vetted, versioned, bilingual clauses with metadata (risk level, jurisdiction, "fallback" alternatives). It's an inline-database (Notion-style) the AI also draws on for "insert standard clause" and "missing clause" suggestions.

**Layout** (List archetype, "database" view):
```
┌── sidebar ──┐┌──────────────────────── content ─────────────────────────────────┐
│ TYPES       ││ Clauses › All                            [+ New clause]            │
│ ▸ All       ││ ┌ FilterBar: [Search text…] Type▾ Jurisdiction▾ Risk▾ Status▾ Lang▾│
│ ▸ Confiden. ││ │ View: [Table] [Board by type] [By jurisdiction]   148 clauses    │
│ ▸ Liability ││ ├──────────────────────────────────────────────────────────────────┤│
│ ▸ Indemnity ││ │ Title              Type      Jur.  Risk  Lang  Status  Used  ⋮   ││
│ ▸ Termination││ │ Limitation of Liab Liability Oman  ▲Med  EN+ع  Approved 210  ⋮  ││
│ ▸ IP        ││ │  └ fallbacks: "Mutual cap", "Higher cap (client)"                ││
│ ▸ Data/GDPR ││ │ GCC Data Residency Data      GCC   —     EN+ع  Approved 95   ⋮  ││
│ ▸ Force Maj.││ │ Mutual NDA Confiden Confiden. Any   —     EN+ع  Approved 312  ⋮  ││
│ ▸ Governing ││ │ Auto-renewal 12mo  Renewal   Any   ▲Med  EN+ع  In review —    ⋮  ││
│ [+ New]     ││ │ ...                                                              ││
└─────────────┘└───────────────────────────────────────────────────────────────────┘

Open a clause → detail:
  • The clause text (EN tab / ع tab — linked, "translate" with AI draft + human review)
  • Variables it uses (shared with templates)
  • Metadata: type, jurisdiction(s), risk level + rationale, "use when…", "don't use when…"
  • Fallback / alternative clauses (ranked: preferred → acceptable → walk-away)
  • Approval status (draft → legal review → approved → deprecated) + who approved + when
  • Versions (each contract that used it snapshots the version; "v2 available" nudges)
  • Usage analytics (how many contracts, which templates default to it, "contracts with this clause
    have X% fewer risk flags")
  • AI: "summarize this clause", "compare with the version in {contract}", "explain the risk"
```

**How it plugs in:** editor "/clause" or the right-rail Clauses panel inserts a clause (snapshotting its current version); AI risk analysis maps flagged contract clauses to library clauses ("your clause differs from our approved Limitation of Liability — here's the diff"); "missing clause" suggestions pull from clauses marked "standard for {type}"; templates attach default clauses.

**States:** draft / legal-review / approved / deprecated; "deprecated — use {replacement}" banner; permissions (who can author/approve clauses — usually legal/admin); language-pair completeness indicator.

**Edge cases:** a clause used in active contracts gets deprecated (those contracts keep their snapshot + a "review" nudge; can't be hard-deleted); conflicting clauses (mutually exclusive — flagged if both inserted); jurisdiction mismatch (warn if a clause's jurisdiction doesn't match the contract's governing law).

**RTL/Mobile:** list mirrors; clause text renders in its own language; mobile is read/search-only for the library (authoring clauses is a desktop task).

---

> Continued in **[Doc 07 — Modules, Part 2: Intelligence & Lifecycle](./07-modules-part2.md)** (OCR upload/processing/extraction, AI analysis, workflow builder, signature placement, signing, lifecycle timeline, renewals, expiry, search, AI assistant) and **[Doc 08 — Modules, Part 3: Admin & Trust](./08-modules-part3.md)**.
