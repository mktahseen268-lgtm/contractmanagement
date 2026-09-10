# Accessibility — WCAG 2.1 AA

Phase 9, item 5. This document is the audit, the fixes, and — the part that matters most — the
list of what is **not** yet conformant. A statement that claims full conformance without the
exceptions is the one nobody can act on.

The in-product statement lives at `/accessibility` and is written for the reader, not the
auditor. This document is the working record behind it.

---

## 1. Why this is a requirement and not a nicety

Two reasons, and only one of them is the RFP.

The RFP asks for it. But the operative reason is §5.3 of the requirement: agreements are signed
by **branch customers**, not only by bank staff. That population includes people with low
vision, people who cannot use a mouse, people using a screen reader, and people who are not
digitally literate at all. A signing flow those people cannot complete does not degrade
gracefully — it produces a signature somebody else obtained on their behalf, which is a consent
defect, not a usability one.

That is why the accessibility work and the non-digitally-literate path (item 7) were built
together, and why the signing portal got the most attention.

---

## 2. What was fixed

### 2.1 Focus is visible everywhere (2.4.7)

The usual cause of an invisible focus ring is a reset. `:focus-visible` is now given an explicit
2px accent outline in `apps/web/src/app/globals.css`, applied globally rather than per
component — a component-by-component version always misses something, and the one it misses is
the one a keyboard user gets stuck on.

`:focus-visible` rather than `:focus` so the ring appears for keyboard navigation and not on
mouse clicks. That distinction is the reason people reach for `outline: none` in the first
place; using the right selector removes the motivation.

### 2.2 Skip link (2.4.1)

`apps/web/src/components/shell.tsx` — the first element in the tab order, before the sidebar.

It was initially placed after the sidebar, which made it decoration: a keyboard user still
tabbed through twenty navigation links to reach it. It was moved. `<main>` also carries
`tabIndex={-1}`, without which the browser scrolls to the target and leaves focus in the
navigation — the link appears to work and does nothing.

### 2.3 Landmarks and names

`<nav aria-label="Main">`, `<main id="main">`, `<header>`. Screen-reader users navigate by
landmark; an unlabelled second nav is announced as "navigation" with no way to tell which.

### 2.4 Colour is never the only signal (1.4.1)

The guided-actions panel (`components/guidance.tsx`) distinguishes critical / warning /
information by **icon and text as well as colour**, and each carries a visually-hidden severity
label. A red border alone conveys nothing to a reader with a colour-vision deficiency, and
nothing at all to a screen reader.

### 2.5 Progress and state are announced

`role="progressbar"` with `aria-valuenow` / `aria-valuemin` / `aria-valuemax` and a name on the
training bars; `aria-current="step"` on the stage tracker and the assisted-signing stepper;
`aria-pressed` on the knowledge-base filter toggles; `aria-expanded` on the help tooltip
trigger. Without `aria-current` a six-item stage tracker reads as six equal items and conveys
nothing.

### 2.6 Help reachable without a mouse (2.1.1)

The `HelpTip` trigger is a real `<button>` with an accessible name, opens on **focus** as well
as hover, closes on Escape, and links its panel with `aria-describedby`. Hover-only help is help
a keyboard user does not have.

### 2.7 Touch targets (2.5.5)

`@media (pointer: coarse)` enforces a 44px minimum on buttons and enlarges checkboxes and radios.
Scoped to coarse pointers because a dense desktop table legitimately cannot always give 44px,
while on a touch screen the constraint is physical.

### 2.8 Reduced motion (2.3.3)

`prefers-reduced-motion: reduce` collapses animations and transitions. Four lines, and
vestibular disorders are real.

### 2.9 Contrast — including the brand colour (1.4.3)

Two failures, both found by the automated scan and neither visible by eye.

**Secondary text.** `--color-text-3` was `#7a8694`, measuring **3.30:1** on `surface-3` and
3.71:1 on white — failing on every background it was used against, not marginally. Now
`#616b78`, which measures 4.81 / 5.03 / 5.27 / 5.41 across the four backgrounds it appears on.
Chosen to clear the bar with headroom on all four rather than to pass on the lightest and fail
in situ.

**The brand accent, which was the bigger one.** `#3e7bfa` measures **3.88:1** against the white
text sitting on it, so *every primary button in the product* failed. Darkening the default would
fix the default and nothing else: the accent is a tenant setting, and the next organisation to
pick a cheerful brand colour breaks it again with nobody noticing until an audit.

So `apps/web/src/lib/contrast.ts` derives the button background from whatever colour is
configured — left exactly as chosen when it already passes, darkened only as far as it must when
it does not. The colour as chosen is kept in `--color-accent-brand` for borders, icons and large
text, where 3:1 applies and the brand should still look like itself.

### 2.10 Labels are associated, not merely adjacent (1.3.1, 3.3.2)

The shared `Field` primitive rendered a bare `<label>` with no `htmlFor`. It looks identical and
means a screen reader announces **"edit text, blank"** for every field in the product. axe rated
it *critical* on the sign-in form, and because every form goes through `Field`, every form had
it.

Fixed in that one component rather than at a few hundred call sites: `Field` generates an id,
clones its child to attach it, and wires the hint and any error message with `aria-describedby`
so both are announced with the field instead of read out separately at the end of the form. It
also now takes an `error` prop that sets `aria-invalid` and renders the message in a
`role="alert"` — which closes what was listed here as open item 6.

### 2.11 Right-to-left (1.3.2)

Urdu sets `dir="rtl"` on the document, and directional icons use `rtl:rotate-180`. Logical
properties (`ps-`, `start-`) rather than `pl-`/`left-` where the layout is directional. A
translated interface that still reads left-to-right is harder to use than an English one,
because every eye movement is backwards.

### 2.12 Ownership of `dir` and `lang`

Two effects were setting `dir` — the app layout from the tenant locale, and the i18n provider
from the user's choice — and whichever ran last won. The i18n provider is now the single owner;
the tenant locale is the starting value via `useLocaleDefault`, which never overrides a choice
the person has made.

---

## 3. What is NOT conformant yet

This is the section that makes the rest usable. Each item names the criterion, the impact, and
what closing it needs.

| # | Criterion | Where | Impact | To close |
|---|---|---|---|---|
| 1 | **1.2.2 Captions** | Knowledge-base video | A deaf viewer gets nothing from a video with no captions. | The player falls back to the written guide, which covers the same ground — that is a mitigation, not conformance. Needs a caption track (WebVTT) uploaded with each video. **No video ships with captions today.** |
| 2 | **1.4.10 Reflow** | Audit log, analytics tables | Wide tables scroll horizontally below 320px CSS pixels. | Card-per-row layout at narrow widths. Done for the signing and approval surfaces (item 8); not for the reporting tables. |
| 3 | **4.1.2 Rich text editor** | Tiptap block editor | The editor is a `contenteditable` surface; its toolbar is reachable but the editing model is not fully announced. | Upstream. Tiptap's own accessibility is the ceiling here; the honest mitigation is that documents can also be produced from templates and DOCX without touching the editor. |
| 4 | **2.4.3 Focus order** | Command palette (⌘K) | Focus is trapped correctly on open, but the return target after close is the body rather than the trigger. | One `useRef` on the trigger. Small; not yet done. |

**Closed since the first pass:** contrast (§2.9) and error identification / label association
(§2.10). Both were listed here as open and both are now fixed and covered by the CI scan, which
is why they moved rather than being quietly deleted.

**Not a claim of conformance.** With items 1–4 open, the honest statement is *substantially
conformant with WCAG 2.1 AA, with the exceptions listed above*. An independent audit by a
qualified accessibility tester is a separate exercise and has not been done — automated checking
catches roughly a third of WCAG issues, which is a useful third and not a substitute.

---

## 4. Automated checking in CI

`axe-core` runs against the two journeys the RFP is scored on — the signed-in application and
the **public signing portal** — via Playwright in the `a11y` job of `.github/workflows/ci.yml`.

The scan asserts **zero violations at serious or critical impact**. Moderate and minor findings
are printed and do not fail the build, because the known-open items in §3 sit there and a job
that is red on day one gets disabled in week one. When an item in §3 closes, its rule moves up
into the failing set.

It currently reports **zero violations at any impact** on the scanned surfaces. That threshold
was not chosen to make the first run green — the first run failed on three pages, and the
contrast and label defects in §2.9 and §2.10 are what it found. Both were fixed rather than
excluded, which is the only version of this job worth having.

It also runs at a **phone viewport as well as a desktop one** (item 8). A layout that only
passes at 1280px has not been checked where it actually gets used.

**What it does not cover:** the signed-in application behind authentication. These are the
signed-out and error-state surfaces — sign-in, the signing portal with a dead link, the printable
guide. That is deliberate for the portal (an expired link is what a customer most often lands on)
and a genuine gap for the rest, which is covered by the manual testing in §5 until the Playwright
suite grows an authenticated fixture in Phase 10.

What automated scanning does **not** cover, and nobody should imply otherwise: whether the
reading order makes sense, whether an `alt` text is accurate rather than merely present, whether
a flow can actually be completed with a screen reader, or whether the wording can be understood
by the person it is aimed at. Those need a human, and for the signing portal specifically they
need a human from the population that will use it.

---

## 5. Testing done by hand

| Surface | Keyboard only | Screen reader | 200% zoom | Coarse pointer |
|---|---|---|---|---|
| Sign-in | ✅ | ✅ NVDA | ✅ | ✅ |
| Signing portal (standard) | ✅ | ✅ NVDA | ✅ | ✅ |
| Signing portal (assisted) | ✅ | ✅ NVDA | ✅ | ✅ designed for it |
| Printable guide | n/a | ✅ | ✅ | n/a |
| Dashboard | ✅ | 🟡 charts are decorative and hidden from the tree; the same figures are in the KPI text | ✅ | ✅ |
| Contract detail | ✅ | ✅ | ✅ | ✅ |
| Inbox / approvals | ✅ | ✅ | ✅ | ✅ |
| Help centre / training | ✅ | ✅ | ✅ | ✅ |
| Audit log | ✅ | 🟡 wide table | 🟡 horizontal scroll | 🟡 |
| Block editor | 🟡 see §3 item 3 | 🟡 | ✅ | 🟡 |

---

## 6. The statement in the product

`/accessibility` in the signed-in app, and linked from the signing portal footer. It states the
target, the known exceptions in plain language, and how to report a barrier — a statement with
no route to report a problem is a page nobody can act on.
