"""Multi-level clause numbering, as real Word numbering rather than typed-in text.

This is the part of DOCX export that actually matters for MMBL. A contract's clause numbers
are structural: legal drafting refers to "clause 7.2.1", amendments target it, and inserting a
clause must renumber everything below it. If the export writes "7.2.1" as literal text, the
document *looks* right and is broken — the counterparty edits it in Word, adds a clause, and
now the numbering is wrong everywhere and nobody notices until it is signed.

So numbering is emitted as a `w:numbering` definition with `w:numFmt`/`w:lvlText` per level,
and each paragraph carries a `w:numPr` reference. Word then owns the numbers, renumbers on
edit, and the numbering survives the round-trip because it is data, not characters.

The scheme is `decimal` at every level with cumulative text — 1, 1.1, 1.1.1 — which is what
Pakistani and English commercial agreements use. `%1` refers to level 1's counter, `%2` to
level 2's, so `%1.%2` renders as "7.2".
"""

from __future__ import annotations

from docx.oxml.ns import nsmap, qn
from docx.oxml.parser import OxmlElement

#: Word requires an abstract numbering id and a concrete num id; keeping them fixed and high
#: avoids colliding with anything a template already defines.
ABSTRACT_NUM_ID = 7100
NUM_ID = 7101

MAX_LEVELS = 6

#: Indentation per level, in twentieths of a point (1440 = one inch).
_INDENT_STEP = 420
_HANGING = 420


def _element(tag: str, **attrs: str):
    node = OxmlElement(tag)
    for key, value in attrs.items():
        node.set(qn(key.replace("_", ":")), value)
    return node


def _level(index: int):
    """One `w:lvl`: decimal, cumulative, hanging-indented."""
    lvl = _element("w:lvl", w_ilvl=str(index))
    lvl.append(_element("w:start", w_val="1"))
    lvl.append(_element("w:numFmt", w_val="decimal"))
    # Cumulative text: level 0 -> "%1.", level 1 -> "%1.%2", level 2 -> "%1.%2.%3", …
    if index == 0:
        text = "%1."
    else:
        text = ".".join(f"%{n + 1}" for n in range(index + 1))
    lvl.append(_element("w:lvlText", w_val=text))
    lvl.append(_element("w:lvlJc", w_val="left"))

    pPr = OxmlElement("w:pPr")
    left = _INDENT_STEP * (index + 1)
    pPr.append(_element("w:ind", w_left=str(left), w_hanging=str(_HANGING)))
    lvl.append(pPr)
    return lvl


def ensure_numbering(document) -> int:
    """Install the clause-numbering definition on a document. Returns the `numId` to reference.

    Idempotent: a document that already carries the definition is left alone, so exporting
    from a template that was itself exported does not accumulate duplicates.
    """
    numbering_part = _numbering_part(document)
    root = numbering_part.element

    for existing in root.findall(qn("w:num")):
        if existing.get(qn("w:numId")) == str(NUM_ID):
            return NUM_ID

    abstract = _element("w:abstractNum", w_abstractNumId=str(ABSTRACT_NUM_ID))
    abstract.append(_element("w:multiLevelType", w_val="multilevel"))
    for index in range(MAX_LEVELS):
        abstract.append(_level(index))

    num = _element("w:num", w_numId=str(NUM_ID))
    num.append(_element("w:abstractNumId", w_val=str(ABSTRACT_NUM_ID)))

    # Word is strict about ordering: every w:abstractNum must precede every w:num.
    last_abstract = root.findall(qn("w:abstractNum"))
    if last_abstract:
        last_abstract[-1].addnext(abstract)
    else:
        root.insert(0, abstract)
    root.append(num)
    return NUM_ID


def _numbering_part(document):
    """The document's numbering part, created if the template has none."""
    part = document.part
    try:
        return part.numbering_part
    except (KeyError, AttributeError, ValueError):
        pass

    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.parts.numbering import NumberingPart

    numbering = NumberingPart.new()
    part.relate_to(numbering, RT.NUMBERING)
    _ = PackURI  # imported for clarity about where the part lives in the package
    return numbering


def apply_number(paragraph, level: int, num_id: int = NUM_ID) -> None:
    """Attach `paragraph` to the clause-numbering sequence at `level` (0-based).

    The paragraph keeps whatever style it has; numbering is a separate property, which is why
    a numbered heading can still be a heading.
    """
    pPr = paragraph._p.get_or_add_pPr()
    existing = pPr.find(qn("w:numPr"))
    if existing is not None:
        pPr.remove(existing)
    numPr = OxmlElement("w:numPr")
    numPr.append(_element("w:ilvl", w_val=str(max(0, min(level, MAX_LEVELS - 1)))))
    numPr.append(_element("w:numId", w_val=str(num_id)))
    # w:numPr must sit early in w:pPr; Word tolerates more, but a strict validator does not.
    pPr.insert(0, numPr)


def read_number_level(paragraph) -> int | None:
    """The numbering level of a paragraph, or None when it is not numbered.

    Used on import to reconstruct the clause hierarchy without parsing digits out of text —
    which is the whole point of storing numbering as data.
    """
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is None:
        return None
    numPr = pPr.find(qn("w:numPr"))
    if numPr is None:
        return None
    ilvl = numPr.find(qn("w:ilvl"))
    if ilvl is None:
        return 0
    try:
        return int(ilvl.get(qn("w:val")) or 0)
    except (TypeError, ValueError):
        return 0


def numbering_fingerprint(document) -> list[dict]:
    """A structural summary of the numbering definitions.

    Used by the round-trip test. Comparing this rather than raw bytes is deliberate: a DOCX is
    a zip, and byte equality depends on entry order, compression and Word's `rsid` churn —
    none of which affect the document. What must survive is the numbering *structure*, and
    that is what this captures.
    """
    out: list[dict] = []
    try:
        root = _numbering_part(document).element
    except Exception:  # noqa: BLE001
        return out
    for abstract in root.findall(qn("w:abstractNum")):
        levels = []
        for lvl in abstract.findall(qn("w:lvl")):
            fmt = lvl.find(qn("w:numFmt"))
            text = lvl.find(qn("w:lvlText"))
            levels.append({
                "ilvl": lvl.get(qn("w:ilvl")),
                "fmt": fmt.get(qn("w:val")) if fmt is not None else None,
                "text": text.get(qn("w:val")) if text is not None else None,
            })
        out.append({"abstract_id": abstract.get(qn("w:abstractNumId")), "levels": levels})
    return out


__all__ = [
    "ABSTRACT_NUM_ID", "MAX_LEVELS", "NUM_ID", "apply_number", "ensure_numbering",
    "numbering_fingerprint", "nsmap", "read_number_level",
]
