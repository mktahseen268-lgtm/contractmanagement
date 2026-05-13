# 11 — Contract Editor

The drafting/negotiation surface. The brief wants it to feel like **Notion + Google Docs + PandaDoc combined**: a block-based document editor with dynamic variables, clause insertion, an AI writing assistant, comments, suggestions (redlines), real-time collaboration, and version history. It's the same component used for **templates** ("template mode") and is the source-of-truth document that renders to the PDF used for signing.

---

## 1. The surface

```
┌─ top toolbar (minimal, contextual) ─────────────────────────────────────────────────────┐
│ ‹ Back  MSA — Acme Corp · draft · autosaved 12s ago    [Comments][Suggesting ▾][Share]  │
│                                                         [Version history]  [Submit ▸]   │
├─ formatting bar (appears on selection, like Notion/Docs) ───────────────────────────────┤
│  B I U S ¶ H1 H2 H3 • 1. ❝ </> 🔗 🅰 align ↔  | /clause  /variable  ✦AI  💬comment       │
├──────────────────────────────────── DOCUMENT ──────────────────────────┬─ right rail ──┤
│  (centered "paper" column, serif body, ~70ch line length)               │ [Variables]   │
│                                                                         │  {party_name} │
│  MASTER SERVICES AGREEMENT                                              │  {eff_date}   │
│                                                                         │  {value}      │
│  This Agreement is made between {our_entity ▾} ("Provider") and          │  {term}       │
│  {counterparty_name ▾} ("Client") effective {effective_date ▾}.          │  [+ new var]  │
│                                                                         │ ───────────── │
│  §1. Services.  ……………………………                                            │ [Clauses]     │
│                                                                         │  search lib…  │
│  §8. Limitation of Liability.  [≡ block menu]                            │  • Conf'ty    │
│      ████████ ← AI suggestion in margin: "below standard cap" [accept]   │  • Liability  │
│      ……………………………… 💬 2  ┃ M.Khan suggested: "$1,000,000" (insertion)     │  • Termin'n   │
│                                                                         │ ───────────── │
│  §12. Renewal.  ……  {renewal_term ▾} … unless cancelled {notice_days ▾}. │ [Comments] 3  │
│                                                                         │  §8: "raise…" │
│  + add block (type "/" for commands)                                    │  §9: "name…"  │
│                                                                         │ ───────────── │
│  ───── presence: ●M.Khan editing §8 · ●you · A.Smith viewing ─────       │ [AI ✦]        │
│                                                                         │  ask / draft… │
│                                                                         │ ───────────── │
│                                                                         │ [Versions]    │
│                                                                         │  v3 (now)     │
│                                                                         │  v2 · 2h ago  │
│                                                                         │  v1 · 3d ago  │
└─────────────────────────────────────────────────────────────────────────┴───────────────┘
```

---

## 2. Blocks

The document is a tree of typed blocks (stored as structured JSON — a portable, diffable, renderable format; think ProseMirror/Tiptap or Lexical or Slate doc model). Block types:

- **Text / heading (H1–H4) / paragraph** — rich inline marks (bold, italic, underline, strikethrough, code, link, highlight, super/subscript, comment-anchor, suggestion-anchor, **variable chip**).
- **List** — bullet, numbered (with legal-style nesting: 1 / 1.1 / 1.1.1, a / i / A), checklist.
- **Clause block** — a clause inserted from the library; rendered like a numbered section; carries a reference to the library clause + version (so "v2 available" can nudge); can be "locked" (template-enforced, not editable) or editable; the AI risk analysis maps these.
- **Section / numbered section** — auto-numbered headings (§1, §2, … with auto-renumber on reorder/insert/delete) — the backbone of a contract.
- **Table** — for pricing/fee schedules/SLAs; cells can hold variables; PandaDoc-style "pricing table" variant with auto-totals.
- **Signature block** — placeholder for where signatures will go (the actual fields are placed in Module 13, but the block reserves the space and labels the parties).
- **Variable/merge-field chip** — inline; displays the variable's name or, in preview, its value; click → edit definition or value; the right-rail Variables panel manages them.
- **Conditional block** — "show this section only if {renewal_type} == 'auto'" (used heavily in templates); shows a faint condition badge in edit mode.
- **Comment-only / instructional block** — a note to collaborators that won't render in the final PDF ("⚠ confirm the cap with finance before sending").
- **Page break, divider, callout, quote, image/logo, attachment-reference, code** — supporting blocks.
- **AI-draft block** — content the AI drafted, visually marked (aurora tint + "AI draft — review") until a human accepts it (which removes the marking and records the acceptance).

Each block: a hover "≡" menu (turn into / duplicate / move up-down / delete / comment / "ask AI about this" / "compare to library version" if a clause / "lock" if a template); drag handle to reorder; multi-block selection.

---

## 3. The "/" slash menu

Type `/` anywhere → a fuzzy command menu (Notion-style):
- **Blocks:** `/h1` `/h2` `/section` `/bullet` `/numbered` `/checklist` `/table` `/pricing-table` `/divider` `/callout` `/quote` `/page-break` `/image` `/signature-block`.
- **Insert:** `/clause` (search the clause library inline → insert, snapshotting the version; shows risk level + jurisdiction in the picker) · `/variable` (insert an existing merge field or define a new one) · `/template-section` (pull a section from another template) · `/date` `/today` `/our-entity` `/counterparty`.
- **AI commands (✦):** `/ai draft a [confidentiality] clause` · `/ai simplify this` (select first) · `/ai make this more favorable to us` · `/ai translate this section to Arabic` (creates the AR counterpart) · `/ai summarize this contract` · `/ai check for missing standard clauses` · `/ai explain this clause` · `/ai suggest a fallback for this clause` · `/ai rewrite in plain English`. All AI output lands as an **AI-draft block** (aurora-marked, "review") that a human must accept; nothing is silently committed; everything is source-aware and the assistant cites the library clauses it drew on.
- **Comment:** `/comment` (anchor a comment to the selection).

---

## 4. Variables / merge fields

Defined per document (or inherited from the template): name, type (text / long-text / number / currency / date / boolean / select(options) / party-reference / entity-reference / table), default value, required, help text, validation. Inserted as inline chips. In **edit mode** the chip shows the variable name; in **preview/PDF** it shows the resolved value (pulled from the contract's metadata — so editing the contract's "value" field updates every `{value}` chip). Unresolved required variables block "Submit for approval" / "Prepare for signature" (a lint panel lists them, click → jump to the chip). Variables are shared between the editor, the creation wizard (which collects their values), templates, and clauses.

---

## 5. Comments & suggestions (collaboration)

- **Comments:** anchor to a selection or a block; threaded; @mention (notifies + grants view access if needed); resolve/reopen; a right-rail Comments panel lists all (filter by open/resolved/mine/@me); each comment shows in the margin with a "💬 N" marker; internal-only (never visible to external collaborators unless explicitly shared); deleting a comment is audited.
- **Suggesting mode (redlines):** toggle "Suggesting" → edits become tracked **insertions/deletions/format-changes** (Google-Docs-style), attributed to the author, shown inline with strike/underline + a margin card ("M.Khan suggested: replace '$500,000' with '$1,000,000'") → the document owner (or anyone with edit rights) **accepts/rejects** each, or "accept all from {person}"; accepted suggestions become normal content; the whole redline history is in version history and the audit log. Essential for negotiation — internal *and* with external counterparties (an external collaborator with "suggest" permission redlines via the portal; their suggestions appear here for the internal owner to triage).

---

## 6. Real-time collaboration & presence

Multiple users edit/comment simultaneously; **presence** = avatars showing who's here and where their cursor/selection is ("●M.Khan editing §8"); changes sync live; conflict-free via a CRDT (Yjs-style) or OT layer on a **separate WS/collab service** (so collaboration load never touches the API tier — Doc 18). Offline edits queue and merge on reconnect. "Locked" template blocks can't be edited even in a live session. A "version checkpoint" can be taken manually (or auto, on submit / on send / every N minutes / on each accepted suggestion batch) — see versioning. Real-time collab can be plan-gated (it's a heavier feature).

---

## 7. Version history

Every checkpoint is an immutable `contract_version` (full block-document snapshot + metadata: who, when, label, summary-of-changes (auto-generated: "+2 clauses, edited §8, accepted 3 suggestions"), the contract metadata at that point). The right-rail Versions panel + a full-page version browser: view any version (read-only), **compare** any two (block-level diff: added/removed/changed sections, inline word-diff within changed blocks), **restore** a version (creates a new version that equals the old one — nothing is destroyed), name versions ("v1 sent to Acme", "post-legal-review"). The version used when a contract was *sent for signature* is locked and is what gets signed; the *signed* version (flattened PDF + hash) is the legal artifact. Templates version independently (Module 16); a contract built from template v1 keeps v1's snapshot even after the template moves to v2 ("template updated — review changes?").

---

## 8. Rendering & output

The block document renders to: (a) the in-editor "paper" view; (b) a faithful **PDF** (the legal artifact — proper pagination, numbered sections, headers/footers, the org's letterhead/branding, resolved variables, signature blocks; Arabic documents render RTL with correct shaping/numerals; generated by a Celery PDF job, cached, hash-stamped); (c) optionally **DOCX** (for offline review/legal redlining outside the system — re-importable, mapping tracked-changes back to suggestions where possible). Drafts get a "DRAFT — not executed" watermark on download; the signed copy gets the signatures + an audit-trail page + the Certificate of Completion.

---

## 9. States

- **Editing** (draft, you have edit rights) — full toolbar, autosave, presence.
- **Read-only** (you have view/comment but not edit, or the contract has left `draft`) — toolbar hidden, comments/suggestions allowed if your role permits, "request edit access".
- **Locked** (sent for signature / signed / active) — fully read-only document; the DocViewer shows the rendered/sealed PDF with overlays (signatures, comments, AI highlights), version selector, downloads.
- **Template mode** — adds: lock/unlock blocks, conditional-block config, variable schema management, "default clauses" attachment, "default workflow" / "custom field schema" / "language pair" config, publish/version controls; preview "as a contract with sample data".
- **Loading** (skeleton document) · **save-failed** (autosave retry, "your changes are safe locally") · **conflict** (rare with CRDT — a merge banner) · **offline** (edits queue, "reconnecting…") · **AI-thinking** (an AI command runs — the target area shows the aurora breathing, output streams in as an AI-draft block).

---

## 10. Accessibility & RTL & mobile

- **A11y:** full keyboard editing (all formatting via shortcuts; the slash menu and block menu are keyboard-navigable; comments/suggestions reachable by keyboard); screen-reader support for block structure, comments ("comment by M.Khan on §8"), and suggestions ("suggested insertion"); visible focus; respects reduced motion (the aurora becomes static).
- **RTL:** when the document language is Arabic, the document column is RTL (text, lists, section numbering, tables, the formatting bar's directional buttons); when the *contract* is Arabic but the *UI* is English, the document still renders RTL inside an LTR app chrome (and vice-versa); mixed EN/AR within a paragraph uses bidi isolation; the right rail and toolbars mirror with the UI direction; numerals per the tenant setting; "translate this section to Arabic" produces the RTL counterpart and links the EN↔AR documents.
- **Mobile:** the editor is **desktop-first** (serious drafting is a desktop task). On mobile/tablet you can: read the document (DocViewer), add/resolve comments, accept/reject suggestions, fill variable values, and do light text edits — but block-level restructuring, table editing, and template authoring are gated to larger screens with a "best on desktop" hint. The mobile reading view is excellent (it's the same DocViewer used in signing). See Doc 12.
