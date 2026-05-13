# 12 — Mobile Experience

Mobile is **not** "the desktop app squeezed." It's a focused companion for the things people actually do on a phone: **approve, sign, scan, get notified, glance**. Everything else degrades gracefully ("best on desktop"). Built as a **responsive PWA** (installable, offline-aware, web-push) on the same Next.js codebase; optional thin native wrappers (Capacitor/Expo) later if app-store presence + native push/camera/biometrics demand it.

---

## 1. What mobile is *for* (priority order)

1. **Approvals** — review what's blocking you and approve/reject/request-changes in 2–3 taps, from a push notification or email.
2. **Signing** — the full signing ceremony, one-handed, polished (this is also the external signer portal, which is *primarily* a mobile experience — counterparties open links on phones).
3. **Scanning** — capture documents with the camera, guided multi-page, auto-crop, send to the OCR pipeline.
4. **Notifications** — push for approvals/signatures/mentions/urgent expirations; an inbox to triage.
5. **Glance** — dashboard: what needs me, what's at risk, key numbers.
6. **Look things up** — search and view a contract (read the doc, see status, see who's blocking).
7. **Light edits** — comments, accept/reject suggestions, fill metadata. *Not* heavy drafting, *not* workflow authoring, *not* signature-field placement, *not* template/clause authoring, *not* admin matrix editing — those say "open on desktop" with a one-tap "email myself a link."

---

## 2. Navigation (mobile shell)

- **Bottom tab bar** (5): **Home** (dashboard) · **Contracts** (list) · **Inbox** (approvals + signatures + notifications, with a badge) · **Scan** (camera, center, slightly raised — the "+" energy) · **More** (workflows view-only, reports, templates/clauses read-only, settings, account, switch workspace, theme, language).
- **Top bar**: contextual title + back + a `⋯` overflow + (on lists) a filter icon that opens a **bottom-sheet** of filters.
- **Right drawer → bottom-sheet**: the Activity / AI Assistant / Signers / Comments tabs become a swipe-up bottom-sheet with a segmented control.
- **⌘K → full-screen search** (a search icon in the top bar; on a phone it's a full page, not a palette).
- **Progress Tray → a collapsible pill** anchored above the tab bar ("3 documents processing…" → tap to expand to a sheet).
- **RTL**: the tab bar order reverses, the back gesture flips, sheets and the drawer mirror — the whole shell is `dir`-aware.

---

## 3. Key mobile screens

**Dashboard (Home):** a vertical stack — a greeting, a horizontal scroll-snap **carousel of KPI cards** (Total / Pending approvals / Awaiting signature / Expiring / OCR today / Open risks), then **"Needs your attention"** as the hero (a list of approval/sign/expiry cards, each with one inline action), then the **AI Recommendations** card (aurora), then **recent activity**. Quick Create as a `+` FAB or in the More tab. Charts are simplified (one sparkline per card; full charts say "view on desktop for detail" but render a basic version).

**Contracts list:** the DataTable becomes a **card list** (title + status pill + lifecycle dots + owner avatar + expiry-in-Nd + risk badge); tap → detail; long-press → multi-select → a bottom bulk-action sheet; filter icon → bottom-sheet filters + saved views; pull-to-refresh; infinite scroll. Board/Calendar views available (swipeable columns / swipeable month) but the card list is the default.

**Contract detail:** a collapsing header (title + status pill + a "▸" to expand full metadata + the LifecycleBar as a horizontal dot-track); the **AI summary** and **"needs you" actions** float to the top; tabs (Overview / Document / Approvals / Signatures / AI Insights / Files) become a scrollable segmented control or a select; the **Document** tab is the DocViewer (pinch-zoom, page swipe, thumbnails sheet, search); the **Approvals** tab shows the run timeline + inline approve/reject if it's you; **AI Insights** sections are collapsible accordions with "needs you" risks at the top and "insert clause"/"request change" actions that queue a change request (no desktop editor needed); the drawer tabs are a bottom-sheet.

**Inbox:** three sub-tabs (Notifications / My Approvals / My Signatures). Approval/signature cards are **swipe-actionable** (swipe → Approve / Sign with a confirm step; swipe other way → Open); each shows the contract + AI summary + risk flags + time waiting; tap an approval → a focused review screen (summary, risks, who else is on the chain) → Approve (+ optional comment). Push notifications deep-link straight to the relevant action.

**Scan (camera):** the hero mobile feature. Tap **Scan** → camera opens with **live edge detection** (a highlighted quad over the detected document) → tap to capture (or auto-capture when steady) → it auto-crops + enhances + shows a preview → "Add page" (multi-page) or "Retake" or "Use this" → after all pages, "Looks blurry on page 2 — retake?" nudges → choose what happens after OCR (create a contract / just extract) + assign type/owner/folder → "Start OCR" → it uploads, the Progress Tray pill shows progress, you get a push when it's ready → tap → the **mobile review screen**.

**OCR review (mobile):** the side-by-side desktop layout becomes **stacked** — the document page on top (tap a field below → the box pulses on the page; pinch-zoom the page), the **extracted fields** below as a list with confidence chips; or a **"verify mode"** that shows one uncertain field at a time with its source region zoomed-in on top and Accept / Edit / Skip below, swiping through the amber/red fields → then "Create contract." Designed so a person can clear a scanned contract on the train.

**Signing ceremony (Module 14) / external portal (Module 21):** **first-class mobile design** — branded header, a progress rail (Verify → Sign → Done), the document large and scrollable with fields that **pulse**, a "↓ next field" button, OTP step with SMS-autofill, e-sign consent, the **adopt-signature** flow (type with the OS keyboard, or **draw with a finger** on a full-width canvas, or upload a photo of a signature), per-field date/name/title auto-fill, a bottom-anchored **Finish**, then the **done screen** with the green VerifiedSeal and "download what you signed / we'll email the executed copy." One-handed, big touch targets, no horizontal scrolling, fully accessible (VoiceOver/TalkBack narrates "you have 3 required fields", high-contrast, scalable text).

**Search:** full-screen — a search field (NL queries work; the parsed filters are shown and editable), recent searches, results as cards grouped by type, filters in a bottom-sheet; voice input offered.

**Settings / Account:** the mobile-relevant bits work fully (MFA setup, sessions list + "sign out all", notification preferences, language, theme, profile, delegate-my-approvals); the heavy admin matrices (roles, custom fields, SSO, workflow editing) show a read-only summary + "manage on desktop."

---

## 4. Mobile-specific interaction patterns

- **Push notifications** (web-push now; native if wrapped later) for approvals, signature requests, @mentions, urgent expirations (≤7d, passed opt-out), OCR-done; tapping deep-links to the action; quiet hours respected; configurable per type.
- **Biometric unlock** (Face/Touch ID via WebAuthn/passkeys or the native wrapper) for app re-entry and as a step-up factor on sensitive actions.
- **Bottom sheets** for filters, the drawer tabs, the bulk-action bar, the Progress Tray, contextual `⋯` menus — never modals that fight the keyboard.
- **Swipe actions** on list rows (approve/sign/open) and **pull-to-refresh** everywhere.
- **Camera + photo-library + share-sheet ingestion** ("share to {App}" from another app's PDF → opens the upload flow).
- **Offline-aware:** the dashboard, recent contracts, and the inbox cache for offline viewing; approvals/signs queue and submit on reconnect (with a clear "will submit when online" state); the editor's light edits queue too; a global "you're offline — showing cached data" banner.
- **One-handed reach:** primary actions bottom-anchored (the thumb zone); the FAB / Scan tab where the thumb lands; long lists scroll, key actions don't require reaching the top.
- **Reduced data / slow networks:** progressive image loading, skeletons, document pages loaded on demand, "tap to load full document."

---

## 5. Responsive breakpoints (how the desktop layout collapses)

| Width | Shell | Notes |
|---|---|---|
| `≥1280` (xl) | full 3-pane: icon rail + contextual sidebar + content + right drawer | the canonical desktop experience |
| `1024–1279` (lg) | icon rail + content + right drawer; contextual sidebar collapses to a toggle | editor/canvas full-width |
| `768–1023` (md, tablet) | collapsed icon rail (icons only) + content; sidebar & drawer become slide-overs; tables stay tables but compact | editor: read + comment + light edits; canvas: view-only; signature placement: "best on desktop" |
| `<768` (sm, phone) | the mobile shell above: bottom tab bar, sheets, card lists, full-screen search | the focused companion experience |

The same React components render across all of these — they're built mobile-up with responsive variants, not as separate apps. Heavy desktop-only surfaces (workflow canvas editing, signature-field placement, template/clause authoring, the RBAC matrix) detect small screens and show a graceful "this works best on a larger screen — [email myself a link]" instead of a broken layout.

---

## 6. Native-app question (later)

The PWA covers ~95% of the value. Consider thin **Capacitor/Expo wrappers** (same web codebase inside a native shell) if/when: app-store discoverability matters for sales; native push reliability (esp. iOS) becomes a pain point; deeper camera control / native document-scanner SDKs meaningfully beat the web camera for Arabic scans; biometric integration needs to be rock-solid; or enterprise MDM/managed-app distribution is a requirement. A *fully* native app (separate codebase) is only justified if mobile becomes a primary surface — unlikely for a CLM, where desktop is where the real work happens. Decision deferred; the responsive PWA ships first.
