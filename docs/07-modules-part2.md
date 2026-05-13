# 07 — Modules, Part 2: Intelligence & Lifecycle

Covered here: **8 OCR Upload · 9 OCR Processing · 10 OCR Extracted Data · 11 AI Analysis · 12 Approval Workflow Builder · 13 Signature Placement · 14 Digital Signing · 15 Lifecycle Timeline · 26 Expiry Tracking · 27 Renewal Management · 28 Smart Search · 29 AI Assistant Panel**. The OCR/AI experience is detailed further in [Doc 09](./09-ocr-ai-experience.md); the workflow builder in [Doc 10](./10-workflow-builder.md).

---

## Module 8 — OCR Upload Experience

**Purpose:** get documents into the system as painlessly as the Dropbox-ref upload toast made it look — and immediately set expectations about the intelligence pipeline they're entering.

**Layout** (`/intelligence/upload` — Viewer-ish archetype):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Intelligence › Upload & Scan                                                       │
│ ┌─────────────────────────────── DROP ZONE (aurora-tinted) ──────────────────────┐ │
│ │            ⤵  Drop files here, or                                              │ │
│ │            [ Browse ]  [ 📷 Scan with camera ]  [ ☁ Import from Drive/SharePoint ]│
│ │            PDF, JPG, PNG, TIFF, multi-page · up to 50MB/file · 200 files/batch  │ │
│ │            ✓ Arabic + English + multilingual  ✓ tables  ✓ signatures & stamps  │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
│ ── QUEUED (per-file rows, like the Dropbox-ref upload toast) ───────────────────── │
│ │ ▣ Acme_MSA_signed.pdf      12 pages   ▓▓▓▓▓▓▓░░ 78%  uploading…       [×]      │ │
│ │ ▣ Lease_TowerB.jpg          1 page    ✓ uploaded · queued for OCR    [×]      │ │
│ │ ▢ Vendor_NDA_scan.tiff      3 pages   ⚠ too low res (120dpi) — proceed anyway?  │ │
│ │ ▢ random_photo.png          —         ✗ doesn't look like a document — remove? │ │
│ ── BATCH OPTIONS ──────────────────────────────────────────────────────────────── │
│ │ Languages: [auto-detect ▾]  Auto-crop ☑  Enhance ☑  Detect signatures ☑       │ │
│ │ After OCR: ◉ Create one contract per file  ○ One contract (merge files)        │ │
│ │ ○ Just extract data, don't create contracts (review only)                      │ │
│ │ Assign: Type [auto ▾] · Owner [me ▾] · Folder [— ▾] · Tags [+]                │ │
│ │                                          [ Cancel ]  [ Start OCR (3 files) ▸ ] │ │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Key components:** the aurora drop zone (drag, browse, camera-capture (mobile/webcam — multi-shot, auto-edge-detect, re-take per page), cloud picker), the per-file queue (name, page count, upload progress, validation badges, remove), batch options (language hint, preprocessing toggles, post-OCR behavior, default metadata), client-side validation (type, size, "this might not be a document" heuristic, low-DPI warning), the `ProgressTray` takes over once "Start OCR" is hit.

**States:** empty (just the drop zone + reassuring capability list) · uploading (per-file progress) · mixed (some uploaded, some failed, some warned) · ready (Start enabled) · started (transitions to the processing screen / minimizes to the tray) · over-quota (plan limit reached → "upgrade or remove files") · resumable (a failed upload can retry without re-selecting).

**Edge cases:** password-protected PDFs (prompt for password); corrupt files (clear error + skip); 200-file batch (chunked uploads, the tray handles it, you can navigate away); same file uploaded twice (dedupe by hash, "you already have this — open it?"); a file that's already text-based PDF (skip OCR, go straight to AI extraction — faster).

**RTL:** layout mirrors; file names with Arabic render correctly (bdi-isolated). **Mobile:** camera is the hero ("Scan a document"); guided multi-page capture; the tray is a bottom-sheet; see Doc 12.

---

## Module 9 — OCR Processing Screen

**Purpose:** make a 10–120 second wait feel intelligent and trustworthy, not like a spinner. (Detailed animation/state spec in Doc 09.)

**Layout** (`/intelligence/jobs/:jobId` — live):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Intelligence › Processing "Procurement Q2 batch" · 3 files · 16 pages              │
│ ┌─ overall ──────────────────────────────────────────────────────────────────────┐ │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░  page 11 of 16 · ~22s left · [run in background →]          │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌─ live preview (aurora "scan" sweep over the page) ──┐ ┌─ pipeline stages ───────┐ │
│ │  [page thumbnail with a soft light sweep,           │ │ ✓ Upload                │ │
│ │   bounding boxes fading in as text is detected,     │ │ ✓ Preprocess (rotate,   │ │
│ │   "detecting tables…" "detecting signatures…"]      │ │   deskew, denoise, crop)│ │
│ │                                                     │ │ ⟳ OCR (Arabic+English)  │ │
│ │   [‹ prev page]  page 11/16  [next page ›]          │ │ ⟳ Layout & tables       │ │
│ │   detected so far: 8 paragraphs, 1 table,           │ │ ○ Signature/stamp detect│ │
│ │   2 signature blocks, 1 stamp, langs: ar+en         │ │ ○ AI extraction         │ │
│ └─────────────────────────────────────────────────────┘ │ ○ Risk & summary        │ │
│ ┌─ per-file ──────────────────────────────────────────┐ └─────────────────────────┘ │
│ │ Acme_MSA_signed.pdf   12p  ▓▓▓▓▓▓▓▓▓░  done OCR, AI next                       │ │
│ │ Lease_TowerB.jpg       1p  ✓ complete — [review →]                            │ │
│ │ Vendor_NDA_scan.tiff   3p  ⚠ page 2 low-confidence — will flag for review     │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
│  [ Cancel job ]                                  on done → [ Review extracted data ▸ ]│
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Behavior:** WebSocket (or SSE / poll) stream of progress events from the Celery job → updates the bar, the stage list, the live preview. "Run in background" minimizes to the `ProgressTray` and you can keep working; you're notified (toast + tray + notification center) when it's ready. Per-file rows show partial completion (a 1-page file finishes while a 50-pager is still going → "review now" link appears immediately for the done one).

**States:** queued (waiting for a worker — "starting…") · running (the above) · partially done (some files complete) · done (CTA to review) · failed (a file or page failed → clear reason + per-item retry: "page 4 failed: image too dark — re-upload page / skip page / enter manually") · cancelled · timed-out (rare — offer retry on a higher-priority queue). The job persists in the `jobs` table so refreshing the page resumes the live view.

**Edge cases:** worker crash mid-job (the job is retried/resumed idempotently); a 200-file batch (the tray, not this full screen, is the right surface — this screen shows aggregate + lets you drill in); the user closes the tab (job continues server-side; tray + notifications on return).

**RTL/Mobile:** mirrors; on mobile this is usually just the tray's expanded view (a list of files with progress) rather than the full split layout.

---

## Module 10 — OCR Extracted Data Screen

**Purpose:** the trust moment — show what the machine read, where it read it, and how sure it is; let the human verify the uncertain bits fast. (Full interaction spec in Doc 09.)

**Layout** (`/intelligence/jobs/:jobId/review` — Viewer archetype, side-by-side):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Review extraction · Acme_MSA_signed.pdf (1 of 3)        [‹ prev file] [next file ›] │
│ ┌──────────── ORIGINAL (DocViewer + highlight boxes) ──┐ ┌─ EXTRACTED FIELDS ─────┐ │
│ │  [rendered page; clicking a field on the right       │ │ ⚡ Auto-extracted · review│ │  ← aurora
│ │   pulses its source box here; boxes are color-coded  │ │   2 of 9 fields need you │ │
│ │   by confidence: teal/amber/red]                     │ │ ─────────────────────── │ │
│ │   ┌─────────────────────┐                            │ │ Contract type           │ │
│ │   │ "MASTER SERVICES…"  │ ← title box (teal)         │ │  [ MSA ▾ ]      ●96%    │ │
│ │   └─────────────────────┘                            │ │ Title                   │ │
│ │   ...                                                │ │  [Master Services Agmt…]●94%│
│ │   ┌──────┐ "between Acme Corp ('Provider')…"          │ │ Counterparty            │ │
│ │   └──────┘   (party box, teal)                       │ │  [Acme Corp]    ●91%    │ │
│ │   ...                                                │ │ Effective date          │ │
│ │   ┌────┐ "1 January 2026" (date box, amber)          │ │  [2026-01-01]   ●72% ⚠  │ │  ← amber: in
│ │   └────┘                                             │ │ End date                │ │     "verify all"
│ │   ...                                                │ │  [__________]   ●41% ⚠⚠ │ │  ← red: needs you
│ │   ┌────────┐ scribble (signature, "detected")        │ │ Value                   │ │
│ │   └────────┘                                         │ │  [$120,000 ▾USD] ●88%   │ │
│ │                                                      │ │ Renewal                 │ │
│ │  [page 1/12 ‹ ›][fit][zoom][thumbnails]              │ │  [Auto-renew ▾] ●77% ⚠  │ │
│ │                                                      │ │ Governing law           │ │
│ │                                                      │ │  [Oman]         ●83%    │ │
│ │                                                      │ │ Detected clauses (12) ▾ │ │  ← expands to
│ │                                                      │ │ Detected signatures (2)▾│ │     a list, each
│ │                                                      │ │ Detected stamps (1) ▾   │ │     linking to its box
│ │                                                      │ │ ─────────────────────── │ │
│ │                                                      │ │ Tables found: 1 → [view]│ │
│ │                                                      │ │ Languages: ar + en      │ │
│ └──────────────────────────────────────────────────────┘ └─────────────────────────┘ │
│  [Re-run OCR ▾] [Verify all (2) ▸]            [Discard]  [Create contract from this ▸]│
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Key components:** the split `DocViewer` (left, with the confidence-colored bounding-box overlay) ↔ the extracted-fields panel (right, aurora-tinted "intelligence" surface); each field is an editable input with a `ConfidenceChip`; clicking a field highlights+pulses its source box (and vice versa); "Verify all" steps you through only the amber/red fields one at a time (next/skip/accept); collapsible sections for detected clauses, signatures, stamps, tables (each item links to its location); "re-run OCR" (whole doc or a single page, optionally with different settings — e.g., force a language, higher quality, on a priority queue); footer actions: discard, or "create contract from this" (carries the verified values into the creation wizard at the Review step, attaches the source files, sets status `draft`).

**States:** ready (the above) · all-high-confidence (no red/amber → "Looks good — all 9 fields high confidence. [Create contract ▸]" with verify-all skippable) · low-overall (a banner: "This scan was hard to read — consider re-uploading a clearer copy" + the data still shown, mostly red) · text-PDF (no OCR was needed → "Extracted from native text, high confidence" + the same review UI) · multi-file batch (a strip at the top to move between files; "verify all & create all" bulk action that runs each file's verify-all in sequence) · in-progress save (edits autosave to the extraction record so you can leave and return).

**Edge cases:** a table that needs to map to structured fields (a "map table" mini-tool: pick which columns are which); two candidate values for one field (a small chooser: "found '2026-01-01' on p.1 and '2026-12-31' on p.1 — which is the effective date?"); right-to-left text whose order the OCR got wrong (a "this looks reversed — flip?" affordance); a field the model is *confident* about but is *wrong* (the human edits it — and that correction can optionally feed a feedback loop / fine-tuning dataset).

**RTL/Mobile:** the split layout stacks on mobile (original on top, fields below, or a toggle); RTL flips the panes; the document renders in its own language regardless. See Doc 12 for the mobile review pattern (one field at a time, swipe through).

---

## Module 11 — AI Analysis Screen

**Purpose:** the contract's "AI Insights" — summary, classification, clause detection, risk analysis, missing-clause suggestions, obligations, recommendations — presented as a *labeled, confidence-calibrated, source-linked* analysis, not a magic verdict. This is both a tab on the contract detail (Module 5) and a standalone view; here we spec the content.

**Layout** (`/contracts/:id/insights` — content area, all aurora-tinted "intelligence" surface):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ MSA — Acme Corp › AI Insights        Generated by AI · {model} · {date} · [Re-run]  │
│ ┌─ SUMMARY ──────────────────────────────────────────────────────────────────────┐ │
│ │ "A 3-year master services agreement between {us} and Acme Corp. Auto-renews for │ │
│ │ 12-month terms unless cancelled 60 days prior. Liability capped at $500k.       │ │
│ │ Governing law: Oman. Includes GCC data-residency obligations. Payment net-30."  │ │
│ │ Confidence ●92%  ·  [shorter] [longer] [in Arabic] [copy] [explain]            │ │
│ ├─ CLASSIFICATION & METADATA ────────────────────────────────────────────────────┤ │
│ │ Type: MSA ●96% · Family: Services · Parties: {us}, Acme Corp ●91% · Value $120k │ │
│ │ ●88% · Term 2026-01-01 → 2026-12-31 ●72%⚠ · Renewal: auto ●77%⚠ — each links to │ │
│ │ its source clause. [edit any]                                                  │ │
│ ├─ DETECTED CLAUSES (12) ────────────────────────────────────────────────────────┤ │
│ │ ✓ Confidentiality §3   ✓ Limitation of Liability §8 (▲Med)   ✓ Termination §11 │ │
│ │ ✓ IP §6   ✓ Data Protection §9   ✓ Governing Law §15   ✓ Force Majeure §14 …   │ │
│ │ each: [go to clause] [compare to library version] [explain]                    │ │
│ ├─ RISK ANALYSIS ────────────────────────────────────────────────────────────────┤ │
│ │ ▲ HIGH — §8 Limitation of Liability: cap ($500k) below our standard ($1M);      │ │
│ │   no carve-outs for IP/confidentiality breaches. → [insert standard clause]     │ │
│ │   [request change in workflow] [accept risk + note]                            │ │
│ │ ▲ MED — §12 Auto-renewal: 60-day notice is long; consider 30. → [edit] [accept] │ │
│ │ ▲ MED — §9 Data: references "applicable law" without naming PDPL. → [clarify]   │ │
│ │ — LOW — payment terms, IP assignment, term length: standard.                   │ │
│ │ Overall risk: ▲ Medium · 1 high, 2 medium, … · [add all suggested changes]     │ │
│ ├─ MISSING / RECOMMENDED CLAUSES ────────────────────────────────────────────────┤ │
│ │ ⚠ No "Limitation of Liability — carve-outs" clause (standard for MSA). [insert] │ │
│ │ ⚠ No "Subcontracting / Assignment" clause. [insert]                            │ │
│ │ ⚠ No "Audit rights" clause. [insert]   (each from the clause library)          │ │
│ ├─ OBLIGATIONS & KEY DATES ──────────────────────────────────────────────────────┤ │
│ │ ▢ Renewal opt-out by 2026-11-01 (us)   ▢ Insurance cert by 2026-02-15 (Acme)   │ │
│ │ ▢ Quarterly report by each quarter-end (Acme)   → [add all as reminders]       │ │
│ ├─ SMART TAGS ───────────────────────────────────────────────────────────────────┤ │
│ │ #auto-renew #data-residency #liability-cap #oman-law #net30  [accept] [edit]   │ │
│ └────────────────────────────────────────────────────────────────────────────────┘ │
│  Every section: confidence shown · source-linked · "explain" · human-overridable.   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Principles:** (1) always labeled as AI-generated, with model + timestamp; (2) always shows confidence per item; (3) always source-linked (click → the clause/paragraph highlights in the document); (4) always overridable by a human (and overrides are recorded); (5) actions are *concrete* — "insert standard clause from library", "request this change in the approval workflow", "accept risk with a note", "add as reminder", "explain"; (6) "re-run analysis" (e.g., after edits, or to use a newer model) and a visible "this analysis is for version N" so stale analysis is obvious.

**States:** computing (skeleton + "analyzing…" with the aurora breathing) · ready · stale ("the document changed since this analysis — [re-run]") · failed (clear error + retry) · low-confidence overall ("hard to analyze — likely a poor scan or unusual format; treat results cautiously") · no-AI-plan (the section shows an upsell: "AI analysis is available on the Pro plan").

**Edge cases:** very long contracts (chunked analysis, "analyzing pages 40–60…"); non-contract documents uploaded by mistake (the classifier says "this doesn't look like a contract — proceed?"); contracts in languages the AI is weaker in (lower confidence, a note); a clause the AI flags that's actually fine ("dismiss this flag" + reason → improves the model over time).

**RTL/Mobile:** mirrors; Arabic summaries render RTL within the (possibly EN) UI; on mobile, sections are collapsible accordions, "needs you" risks float to the top, "insert clause" actions still work (they queue a change request rather than opening the desktop editor). See Docs 09, 12.

---

## Module 12 — Approval Workflow Builder

**Full spec in [Doc 10 — Workflow Builder](./10-workflow-builder.md).** Module-level summary: a visual, ClickUp/Monday/Zapier-style canvas at `/workflows/:id`. Left = node palette (Start → Approval step, Parallel group, Condition (if value/type/department/risk/tag/custom-field), Notify, Set field, Wait/SLA + escalation, Sign step, End). Center = the canvas: draggable nodes, edges, sequential & parallel branches, condition forks, escalation paths drawn explicitly. Right = the selected node's config (who approves — specific users / roles / "the contract owner's manager" / dynamic from a field; required vs any-N; SLA + reminder cadence + on-breach action (remind/escalate/skip/auto-approve); allowed decisions). Top = name, status (draft/active), "Simulate" (run a what-if with a sample contract → see the path it takes), version history, "set as default for {contract types}". Validation: no orphan nodes, every path reaches End, every approval step resolves to at least one person, no infinite loops. Also: a `/workflows/:id/runs` view — every contract currently/previously on this workflow, where it sits, a stage-by-stage bottleneck heatmap, avg time per stage, SLA-breach rate, rejection rate.

---

## Module 13 — Signature Placement UI

**Purpose:** decide *who signs what, where, and in what order* — the DocuSign-grade "prepare to send" experience.

**Layout** (`/contracts/:id/prepare-signature` — Editor/Viewer hybrid archetype):
```
┌── recipients ──┐┌──────────────── DOCUMENT (DocViewer + field overlay) ───────────┐
│ RECIPIENTS     ││ Prepare "MSA — Acme Corp" for signature           [Preview][Send ▸]│
│ 1 ▣ J.Doe (us) ││ ┌─────────────────────────────────────────────────────────────┐ │
│   signer · 1st ││ │  page 1 of 12                                               │ │
│   ✉ verify:none││ │   §1 …………………………………………                                     │ │
│ 2 ▣ A.Khan(Acme││ │   §2 …………………………………………                                     │ │
│   signer · 2nd ││ │                                                             │ │
│   ✉ verify:OTP ││ │  ┌──────────────┐  ← [Signature] field, assigned to Acme    │ │
│ 3 ▢ CC: legal@ ││ │  │  Sign here   │     (color-coded per recipient), required  │ │
│   copy only    ││ │  └──────────────┘                                           │ │
│ [+ recipient]  ││ │  Date: ┌──────┐  Name: ┌──────────┐  Title: ┌──────────┐    │ │
│ ── SIGNING ──  ││ │        └──────┘        └──────────┘         └──────────┘    │ │
│ ◉ Sequential   ││ │  ...                                                        │ │
│ ○ Parallel     ││ │  page 12: ┌──────────┐ ┌──────────┐  (both parties' blocks) │ │
│ ○ Custom order ││ │            J.Doe sig    A.Khan sig                          │ │
│ ── FIELDS ──   ││ │  [thumbnails ▾]  [zoom][fit]                                │ │
│ drag onto doc: ││ └─────────────────────────────────────────────────────────────┘ │
│ ✍ Signature    ││  ⚠ Recipient 1 has no signature field yet. Auto-place? [Yes]    │ │
│ ✎ Initials     ││  Message to signers: [Please review and sign by Fri ____]      │ │
│ 📅 Date signed ││  Reminders: every [3] days, expire link after [14] days        │ │
│ 🔤 Text / Name ││  CC final copy to: [legal@acme.com] [+]                        │ │
│ ☑ Checkbox     ││  Order of operations preview:  1 J.Doe → 2 A.Khan → done       │ │
└────────────────┘└─────────────────────────────────────────────────────────────────┘
```

**Key components:** **Recipients panel** — add people (name, email, role: *signer* / *approver-before-signing* / *CC*; signing order; per-recipient auth level: none / email-OTP / SMS-OTP / ID-verification; "in person" option for kiosk signing); each recipient gets a color. **Field palette** — drag `Signature`, `Initials`, `Date signed`, `Name`, `Title`, `Text` (free / pre-filled), `Checkbox`, `Attachment-request`, `Stamp` onto pages; each placed field is assigned to a recipient, sized/moved (drag + arrow-key nudge), marked required/optional, optionally pre-filled. **Auto-place** — "place standard signature blocks for all signers on the last page" one-click. **Send settings** — message to signers, reminder cadence, link expiry, CC the executed copy, attach a cover note. **Preview** — see exactly what each recipient will see. **Validation** — every signer has ≥1 signature field; no overlapping fields; required fields make sense; warns on no-fields recipients.

**States:** editing · validation errors (can't send) · ready · sending (generating tokens, queuing emails — `ProgressTray`) · sent (status → `out_for_signature`; the Signatures tab on the contract takes over) · re-prepare (recall a sent envelope to add a signer or fix a field → re-send, audited) · template-of-fields (save a field layout to reuse on similar contracts).

**Edge cases:** the document changes after fields were placed (fields anchored to text vs absolute coords — re-validate, warn if pages shifted); a recipient with no email (generate an access link to share manually); bulk-send (the same contract template to many counterparties, each their own envelope — a table where you paste recipients); in-person signing (a "host" passes a device to the signer at a kiosk); signing on behalf (a delegate signs — recorded as such).

**RTL/Mobile:** the panels mirror; field overlay coords are document-space (unaffected by UI direction); preparing for signature is a desktop-class task — on mobile you can review and send a pre-prepared envelope but field placement is desktop-first. See Doc 12.

---

## Module 14 — Digital Signing Experience

**Purpose:** the ceremony. For internal signers (in-app) and external signers (the portal, Module 21). Calm, trustworthy, fast — borrows extra polish from Direction C per Doc 02.

**Layout** (`/sign/:token` for external; an in-app modal/route for internal — Viewer archetype, extra-polished):
```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  [Org logo]   You're signing: MSA — Acme Corp   ·  sent by J.Doe  ·  due Fri 5 PM   │
│  ┌─ progress rail ─────────────────────────────────────────────────────────────────┐│
│  │  ① Verify  ②• Review & sign  ③ Done           Fields remaining: 3              ││
│  └─────────────────────────────────────────────────────────────────────────────────┘│
│  ┌──────────────── DOCUMENT (large, paper-like; fields pulse where you act) ───────┐│
│  │   §1 ……………………………                                                              ││
│  │   §8 Limitation of Liability ……  ← (read; AI margin note available on hover)    ││
│  │   ...                                                                           ││
│  │   ┌──────────────┐  ← "Click to sign" (your color); a soft pulse draws the eye  ││
│  │   │  Sign here ▸ │                                                              ││
│  │   └──────────────┘   Date: [auto: 2026-05-12]   Title: [____]                   ││
│  │   ...                                                                           ││
│  │  [↓ next field]  [page 12/12]  [download a copy (watermarked draft)]            ││
│  └─────────────────────────────────────────────────────────────────────────────────┘│
│  Footer:  ☑ I agree to use electronic records and signatures (e-sign disclosure ▾)  │
│           [ Decline ▾ ]                                              [ Finish ▸ ]   │
└────────────────────────────────────────────────────────────────────────────────────┘

Adopt-signature modal:  [Type your name] (font-styled) | [Draw] (canvas/touch) | [Upload image]
                        Preview → "Adopt and sign" → applies to all your fields.

Done screen:  ✓ "You've signed."  [green VerifiedSeal]  "We'll email you the executed copy
              when everyone has signed."  [Download what I signed] [Return to {Org}]
```

**Key components:** identity step (OTP if required); e-sign consent (the legal disclosure, expandable, with consent recorded); the document with **field pulses** (the next required field gently glows; "next field" jump button); the **adopt-signature** flow (type / draw / upload, with a styled preview, applied to all the signer's fields at once); per-field date/name/title auto-fill; "download a copy" (watermarked while pending); **Finish** (records: the signature image, timestamp, IP, device fingerprint, geolocation if permitted, the hash of the document at the moment of signing, the consent record); decline (with a reason → notifies the sender); the **done** state (VerifiedSeal, "what happens next", download). Throughout: a "questions? contact {sender}" affordance; if collaboration is enabled, a "request changes / comment" path instead of forcing decline.

**States:** invalid/expired/revoked link · needs-identity-verification · ready-to-sign · in-progress (fields partly filled) · signed-by-you-waiting-others · declined · all-signed (executed) · expired-unsigned (sender re-sends or voids) · already-signed-by-you (revisiting the link shows your signed state, not the form) · accessibility mode (keyboard: Tab between fields, Enter to open the sign modal, full screen-reader narration of "you have 3 required fields", high-contrast).

**Edge cases:** signer on mobile with a touchscreen (drawing is great; otherwise typed) vs desktop with a mouse (typed is better); a signer who is also an approver (their approval step precedes their signing field); in-person/kiosk (host hands over device, signer's IP = host's, recorded as in-person); a signer who needs to add an attachment (a request-attachment field — upload before finishing); signing the same envelope on two devices (server-side lock — "you're already in this envelope on another device"); document so long the "agree" button is far below the fold (require scroll-to-end before "Finish" enables, configurable).

**RTL/Mobile:** the ceremony mirrors; the document renders in its own language (an Arabic contract reads RTL even for an English-UI signer); **mobile is a first-class target** — one-handed, big "Sign here", bottom-anchored Finish, OS keyboard for typed signature, touch for drawn; see Doc 12. The completion VerifiedSeal and "executed copy" email link are the brand-halo moment for external counterparties.

---

## Module 15 — Contract Lifecycle Timeline

**Purpose:** the chronological story of one contract — every state change, approval, signature, edit, comment, share, view, reminder, renewal — as a single, filterable, exportable timeline. This is partly the contract's Activity tab and partly a richer "story" view.

**Layout** (`/contracts/:id/activity` and a "Timeline" tab — Detail-archetype body):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ MSA — Acme Corp › Timeline           [Filter: all ▾] [Export ▾]   ◍───◍───◍───○───○ │
│  ┌ Today ──────────────────────────────────────────────────────────────────────────┐│
│  │ ● 14:02  J.Doe submitted for approval → workflow "Procurement standard"           ││
│  │ ● 09:11  AI re-ran analysis (v3) — risk: Medium (1 high, 2 med)        [view]    ││
│  ├ Yesterday ──────────────────────────────────────────────────────────────────────┤│
│  │ ● 16:40  A.Khan (Acme) viewed the shared draft (IP …, Muscat)         [details] ││
│  │ ● 11:22  M.Khan edited §8 Limitation of Liability  (v2 → v3)  [compare] [restore]││
│  │ ● 10:05  Comment by Legal on §9: "name PDPL explicitly" — resolved by M.Khan     ││
│  ├ 3 May ──────────────────────────────────────────────────────────────────────────┤│
│  │ ● OCR completed — created from Acme_MSA_signed.pdf (9 fields, 2 verified by J.Doe)││
│  │ ● Contract created · status: draft · owner J.Doe                                 ││
│  └──────────────────────────────────────────────────────────────────────────────────┘│
│   Filters: state changes · approvals · signatures · edits/versions · comments ·       │
│            shares & access · AI events · reminders · renewals · everything            │
│   Export: PDF "contract history report" · CSV · evidence package (signed, for legal). │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Key components:** the grouped `Timeline` (by day / "x ago"), each entry = icon + actor (avatar) + action + object + timestamp + optional detail expander (e.g., a version diff inline, an access record's IP/device/geo, a comment thread); the `LifecycleBar` pinned at the top showing where it is now; filters by event category; export (a human-readable PDF "contract history", CSV, or — for legal — a signed/sealed **evidence package** that includes the contract versions, the audit chain, the signature certificate, and access logs). This view is *read-only* — it's a record, not an action surface (actions live on the relevant tabs).

**States:** loading (skeleton) · normal · filtered · empty (brand-new contract: "history will appear here as things happen") · large (virtualized, server-paged, "load earlier"). The data is the per-contract slice of the immutable audit log (Module 18) plus activity events; entries that are audit-grade carry the hash chip and "verify".

**Edge cases:** events on the same second (stable secondary sort by sequence id); imported contracts ("migrated from {system} on {date}" as the first entry); legal hold ("retention extended due to legal hold by {admin} on {date}"); redactions for privacy (an admin can mark an entry's details as restricted — but never delete it; the redaction itself is logged).

**RTL/Mobile:** mirrors; the lifecycle bar reverses; on mobile it's a clean vertical feed with collapsible details, the filter is a bottom-sheet, export is in the `⋯` menu.

---

## Module 26 — Contract Expiry Tracking

**Purpose:** never be surprised by an end date. A dedicated lens over all contracts approaching expiry, plus the calendar view and the dashboard widgets that feed off it.

**Layout** (a saved-view + a calendar; lives under Contracts and Reports):
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Contracts › Expiring          [⊞ List][▥ Calendar]    [next 30d ▾] [my contracts ▾] │
│ ┌ buckets (chips): [Overdue 2] [≤7d 3] [≤30d 18] [≤60d 27] [≤90d 41] [no end date 6]│
│ ┌──────────────────────────────────────────────────────────────────────────────────┐│
│ │ Title             Owner  End date    In…   Renewal      Value   Action            ││
│ │ Lease — Tower 7   M.Khan 2026-06-01  20d   manual       $48k    [Renew] [Remind]  ││
│ │ MSA — Northstar   A.Sm.  2026-05-19   7d ⚠ auto (opt-out [Review opt-out] ⚠        ││
│ │                                       passed!)                                    ││
│ │ NDA — Globex      J.Doe  2026-05-09  -3d ⚠⚠ none → EXPIRED soon — [extend?] [let go]││
│ │ ...                                                                               ││
│ └──────────────────────────────────────────────────────────────────────────────────┘│
│  Calendar view: month grid, contracts dotted on their end/opt-out dates, colour by   │
│  bucket; click a day → that day's expirations; drag-to-reschedule a reminder.        │
│  Reminder rules (per tenant / per type): notify owner + watchers at 90/60/30/7 days   │
│  before end (and before any opt-out date), via in-app + email (+ push).               │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Behavior:** a nightly Celery beat job scans `active` contracts, computes days-to-end and days-to-any-key-date (opt-out, renewal-decision), creates/updates alerts, and feeds the dashboard "Expiring ≤30d" KPI + AI Recommendations ("3 auto-renew opt-outs in the next 30 days"). The list is just a pre-built saved view with these filters; the calendar is the Contracts "Calendar" view scoped to end dates. Bulk actions: "send renewal reminder", "start renewal", "mark do-not-renew", "snooze reminder".

**States:** healthy (nothing red) · attention (amber buckets populated) · alarm (overdue / passed-opt-out items at the top, red) · empty ("no contracts expiring soon — nice"). Per-row: a clear primary action depending on renewal type (Renew / Review opt-out / Extend / Let expire).

**Edge cases:** contracts with no end date ("evergreen" — a separate bucket, optionally surfaced for periodic review); contracts whose end date is "X days after signature" and they're not signed yet (not counted until signed); auto-renew where the opt-out window has *already passed* (loud warning — the system can't stop the renewal, but flags it); time zones (compute "today" per the contract's governing-law timezone or the tenant default).

**RTL/Mobile:** mirrors; the calendar is a swipeable month on mobile with day-tap → list; the buckets are scrollable chips. See Doc 12.

---

## Module 27 — Renewal Management

**Purpose:** turn an expiring contract into a renewed one with minimum fuss — clone, adjust, route as needed.

**Layout** (`/contracts/:id/renew` — Wizard archetype):
```
┌── stepper ──┐┌────────────────────── step body ─────────────────────────────────┐
│ ① Approach  ││ Renew "MSA — Acme Corp" (ends 2026-12-31)                          │
│ ○ Terms     ││  How do you want to renew?                                         │
│ ○ Parties   ││  ◉ Renew on same terms (just extend dates)                         │
│ ○ Approvals ││  ○ Renew with changes (open editor on a new version)               │
│ ○ Review    ││  ○ Renegotiate (start fresh from this as a base)                   │
│             ││  ○ Do not renew — send non-renewal notice (template) [pick template]│
│             ││  New term: [12 months ▾] → 2027-01-01 → 2027-12-31                 │
│             ││  Value change: [+5% CPI ▾] → $126,000   Other field changes ▾      │
│             ││  Re-run AI analysis on the renewed terms? ☑                         │
│             ││  Routing: ☑ requires re-approval (workflow: …)  ☑ requires re-sign  │
│             ││  (if neither: it just becomes active with new dates, logged)        │
│             ││  [‹ Back]                              [Save draft] [Continue ›]    │
└─────────────┘└───────────────────────────────────────────────────────────────────┘
```

**Behavior:** "renew on same terms" → clones the contract as a new version/period with updated dates (and optional value bump), links `renewed_by`/`renews`, optionally routes through a (usually lighter) approval and/or a re-sign, then becomes `active`; the old contract moves to a `superseded`/`expired` state with a link to its renewal. "With changes" → opens the editor on the new version. "Renegotiate" → the full creation flow with the old contract as the base. "Do not renew" → generates the non-renewal/termination notice from a template, routes it for signature/send, schedules the old contract to `terminated`/`expired` on the end date. The renewal chain is visible on every contract's "Related" card and in reports.

**States:** wizard in progress (autosaves a draft renewal) · awaiting approval/signature (the renewal is a normal contract in those flows) · completed (old → superseded, new → active, dashboards updated) · cancelled (no harm; the old contract still tracks its expiry).

**Edge cases:** auto-renew clauses (the system *reminds* and pre-fills a "confirm renewal" rather than requiring the full wizard — one click "yes, renew" creates the new period; the opt-out path generates the notice); multi-year frame agreements with annual renewals (each period is a child contract); price escalation formulas (CPI, fixed %, custom — applied automatically with a "review the number" prompt); renewing a contract whose template/clauses have newer versions ("update to current standard clauses?").

**RTL/Mobile:** wizard mirrors; on mobile, "renew on same terms" is a 2-tap flow (the auto-renew confirm card), the full wizard is doable but desktop-optimized. See Doc 12.

---

## Module 28 — Smart Search Experience

**Purpose:** find any contract, clause, template, or person — by keyword, by structured filter, or by *natural language* — fast. (IA layers summarized in Doc 04 §6; here's the UX.)

**Surfaces:**
- **⌘K command palette** (everywhere) — fuzzy across contracts (title/#/party), templates, clauses, people, settings pages, recent items, *and* runnable actions ("Create contract", "Switch workspace to…", "Toggle theme", "Switch to Arabic", "Go to audit log"). Results grouped, keyboard-navigable, recents pinned, sub-200ms.
- **`/search` advanced** — a full page:
```
┌──────────────────────────────────── content ──────────────────────────────────────┐
│ Search        [ leases expiring this year over $50k in Muscat________________ 🔎 ]  │
│  Interpreted as: Type=Lease · End date in 2026 · Value > $50,000 · Location=Muscat  │  ← AI parsed
│                  [edit as filters ▾]                                                │     the NL query
│  Filters: [Type▾][Party▾][Owner▾][Status▾][Value range][Date range][Tag▾][Risk▾]    │
│           [Clause contains: "indemnif*"][Custom field…]   [Save as view]            │
│  Results (38)  · sort [relevance ▾]                                                 │
│  ┌ Contracts (31) ───────────────────────────────────────────────────────────────┐ │
│  │ ● Lease — Tower 7 · ends 2026-06-01 · $48k · Muscat   "…matched: 'Muscat', value"│ │  ← shows WHY
│  │ ● Lease — Marina · ends 2026-09-15 · $72k · Muscat    "…matched clause: §2.1 …" │ │     it matched
│  │ ...                                                                            │ │
│  ├ Templates (3) ─ Clauses (2) ─ People (2) ──────────────────────────────────────┤ │
│  └─────────────────────────────────────────────────────────────────────────────────┘│
│  ⚡ AI: "Want a summary of these 31 leases? Total annual value $X. 4 auto-renew. [Go]"│  ← aurora
└────────────────────────────────────────────────────────────────────────────────────┘
```
- **Semantic search** — the NL query is parsed by the AI into structured filters *and* used for embedding-similarity over clauses/contracts (`pgvector`), so "find contracts with an unusual liability cap" works even without exact keywords; each result shows the matched clause snippet + a relevance/confidence indicator. Available in `/search` and in the AI Assistant.
- **In-document search** — inside the DocViewer/editor, find within the current contract (with next/prev, highlight).

**States:** empty (recent searches + saved views + tips) · typing (instant suggestions in ⌘K; debounced for `/search`) · results · no results ("nothing matched — try fewer filters / different words" + "search the full text of all contracts?" toggle) · slow query (skeleton + "searching 12,840 contracts…") · permission-limited ("showing only what you can access" note). Results are saveable as a view; the NL→filters translation is always shown and editable so it never feels like a black box.

**Edge cases:** Arabic queries (search the Arabic content; transliteration tolerance — "Muscat"/"مسقط"); typos (`pg_trgm` fuzzy + the AI's tolerance); huge corpora (server-side everything, ranked, paged); searching within a date range that spans a renewal chain (option: "treat renewal chains as one"); searching by a counterparty that appears under slightly different names (entity-resolution hint: "did you mean Acme Corp / Acme Corporation / ACME LLC — combine?").

**RTL/Mobile:** mirrors; Arabic query input renders RTL; on mobile, ⌘K becomes a full-screen search; `/search` filters go in a bottom-sheet; results are cards. See Doc 12.

---

## Module 29 — AI Assistant Panel

**Purpose:** a single, *labeled*, context-aware AI helper — available as the right-drawer tab everywhere and as a full workspace at `/intelligence/assistant`. It's the conversational front-end to everything the intelligence layer can do, and it always cites sources and shows confidence.

**Layout** (right-drawer tab; full-page is the same, wider):
```
┌──────── AI Assistant (aurora-tinted) ──────────┐
│ Context: MSA — Acme Corp  ▾ (or "all contracts")│  ← scoped; you pick the context
│ ───────────────────────────────────────────────│
│ You: What's risky about this contract?          │
│ ⚡ Assistant: Two things stand out —             │
│   1. §8 caps liability at $500k, below our      │
│      $1M standard, and has no carve-outs for    │
│      IP/confidentiality breaches.  [go to §8]   │
│      [insert our standard clause]               │
│   2. §12 auto-renews with a 60-day notice;      │
│      consider 30.  [edit §12]                   │
│   Confidence ●88% · source: §8, §12 · [explain] │
│ ───────────────────────────────────────────────│
│ Suggested:  • Summarize this contract           │
│             • Compare §8 to our library clause  │
│             • Draft a counter-proposal email    │
│             • Find similar contracts            │
│             • Translate the summary to Arabic   │
│ ───────────────────────────────────────────────│
│ [ Ask anything about this contract…       ] [↑] │
│  ⚠ AI can be wrong — verify before relying.     │
└─────────────────────────────────────────────────┘
```

**Capabilities (scoped to the current context — a contract, a folder, "all my contracts", a template, a clause):** summarize · explain a clause / a risk / a term · compare (this clause vs the library / vs another contract / two versions) · draft (a clause, an amendment, a cover email, a non-renewal notice, a negotiation counter) · review ("what's missing?", "what's unusual?", "is this favorable to us?") · extract (re-pull metadata, list obligations) · find (semantic search across contracts) · translate (EN↔AR, draft for human review) · answer questions ("when does this renew?", "who approved it?", "what's our total exposure on Acme contracts?"). Every answer: labeled "AI", confidence shown, sources linked (click → highlight in the document), actions concrete ("insert clause", "create reminder", "open editor at §8", "start a change request"), and a thumbs-up/down + "report" that feeds quality monitoring. The assistant never *takes* a consequential action silently — it proposes; the human confirms.

**States:** idle (context picker + suggested prompts) · thinking (aurora breathing + streaming tokens) · answered · low-confidence ("I'm not sure — here's my best guess, please verify") · out-of-scope ("I can't help with that") · no-AI-plan (upsell) · rate-limited (gentle "give me a moment"). History per context is kept (so you can revisit "what did the assistant say about this contract last week"); the user can clear it. Privacy: a clear statement of what the assistant can see (only what *you* can see, never another tenant), whether prompts are used to improve models (tenant-configurable, default off for enterprise), and a per-tenant on/off switch for the whole feature.

**Edge cases:** very large context ("all contracts" — it uses retrieval over embeddings + structured queries, not "read everything"); a question that needs data the user can't see (it refuses, citing access); a request to draft something legally sensitive (it drafts but stamps "AI draft — must be reviewed by counsel"); conflicting sources (it surfaces the conflict rather than picking one); the assistant in Arabic (full RTL chat, Arabic responses, Arabic clause drafting).

**RTL/Mobile:** the chat mirrors (messages right-aligned, input flips); Arabic responses render RTL within an EN UI too; on mobile the assistant is a bottom-sheet (swipe up) or a full screen; voice input is offered on mobile. See Doc 12.

---

> Continued in **[Doc 08 — Modules, Part 3: Admin & Trust](./08-modules-part3.md)** (audit logs, reports & analytics, notification center, external client portal, tenant management, billing, users & roles, activity timeline, settings).
