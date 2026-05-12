# 13 — Arabic & RTL

The brief flags this as "VERY IMPORTANT" — twice. This isn't a translated string file; it's a genuinely **bidirectional product**: mirrored layouts, Arabic typography, Hijri calendar support, mixed-script handling, and contracts that render in their own language regardless of the UI's. This is a real moat for MENA/GCC government and enterprise buyers.

---

## 1. Strategy

- **i18n from day one.** Every string in message catalogs (`next-intl` / `react-i18next` on the frontend; gettext-style catalogs on the backend for emails/PDFs). No hardcoded copy. Translations are *human-translated and reviewed* (machine draft only as a starting point); legal-adjacent copy reviewed by an Arabic-speaking lawyer.
- **Direction is a top-level state.** `<html lang="ar" dir="rtl">` when Arabic is active; the whole UI flips. Direction is set per **user preference** (overrides) → falling back to **tenant default** → falling back to browser. A persistent EN ⇄ ع toggle in the top bar and on auth screens; switching is instant (CSS vars + direction swap, no reload).
- **Content language ≠ UI language.** A user with an English UI can open an Arabic contract — and that contract's *document* renders RTL with Arabic typography *inside* the LTR app chrome. And vice-versa. The editor, DocViewer, and PDF renderer honor the **document's** language; the app shell honors the **user's** language. Templates and clauses are language-paired (EN ↔ AR linked); contracts can be EN, AR, or bilingual (two linked documents, or side-by-side columns).
- **Logical CSS only.** The entire codebase uses logical properties (`margin-inline-start`, `padding-block-end`, `inset-inline`, `border-start-start-radius`, `text-align: start/end`, `float: inline-start`) — never `left`/`right`/`margin-left`/etc. Tailwind config uses the logical-properties plugin so `ms-*`, `pe-*`, `start-*`, `end-*`, `text-start` are the only spacing/position utilities used; a lint rule flags physical-direction utilities. This means **one stylesheet works for both directions** — RTL is `dir="rtl"`, not a separate CSS build.

---

## 2. What mirrors (and what doesn't)

**Mirrors in RTL:**
- The whole shell: icon rail + contextual sidebar move to the **right** edge; the right drawer moves to the **left**; the top bar's content flips (search on the right, avatar on the left, etc.).
- Reading order: lists, menus, breadcrumbs (`Home › Contracts › MSA` becomes `MSA ‹ Contracts ‹ Home`), tab order, steppers/wizards (step 1 on the right, progressing left), the LifecycleBar (Draft on the right, Renew on the left), Kanban columns, the workflow canvas (flow reads right-to-left, arrows flip).
- Tables: column **order** reverses (the first logical column is on the right); but each cell's **content** renders in its own direction (a numeric/date/email/code cell stays LTR even in an RTL table — see mixed content).
- Directional **icons**: chevrons, arrows, back/forward, "send" (paper-plane), indent/outdent, "next/previous", progress arrows, the collapse-sidebar caret — mirrored via a `data-flip` utility (`scaleX(-1)`).
- Toasts: bottom-**left** in RTL (the corner opposite the primary content flow).
- Slide-in panels, sheets, drawers: enter from the mirrored side.
- Drag handles, resize grips: mirror.

**Does NOT mirror:**
- The **brand logo / wordmark** (unless the brand has an official Arabic lockup — then swap, don't flip).
- **Non-directional icons**: search, settings (gear), bell, user, check, close (×), plus, trash, calendar, lock, the AI spark, the Verified seal, file-type glyphs, status icons — these are symmetric or convention-fixed; flipping them looks broken.
- **The document content** of a contract — it renders in *its* language's direction, not the UI's.
- **Media** (photos, screenshots, charts' data — though chart **axes/legends** flip and read RTL).
- **Numbers** themselves (`12,840`, `$48k`, `2026-12-31`, version `v3`, contract `#C-2026-0481`), **code/JSON/hashes**, **emails/URLs**, and **Latin brand names** embedded in Arabic text — these stay LTR (via bidi isolation).

---

## 3. Arabic typography

- **Font:** `IBM Plex Sans Arabic` (or `Noto Sans Arabic` / `Cairo` — pick at brand lock; ensure it has the weights we use and good GCC-dialect glyph coverage). It must pair visually with the Latin UI font (`Inter`/`Geist`) so mixed lines look intentional. The contract **document body** in Arabic uses an Arabic serif-equivalent (e.g., `Noto Naskh Arabic` / `Amiri`) for the "printed legal" feel.
- **Size & leading:** Arabic glyphs have taller ascenders/descenders and more internal complexity — bump the **line-height** (~1.6–1.8 for body, more than Latin's 1.5) and slightly increase the **base size** (e.g., 15px UI base vs 14px for Latin) for legibility. Test at every size in the scale.
- **Never** italicize Arabic. **Never** letter-space (`letter-spacing`) Arabic — it breaks the cursive joins. **Never** use faux-bold; use a real bold weight from the font. **Never** ALL-CAPS (no concept of case in Arabic) — use weight/size for emphasis.
- **Numerals:** support both Western Arabic numerals (`0123456789`) and Eastern Arabic numerals (`٠١٢٣٤٥٦٧٨٩`); the choice is a tenant/user setting (default Western for data tables/IDs/currency where alignment matters; Eastern available for document body and where culturally preferred). Use `Intl.NumberFormat` with the chosen numbering system; tabular numerals for aligned columns regardless.
- **Justification:** Arabic text is traditionally justified with *kashida* (glyph elongation) rather than word-spacing — if the document renderer supports kashida justification, offer it; otherwise word-space justification is acceptable for contract bodies but never for short UI strings.
- **Punctuation:** Arabic comma `،`, semicolon `؛`, question mark `؟` — use them in Arabic copy; the i18n catalog handles this, but reviewers must catch Latin punctuation leaking into Arabic strings.

---

## 4. Mixed-script (bidi) handling

Real contracts and real UIs constantly mix Arabic with Latin (a counterparty named "Acme Corp LLC" in an Arabic sentence; an email address; a contract number; an amount in USD; a clause that quotes English defined terms):

- Wrap embedded foreign-direction runs in `<bdi>` (or `unicode-bidi: isolate`) so the bidi algorithm doesn't mangle the surrounding text — names, emails, URLs, codes, numbers, file names, and inline English-in-Arabic (and Arabic-in-English) all get isolated.
- Form **inputs** that hold mixed or Latin content (email, URL, contract #, numeric, code) are `dir="ltr"` (or `dir="auto"`) even in an RTL form, with their **label** start-aligned (i.e., on the right in RTL) — so you type the email left-to-right but the label sits where it belongs.
- The **editor** handles bidi at the paragraph level (a paragraph's base direction follows its dominant script, or an explicit per-block direction toggle) and isolates inline runs; pasted mixed content keeps its directionality; the cursor behaves correctly at script boundaries.
- **Search** is bidi-aware: an Arabic query searches Arabic content; transliteration tolerance helps ("Muscat" ⇄ "مسقط", "Acme" ⇄ "آكمي"); `pg_trgm` fuzzy works across both.

---

## 5. Dates, numbers, calendars, addresses

- **Calendars:** support **Gregorian** and **Hijri (Umm al-Qura)** — a tenant/user setting; date pickers and date displays can show one or both ("١٤٤٧/١١/١٥ هـ — 2026-05-12"); contract dates store as absolute (Gregorian, UTC-anchored) but display in the chosen calendar; "X days until expiry" math is unambiguous regardless of display calendar.
- **Date/number/currency formatting:** always via `Intl.*` with the active locale (`ar-OM`, `ar-SA`, `ar-AE`, `en-…`) — month names, weekday names, AM/PM, decimal/grouping separators, currency symbols and placement all locale-correct.
- **Week start:** Saturday/Sunday per locale; the business calendar (Doc 10) honors regional weekends (Fri–Sat in much of the GCC) and holidays for SLA math.
- **Names & addresses:** name order, honorifics, and address formats vary — keep these as free-form fields with locale-aware hints rather than rigid first/last/street/zip structures; the counterparty/signatory data model is flexible.
- **Phone/OTP:** country-code-aware; SMS OTP delivery via a provider with good GCC reach; OTP inputs stay LTR (digits).

---

## 6. Emails, PDFs, notifications, the external portal

- **Transactional emails** are sent in the recipient's language (their preference, or the tenant default, or — for external signers — the language the sender chose for that envelope); RTL email templates (tables with `dir="rtl"`, mirrored layout, Arabic web-safe fonts with fallbacks); the "Review/Sign" button and legal disclosures translated and reviewed.
- **Generated PDFs** (the contract, the certificate of completion, the audit/evidence package, reports): the renderer must do proper Arabic shaping (contextual letter forms, ligatures), correct RTL line layout, RTL tables, the chosen numeral system, and embed the Arabic font; an Arabic contract is a fully RTL document with letterhead, page numbers ("صفحة ٢ من ١٢"), and signature blocks all mirrored — this is non-negotiable for it to be a usable legal artifact.
- **The external client portal** (Module 21) offers EN/ع and renders the contract in *its* language; a Saudi vendor signing a contract drafted in Arabic gets a fully RTL, Arabic-typography, Hijri-date-aware, Eastern-numeral (if set) signing experience on their phone — and that polish is exactly what wins the regional enterprise/government deal.
- **AI** in Arabic: the assistant chats in Arabic (RTL chat bubbles), summarizes in Arabic, drafts Arabic clauses (stamped "AI draft — review by counsel"), and translates EN↔AR (draft for human review); OCR handles Arabic scans (with the preprocessing/reading-order care from Doc 09); confidence may be lower for Arabic — surfaced honestly.

---

## 7. Testing & QA

- **Every component, every state, in both directions** in Storybook (LTR/RTL × light/dark — Doc 03 §7.4); visual regression tests run both.
- A **pseudo-localization** mode (expand strings ~40%, add accents, force RTL) catches truncation, hardcoded strings, and physical-direction CSS in CI before real translations land.
- **Native Arabic-speaker review** of the actual UI (not just the strings) — flow, terminology (contract-law terms have established Arabic equivalents that matter to lawyers), and "does this feel like a product built *for* us, not *translated for* us."
- **Bidi torture tests**: strings and documents mixing Arabic, English, numbers, emails, URLs, and dates in one line/paragraph — verify nothing reorders wrongly.
- **PDF rendering tests** on real Arabic and bilingual contracts — shaping, justification, tables, page numbers, signature blocks.
- **Lint/CI gates**: no physical-direction CSS utilities; no hardcoded user-facing strings; every new string has both `en` and `ar` entries (CI fails on missing `ar`).
- **Accessibility in Arabic**: screen readers (VoiceOver/TalkBack/NVDA) announce Arabic correctly; focus order follows RTL; the `lang` attribute is set per content language so the SR uses the right voice for mixed content.

---

## 8. Why this is worth the effort

GCC governments, ministries, large regional enterprises, and law firms increasingly *require* genuine Arabic support, Hijri-aware processes, and data residency — and most Western CLM incumbents treat Arabic as an afterthought (a half-translated UI, no Hijri, broken bidi, ugly Arabic PDFs). A product that gets this *right* — mirrored, beautifully typeset, Hijri-capable, bilingual contracts, Arabic OCR — isn't just "localized," it's **differentiated** in a market the incumbents under-serve. It's a sales weapon. Build it in from the start (retrofitting RTL into a left-hardcoded codebase is brutal); the cost is mostly discipline (logical CSS, i18n catalogs, both-direction Storybook) plus the genuinely hard bits (Arabic PDF rendering, OCR quality, Hijri math, native review).
