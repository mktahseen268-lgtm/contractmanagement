"""Render a contract to a PDF (ReportLab — pure Python, no system libs).

Scaffold-grade: a letterhead block (org name · contract title · ref# · type · parties · dates ·
value · governing law), then the document body with light markdown handling (#/##/### headings,
- bullets, **bold**, *italic*, `code`, paragraphs). A diagonal "DRAFT" watermark for non-final
statuses, plus a page header/footer with page numbers. The full product would render the
block-document faithfully and seal signed copies (docs/11, docs/19)."""

from __future__ import annotations

import datetime as dt
import html
import io
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_DRAFTISH = {"draft", "in_review", "changes_requested"}
_INK = colors.HexColor("#0F1729")
_INK2 = colors.HexColor("#475467")
_INK3 = colors.HexColor("#7A8694")
_LINE = colors.HexColor("#E6E8EB")


def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("CMBody", parent=ss["BodyText"], fontSize=10.5, leading=15, spaceAfter=8, textColor=_INK),
        "h1": ParagraphStyle("CMH1", parent=ss["Heading1"], fontSize=15, leading=19, spaceBefore=14, spaceAfter=8, textColor=_INK),
        "h2": ParagraphStyle("CMH2", parent=ss["Heading2"], fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=6, textColor=_INK),
        "h3": ParagraphStyle("CMH3", parent=ss["Heading3"], fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, textColor=_INK2),
        "title": ParagraphStyle("CMTitle", parent=ss["Title"], fontSize=18, leading=22, alignment=TA_CENTER, textColor=_INK),
        "small": ParagraphStyle("CMSmall", parent=ss["BodyText"], fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=_INK3),
        "label": ParagraphStyle("CMLabel", parent=ss["BodyText"], fontSize=8, leading=10, textColor=_INK3),
        "val": ParagraphStyle("CMVal", parent=ss["BodyText"], fontSize=9.5, leading=12, textColor=_INK),
        "aisum": ParagraphStyle("CMai", parent=ss["BodyText"], fontSize=10, leading=14, leftIndent=8, textColor=_INK2, spaceAfter=8),
    }


_INLINE_RE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__"), r"<b>\1</b>"),
    (re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])"), r"<i>\1</i>"),
    (re.compile(r"`(.+?)`"), r'<font face="Courier">\1</font>'),
]


def _inline(text: str) -> str:
    t = html.escape(text or "")
    for pat, rep in _INLINE_RE:
        t = pat.sub(rep, t)
    return t


def _body_flowables(md: str, st: dict) -> list:
    out: list = []
    bullets: list[str] = []

    def flush():
        nonlocal bullets
        if bullets:
            out.append(ListFlowable([ListItem(Paragraph(_inline(b), st["body"])) for b in bullets], bulletType="bullet", start="•", leftIndent=16))
            out.append(Spacer(1, 4))
            bullets = []

    for raw in (md or "").splitlines():
        s = raw.strip()
        if not s:
            flush(); continue
        if s.startswith("### "):
            flush(); out.append(Paragraph(_inline(s[4:]), st["h3"]))
        elif s.startswith("## "):
            flush(); out.append(Paragraph(_inline(s[3:]), st["h2"]))
        elif s.startswith("# "):
            flush(); out.append(Paragraph(_inline(s[2:]), st["h1"]))
        elif s.startswith(("- ", "* ", "• ")):
            bullets.append(s[2:])
        elif set(s) <= {"-", "_", "="} and len(s) >= 3:
            flush(); out.append(HRFlowable(width="100%", color=_LINE, spaceBefore=6, spaceAfter=8))
        else:
            flush(); out.append(Paragraph(_inline(s), st["body"]))
    flush()
    if not out:
        out.append(Paragraph("<i>(This contract has no document body yet.)</i>", st["body"]))
    return out


def _fmt_date(d) -> str:
    if not d:
        return "—"
    if isinstance(d, (dt.date, dt.datetime)):
        return d.strftime("%d %b %Y")
    return str(d)


def _fmt_money(value, currency) -> str:
    if not value:
        return "—"
    try:
        return f"{currency or ''} {float(value):,.0f}".strip()
    except (TypeError, ValueError):
        return f"{currency or ''} {value}".strip()


def is_draftish(status: str) -> bool:
    return status in _DRAFTISH


_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def contract_variables(contract, org_name: str) -> dict[str, str]:
    """The merge-field values available in a contract document ({{name}})."""
    return {
        "counterparty": contract.counterparty or "",
        "our_entity": org_name,
        "org": org_name,
        "us": org_name,
        "title": contract.title or "",
        "reference_no": contract.reference_no or "",
        "ref": contract.reference_no or "",
        "type": (contract.type or "other").replace("_", " ").title(),
        "value": _fmt_money(contract.value, contract.currency),
        "currency": contract.currency or "",
        "effective_date": _fmt_date(contract.effective_date),
        "end_date": _fmt_date(contract.end_date),
        "governing_law": contract.governing_law or "—",
        "renewal_type": (contract.renewal_type or "none").replace("_", " ").title(),
        "department": contract.department or "—",
        "status": (contract.status or "").replace("_", " ").title(),
    }


def substitute_variables(text: str, contract, org_name: str) -> str:
    if not text or "{{" not in text:
        return text or ""
    vals = contract_variables(contract, org_name)
    return _VAR_RE.sub(lambda m: vals.get(m.group(1).lower(), m.group(0)), text)


def render_contract_pdf_bytes(*, contract, org_name: str, draft: bool) -> bytes:
    st = _styles()
    buf = io.BytesIO()

    def _decorate(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_INK3)
        canvas.drawString(18 * mm, h - 12 * mm, org_name[:80])
        canvas.drawRightString(w - 18 * mm, h - 12 * mm, dt.datetime.now().strftime("Generated %d %b %Y %H:%M"))
        canvas.setStrokeColor(_LINE)
        canvas.line(18 * mm, h - 14 * mm, w - 18 * mm, h - 14 * mm)
        canvas.drawCentredString(w / 2, 12 * mm, f"Page {doc.page}")
        if draft:
            canvas.saveState()
            canvas.translate(w / 2, h / 2)
            canvas.rotate(45)
            canvas.setFont("Helvetica-Bold", 96)
            canvas.setFillColor(_LINE)
            canvas.drawCentredString(0, -24, "DRAFT")
            canvas.restoreState()
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm,
        title=(contract.title or "Contract"),
    )

    story: list = [
        Paragraph(_inline(contract.title or "Contract"), st["title"]),
        Spacer(1, 4),
        Paragraph(f"{contract.reference_no} · {(contract.type or 'other').upper()}" + ("  ·  DRAFT — NOT EXECUTED" if draft else ""), st["small"]),
        Spacer(1, 12),
    ]

    facts = [
        ("Parties", f"{org_name}  ·  {contract.counterparty or '—'}"),
        ("Type", (contract.type or "other").replace("_", " ").title()),
        ("Effective date", _fmt_date(contract.effective_date)),
        ("End date", _fmt_date(contract.end_date)),
        ("Value", _fmt_money(contract.value, contract.currency)),
        ("Renewal", (contract.renewal_type or "none").replace("_", " ").title()),
        ("Governing law", contract.governing_law or "—"),
        ("Status", (contract.status or "").replace("_", " ").title()),
    ]
    fact_rows = [[Paragraph(lbl.upper(), st["label"]), Paragraph(_inline(str(v)), st["val"])] for lbl, v in facts]
    ft = Table(fact_rows, colWidths=[34 * mm, (A4[0] - 36 * mm - 34 * mm)])
    ft.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _LINE),
    ]))
    story.append(ft)
    story.append(HRFlowable(width="100%", color=_LINE, spaceBefore=12, spaceAfter=12))

    summary = substitute_variables(getattr(contract, "ai_summary", "") or "", contract, org_name)
    if summary:
        story.append(Paragraph("<b>AI summary</b> &nbsp;<font size=8 color='#7A8694'>(machine-generated — verify before relying)</font>", st["body"]))
        story.append(Paragraph(_inline(summary), st["aisum"]))

    body = substitute_variables(getattr(contract, "body", "") or "", contract, org_name)
    story.extend(_body_flowables(body, st))

    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buf.getvalue()
