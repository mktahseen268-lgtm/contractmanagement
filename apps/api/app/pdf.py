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
    PageBreak,
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


def render_contract_pdf_bytes(*, contract, org_name: str, draft: bool, extra_story: list | None = None) -> bytes:
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
    if extra_story:
        story.extend(extra_story)

    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buf.getvalue()


def _fmt_dt(d) -> str:
    if not d:
        return "—"
    if isinstance(d, (dt.date, dt.datetime)):
        return d.strftime("%d %b %Y %H:%M UTC")
    return str(d)


def stamp_tabs_on_pdf(pdf_bytes: bytes, tabs: list[dict]) -> bytes:
    """Overlay signature/initials/date/text/checkbox tabs onto an existing PDF, in place. Each
    tab carries normalized coords (page 1-based; x,y,width,height as 0..1 fractions of the page;
    y is measured from the top to match the UI). Returns the new PDF bytes.

    Uses ReportLab to render a transparent overlay page that matches each base page's media-box,
    then merges via pypdf. Unknown pages are silently skipped. If pypdf isn't importable, returns
    the input unchanged (the appended Signatures page still records who signed)."""
    if not tabs:
        return pdf_bytes
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas as _canvas
    except Exception:  # noqa: BLE001
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    n_pages = len(reader.pages)
    by_page: dict[int, list[dict]] = {}
    for t in tabs:
        p = max(1, int(t.get("page", 1)))
        if p > n_pages:
            continue
        by_page.setdefault(p, []).append(t)
    if not by_page:
        return pdf_bytes

    writer = PdfWriter()
    for idx, base in enumerate(reader.pages, start=1):
        if idx not in by_page:
            writer.add_page(base)
            continue
        # build an overlay matching this page's size
        mb = base.mediabox
        try:
            pw = float(mb.width); ph = float(mb.height)
        except Exception:  # noqa: BLE001
            pw, ph = 595.0, 842.0  # A4 default points
        ov_buf = io.BytesIO()
        cv = _canvas.Canvas(ov_buf, pagesize=(pw, ph))
        for t in by_page[idx]:
            x = float(t.get("x", 0.5)) * pw
            y_from_top = float(t.get("y", 0.5)) * ph
            y = ph - y_from_top
            w = float(t.get("width", 0.25)) * pw
            h = float(t.get("height", 0.05)) * ph
            kind = t.get("kind", "signature")
            value = (t.get("value") or "").strip()
            # subtle field box
            cv.setStrokeColorRGB(0.24, 0.48, 0.98)
            cv.setLineWidth(0.6)
            cv.rect(x, y - h, w, h, stroke=1, fill=0)
            if kind == "signature":
                cv.setFont("Helvetica-BoldOblique", max(10, min(int(h * 0.7), 24)))
                cv.setFillColorRGB(0.06, 0.13, 0.26)
                cv.drawString(x + 2, y - h * 0.7, ("/s/ " + value)[:200] if value else "/s/")
            elif kind == "initials":
                cv.setFont("Helvetica-Bold", max(10, min(int(h * 0.7), 18)))
                cv.setFillColorRGB(0.06, 0.13, 0.26)
                cv.drawString(x + 2, y - h * 0.7, value[:8] if value else "—")
            elif kind == "date":
                cv.setFont("Helvetica", max(8, min(int(h * 0.6), 12)))
                cv.setFillColorRGB(0.06, 0.13, 0.26)
                cv.drawString(x + 2, y - h * 0.7, value or "—")
            elif kind == "checkbox":
                cv.setFont("Helvetica-Bold", max(8, min(int(h * 0.8), 16)))
                cv.setFillColorRGB(0.06, 0.13, 0.26)
                if value == "true":
                    cv.drawString(x + 2, y - h * 0.75, "✓")
            else:  # text
                cv.setFont("Helvetica", max(8, min(int(h * 0.6), 11)))
                cv.setFillColorRGB(0.06, 0.13, 0.26)
                cv.drawString(x + 2, y - h * 0.7, value[:120] if value else "")
        cv.showPage()
        cv.save()
        ov_buf.seek(0)
        overlay = PdfReader(ov_buf).pages[0]
        try:
            base.merge_page(overlay)
        except Exception:  # noqa: BLE001
            pass
        writer.add_page(base)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def render_signed_pdf_bytes(*, contract, org_name: str, signers: list[dict]) -> bytes:
    """The executed contract: the contract body (no DRAFT watermark) + a Signatures page."""
    st = _styles()
    sig_style = ParagraphStyle("CMSig", parent=st["body"], fontName="Helvetica-BoldOblique", fontSize=14, leading=18, textColor=_INK)
    extra: list = [PageBreak(), Paragraph("Signatures", st["h1"]), Spacer(1, 6),
                   Paragraph(f"This is the executed copy of {_inline(contract.title or 'the contract')} ({contract.reference_no}). The signatures below were captured electronically.", st["small"]),
                   Spacer(1, 14)]
    if not signers:
        extra.append(Paragraph("<i>(No signatures recorded.)</i>", st["body"]))
    for s in signers:
        extra.append(Paragraph(f"<b>{_inline(s.get('name') or '')}</b>" + (f" &nbsp;<font size=8 color='#7A8694'>{_inline(s.get('email') or '')}</font>" if s.get("email") else ""), st["body"]))
        extra.append(Paragraph("/s/  " + _inline(s.get("signed_name") or s.get("name") or ""), sig_style))
        extra.append(Paragraph(f"Signed {_fmt_dt(s.get('signed_at'))}" + (f" · IP {s['ip']}" if s.get("ip") else ""), st["small"]))
        extra.append(HRFlowable(width="60%", color=_LINE, spaceBefore=8, spaceAfter=14))
    extra.append(Spacer(1, 4))
    extra.append(Paragraph("A Certificate of Completion with the full signing audit trail is available separately.", st["small"]))
    return render_contract_pdf_bytes(contract=contract, org_name=org_name, draft=False, extra_story=extra)


def render_certificate_bytes(*, envelope, contract, org_name: str, recipients: list[dict], events: list[dict]) -> bytes:
    """A standalone Certificate of Completion — the signing audit trail."""
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
        canvas.drawCentredString(w / 2, 12 * mm, f"Certificate of Completion · Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm, title="Certificate of Completion")
    story: list = [
        Paragraph("Certificate of Completion", st["title"]),
        Spacer(1, 10),
    ]
    info = [
        ("Document", f"{contract.title or 'Contract'}  ({contract.reference_no})"),
        ("Envelope ID", envelope.id),
        ("Status", (envelope.status or "").replace("_", " ").title()),
        ("Document hash (SHA-256)", envelope.document_hash or "—"),
        ("Created", _fmt_dt(envelope.created_at)),
        ("Sent", _fmt_dt(envelope.sent_at)),
        ("Completed", _fmt_dt(envelope.completed_at)),
    ]
    rows = [[Paragraph(k.upper(), st["label"]), Paragraph(_inline(str(v)), st["val"])] for k, v in info]
    t = Table(rows, colWidths=[44 * mm, (A4[0] - 36 * mm - 44 * mm)])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, 0), (-1, -2), 0.4, _LINE)]))
    story.append(t)
    story.append(HRFlowable(width="100%", color=_LINE, spaceBefore=12, spaceAfter=12))

    story.append(Paragraph("Recipients", st["h2"]))
    rh = [[Paragraph("Name", st["label"]), Paragraph("Email", st["label"]), Paragraph("Role", st["label"]), Paragraph("Status", st["label"]), Paragraph("Signed / declined", st["label"]), Paragraph("IP", st["label"])]]
    for r in recipients:
        rh.append([
            Paragraph(_inline(r.get("name") or ""), st["val"]),
            Paragraph(_inline(r.get("email") or ""), st["val"]),
            Paragraph((r.get("kind") or "signer").title(), st["val"]),
            Paragraph((r.get("status") or "").replace("_", " ").title(), st["val"]),
            Paragraph(_fmt_dt(r.get("signed_at") or r.get("declined_at")) + (f"  ({_inline(r['declined_reason'])})" if r.get("declined_reason") else ""), st["small"]),
            Paragraph(_inline(r.get("ip") or "—"), st["small"]),
        ])
    rt = Table(rh, colWidths=[30 * mm, 38 * mm, 16 * mm, 18 * mm, 38 * mm, 22 * mm], repeatRows=1)
    rt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, 0), (-1, 0), 0.6, _LINE), ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F8FB"))]))
    story.append(rt)
    story.append(HRFlowable(width="100%", color=_LINE, spaceBefore=12, spaceAfter=12))

    story.append(Paragraph("History", st["h2"]))
    eh = [[Paragraph("When", st["label"]), Paragraph("Event", st["label"]), Paragraph("By", st["label"]), Paragraph("IP", st["label"])]]
    for e in events:
        eh.append([
            Paragraph(_fmt_dt(e.get("at")), st["small"]),
            Paragraph((e.get("event") or "").replace("_", " ").title(), st["val"]),
            Paragraph(_inline(e.get("recipient_name") or "—"), st["small"]),
            Paragraph(_inline(e.get("ip") or "—"), st["small"]),
        ])
    et = Table(eh, colWidths=[40 * mm, 40 * mm, 50 * mm, 22 * mm], repeatRows=1)
    et.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LINEBELOW", (0, 0), (-1, 0), 0.6, _LINE), ("LINEBELOW", (0, 1), (-1, -1), 0.3, _LINE), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F8FB"))]))
    story.append(et)
    story.append(Spacer(1, 14))
    story.append(Paragraph(f"Issued by {org_name} via the Contract Management platform. This certificate evidences the electronic signing of the document identified above.", st["small"]))

    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buf.getvalue()
