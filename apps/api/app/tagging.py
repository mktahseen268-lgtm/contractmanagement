"""Smart signature tagging — find the signature blocks instead of making someone drag boxes.

RFP §4a "Smart execution": automated signature tagging, with manual drag-and-drop as an
override rather than the default. Today every tab is placed by hand, which does not survive a
re-render of the document and does not scale past a handful of agreements a week.

How it works: extract each text run from the rendered PDF **with its position** (pypdf's
`visitor_text` hands us the transformation matrix), match the runs against anchor phrases that
appear in real signature blocks, and place a tab relative to the anchor.

Why anchor text and not layout heuristics: a signature block is identified by what it *says* —
"For and on behalf of", "Authorised Signatory", "Signature", "Date" — and those phrases are
stable across MMBL's templates in a way that whitespace and line positions are not. A template
can also declare its own anchors, which is how a non-standard layout gets supported without
touching this file.

Coordinates follow the convention used everywhere in this codebase: fractions of page
width/height, with **y measured from the top**, so on-page maths matches the screen. `pdf.py`
flips to ReportLab's bottom-left origin when stamping.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("uvicorn.error")

#: Anchor phrases → the tab kind they imply. Ordered longest-first at match time so
#: "Authorised Signatory" wins over the bare "Signature" inside it.
ANCHOR_PATTERNS: list[tuple[str, str]] = [
    # --- signature ---
    (r"for and on behalf of", "signature"),
    (r"authoris?zed?\s+signator(?:y|ies)", "signature"),
    (r"signature\s+of\s+(?:the\s+)?(?:authoris?zed\s+)?signator(?:y|ies)", "signature"),
    (r"signed\s+for\s+and\s+on\s+behalf", "signature"),
    (r"signed\s+by", "signature"),
    (r"_{6,}\s*$", "signature"),          # a ruled signature line
    (r"\bsignature\b", "signature"),
    # --- supporting fields ---
    (r"\bdate\s*[:_]", "date"),
    (r"\bdated\b", "date"),
    (r"\bname\s*[:_]", "text"),
    (r"\bdesignation\s*[:_]", "text"),
    (r"\btitle\s*[:_]", "text"),
    (r"\bcnic\s*[:_]", "text"),
    (r"\bwitness\b", "signature"),
    (r"\binitials?\b", "initials"),
]

_COMPILED = [(re.compile(pattern, re.IGNORECASE), kind) for pattern, kind in ANCHOR_PATTERNS]

#: Default tab geometry, as a fraction of the page. A signature box needs to be big enough to
#: hold a drawn mark on a tablet; the supporting fields are single-line.
_SIZES = {
    "signature": (0.26, 0.055),
    "initials": (0.10, 0.045),
    "date": (0.16, 0.030),
    "text": (0.24, 0.030),
    "checkbox": (0.03, 0.025),
}


@dataclass
class Anchor:
    page: int          # 1-based
    x: float           # 0..1 from the left
    y: float           # 0..1 from the TOP
    text: str
    kind: str
    #: How confident we are that this really is a signature-block anchor (0..1). Surfaced in
    #: the UI so a reviewer can see which placements to check rather than trusting all of them.
    confidence: float = 0.6


@dataclass
class TagProposal:
    tabs: list[dict] = field(default_factory=list)
    anchors: list[Anchor] = field(default_factory=list)
    #: Set when nothing was found — the UI shows this instead of an empty result the user
    #: cannot interpret.
    note: str = ""


def _classify(text: str) -> tuple[str, float] | None:
    """The tab kind an anchor phrase implies, plus a confidence."""
    cleaned = " ".join(text.split())
    if not cleaned or len(cleaned) > 120:
        return None
    for pattern, kind in _COMPILED:
        if pattern.search(cleaned):
            # An explicit "for and on behalf of" is a far stronger signal than a stray
            # occurrence of the word "signature" in a clause about signature authority.
            strong = pattern.pattern.startswith(("for and", "authoris", "signed"))
            return kind, (0.9 if strong else 0.65)
    return None


def extract_anchors(pdf_bytes: bytes, *, extra_anchors: list[str] | None = None) -> list[Anchor]:
    """Positioned anchor phrases from a rendered PDF.

    Returns [] rather than raising when the PDF cannot be parsed — automatic tagging is a
    convenience, and failing it must never block sending a document for signature.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        log.warning("tagging: pypdf unavailable; automatic tagging disabled")
        return []

    extra = [(re.compile(re.escape(a), re.IGNORECASE), "signature") for a in (extra_anchors or [])]

    anchors: list[Anchor] = []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001
        log.warning("tagging: could not read the PDF")
        return []

    for index, page in enumerate(reader.pages, start=1):
        try:
            width = float(page.mediabox.width) or 1.0
            height = float(page.mediabox.height) or 1.0
        except Exception:  # noqa: BLE001
            width, height = 595.0, 842.0

        found: list[Anchor] = []

        def visitor(text, cm, tm, font_dict, font_size, _page=index, _w=width, _h=height, _out=found):  # noqa: ANN001, ARG001
            if not text or not text.strip():
                return
            try:
                x_pt, y_pt = float(tm[4]), float(tm[5])
            except Exception:  # noqa: BLE001
                return
            match = _classify(text)
            if match is None:
                for pattern, kind in extra:
                    if pattern.search(text):
                        match = (kind, 0.95)  # a template-declared anchor is authoritative
                        break
            if match is None:
                return
            kind, confidence = match
            _out.append(Anchor(
                page=_page,
                x=max(0.0, min(1.0, x_pt / _w)),
                # PDF y grows upward from the bottom; ours grows downward from the top.
                y=max(0.0, min(1.0, 1.0 - (y_pt / _h))),
                text=" ".join(text.split())[:120],
                kind=kind,
                confidence=confidence,
            ))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:  # noqa: BLE001
            log.warning("tagging: text extraction failed on page %s", index)
            continue
        anchors.extend(found)

    anchors.sort(key=lambda a: (a.page, a.y, a.x))
    return _dedupe(anchors)


def _dedupe(anchors: list[Anchor], *, tolerance: float = 0.012) -> list[Anchor]:
    """Collapse anchors that land on top of each other.

    A single visual line often arrives as several text runs ("Authorised", " ", "Signatory"),
    which would otherwise produce three overlapping tabs on one signature line.
    """
    kept: list[Anchor] = []
    for anchor in anchors:
        duplicate = next(
            (
                k for k in kept
                if k.page == anchor.page
                and abs(k.y - anchor.y) < tolerance
                and abs(k.x - anchor.x) < 0.25
                and k.kind == anchor.kind
            ),
            None,
        )
        if duplicate is None:
            kept.append(anchor)
        elif anchor.confidence > duplicate.confidence:
            duplicate.text, duplicate.confidence = anchor.text, anchor.confidence
    return kept


def propose_tabs(pdf_bytes: bytes, recipient_ids: list[str], *,
                 extra_anchors: list[str] | None = None) -> TagProposal:
    """Turn anchors into concrete tab specs, distributed across the signers.

    Signature anchors are dealt out in document order — first signature block to the first
    signer, and so on — because that is how a signature page is laid out and how the sequence
    of signatories is set. Supporting fields (date, name) attach to the signer whose signature
    block they sit nearest, which is what makes a two-column signature page come out right.
    """
    if not recipient_ids:
        return TagProposal(note="No signers on this envelope to assign tabs to.")

    anchors = extract_anchors(pdf_bytes, extra_anchors=extra_anchors)
    if not anchors:
        return TagProposal(
            anchors=[],
            note=(
                "No signature blocks were recognised in this document. Place the fields "
                "manually, or add an anchor phrase to the template."
            ),
        )

    signature_anchors = [a for a in anchors if a.kind == "signature"]
    other_anchors = [a for a in anchors if a.kind != "signature"]

    if not signature_anchors:
        return TagProposal(
            anchors=anchors,
            note=(
                "Found supporting fields but no signature line. Place the signature field "
                "manually — the rest can then be positioned around it."
            ),
        )

    tabs: list[dict] = []
    assignment: dict[int, str] = {}   # index into signature_anchors -> recipient id

    for index, anchor in enumerate(signature_anchors):
        recipient_id = recipient_ids[index % len(recipient_ids)]
        assignment[index] = recipient_id
        tabs.append(_tab(anchor, recipient_id, "signature", label="Signature"))

    for anchor in other_anchors:
        # Attach to the nearest signature block on the same page, falling back to the nearest
        # anywhere — a date on page 3 belongs to the signature on page 3, not page 1.
        same_page = [
            (i, a) for i, a in enumerate(signature_anchors) if a.page == anchor.page
        ] or list(enumerate(signature_anchors))

        # Distance must weigh the COLUMN more heavily than the row. A two-column signature
        # page — the standard MMBL shape — puts both parties' "Date:" at the same height, so
        # nearest-by-y alone hands both of them to whichever signer happens to come first.
        def _distance(pair, _anchor=anchor):
            candidate = pair[1]
            return ((candidate.x - _anchor.x) * 2.0) ** 2 + (candidate.y - _anchor.y) ** 2

        nearest_index, _ = min(same_page, key=_distance)
        tabs.append(_tab(
            anchor, assignment[nearest_index], anchor.kind,
            label=anchor.text.rstrip(":_ ").title()[:60] or anchor.kind.title(),
        ))

    return TagProposal(tabs=tabs, anchors=anchors)


def _tab(anchor: Anchor, recipient_id: str, kind: str, *, label: str) -> dict:
    width, height = _SIZES.get(kind, _SIZES["text"])
    # Place the field just to the right of the anchor text and nudged up so it sits ON the
    # line rather than under it — which is where a person signs.
    x = min(0.95 - width, anchor.x + 0.16)
    y = max(0.0, anchor.y - height * 0.35)
    return {
        "recipient_id": recipient_id,
        "kind": kind,
        "page": anchor.page,
        "x": round(x, 4),
        "y": round(y, 4),
        "width": round(width, 4),
        "height": round(height, 4),
        "required": kind in ("signature", "date"),
        "label": label,
        "anchor_text": anchor.text,
        "confidence": anchor.confidence,
    }
