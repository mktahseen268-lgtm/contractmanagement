"""Render a contract to .docx, preserving structure rather than appearance.

The RFP's most-cited supplemental requirement is a Word round-trip that keeps MMBL's
formatting and, critically, its **clause numbering**. External counterparties will not
negotiate inside a portal — they will send back a Word document — so the exported file has to
be a real working draft, not a printout.

What "preserving structure" means concretely:

  * clause numbers are Word numbering (see `numbering.py`), not typed digits, so inserting a
    clause renumbers the rest;
  * headings are heading styles, so the counterparty's navigation pane works and our importer
    can find them again;
  * tables are tables;
  * the reference number and title go in the header, which is what makes a returned scan or
    printout identifiable.

The contract body is the markdown-ish format the rest of the app uses (`#`/`##`/`###` for
headings, `-`/`*` for bullets, `1.`/`1.1` for clauses). Parsing is deliberately conservative:
anything unrecognised becomes a plain paragraph rather than being silently dropped.
"""

from __future__ import annotations

import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from . import numbering as numbering_mod

#: `1.` / `1.1` / `1.1.1` at the start of a line — an authored clause number. The depth of the
#: number tells us the level; the number itself is then DISCARDED, because Word regenerates it.
_CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*•]\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|\s*$")
#: `**bold**` and `*italic*`, the only inline marks the app's editor produces.
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def _add_runs(paragraph, text: str) -> None:
    """Split inline emphasis into runs. Word needs runs; a single run with asterisks in it
    would export the literal characters."""
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            paragraph.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            paragraph.add_run(part[1:-1]).italic = True
        else:
            paragraph.add_run(part)


def _header(document, *, title: str, reference: str, org_name: str) -> None:
    section = document.sections[0]
    header = section.header
    paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    paragraph.text = ""
    run = paragraph.add_run(f"{org_name} · {reference}" if reference else org_name)
    run.font.size = Pt(8)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    footer = section.footer
    fpara = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    fpara.text = ""
    frun = fpara.add_run(title[:120])
    frun.font.size = Pt(8)
    fpara.alignment = WD_ALIGN_PARAGRAPH.LEFT


def _flush_table(document, rows: list[list[str]]) -> None:
    if not rows:
        return
    width = max(len(r) for r in rows)
    table = document.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c in range(width):
            cell = table.cell(r, c)
            cell.text = ""
            _add_runs(cell.paragraphs[0], row[c] if c < len(row) else "")
            if r == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True


def build_document(*, title: str, reference: str, org_name: str, body: str) -> Document:
    """The contract as a `Document` object. Split from `render_bytes` so tests can inspect the
    structure without going through a file."""
    document = Document()
    num_id = numbering_mod.ensure_numbering(document)
    _header(document, title=title, reference=reference, org_name=org_name)

    # Only add a title when the body does not already open with one. Adding it
    # unconditionally duplicates the heading on every export -> import -> export cycle, which
    # is exactly the drift the round-trip test exists to catch.
    first_line = next((ln.strip() for ln in (body or "").splitlines() if ln.strip()), "")
    if not _HEADING_RE.match(first_line):
        heading = document.add_heading(title or "Agreement", level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    pending_table: list[list[str]] = []

    for raw in (body or "").splitlines():
        line = raw.rstrip()

        if _TABLE_ROW_RE.match(line):
            if _TABLE_SEP_RE.match(line):
                continue          # the |---|---| separator carries no content
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            pending_table.append(cells)
            continue
        if pending_table:
            _flush_table(document, pending_table)
            pending_table = []

        if not line.strip():
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            document.add_heading(heading_match.group(2).strip(), level=level)
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            paragraph = document.add_paragraph(style="List Bullet")
            _add_runs(paragraph, bullet_match.group(1).strip())
            continue

        clause_match = _CLAUSE_RE.match(line)
        if clause_match:
            depth = clause_match.group(1).count(".")
            paragraph = document.add_paragraph()
            # The authored number is dropped on purpose — Word owns the numbering now, so a
            # clause inserted by the counterparty renumbers everything below it.
            _add_runs(paragraph, clause_match.group(2).strip())
            numbering_mod.apply_number(paragraph, depth, num_id)
            continue

        _add_runs(document.add_paragraph(), line.strip())

    if pending_table:
        _flush_table(document, pending_table)

    return document


def render_bytes(*, title: str, reference: str, org_name: str, body: str) -> bytes:
    buf = io.BytesIO()
    build_document(title=title, reference=reference, org_name=org_name, body=body).save(buf)
    return buf.getvalue()


def render_contract(contract, org_name: str) -> bytes:
    return render_bytes(
        title=contract.title or "Agreement",
        reference=contract.reference_no or "",
        org_name=org_name,
        body=contract.body or "",
    )


def structure_fingerprint(document) -> dict:
    """A structural summary used by the round-trip fidelity test.

    Compares what must survive — heading levels, numbering levels, table shape, header and
    footer text — rather than raw bytes. A DOCX is a zip whose byte layout depends on entry
    order, compression and Word's `rsid` churn, none of which affect the document; a
    byte-equality test would be fragile and would fail for reasons nobody cares about.
    """
    paragraphs = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        paragraphs.append({
            "style": paragraph.style.name if paragraph.style is not None else "",
            "level": numbering_mod.read_number_level(paragraph),
            "text": text,
        })

    tables = [
        {"rows": len(t.rows), "cols": len(t.columns),
         "first_row": [c.text.strip() for c in t.rows[0].cells] if t.rows else []}
        for t in document.tables
    ]

    section = document.sections[0]
    return {
        "paragraphs": paragraphs,
        "tables": tables,
        "numbering": numbering_mod.numbering_fingerprint(document),
        "header": " ".join(p.text.strip() for p in section.header.paragraphs).strip(),
        "footer": " ".join(p.text.strip() for p in section.footer.paragraphs).strip(),
    }
