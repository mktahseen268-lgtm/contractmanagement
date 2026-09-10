"""Build .docx files that carry real tracked changes and comments.

Word is not available in CI, and a parser tested only against documents this codebase wrote is
a parser tested against its own assumptions. These helpers emit the actual OOXML Word produces
— `w:ins`, `w:del` with `w:delText`, a `word/comments.xml` part with `w:commentRangeStart` /
`w:commentReference` anchors — so `importer.py` is exercised against the structures it will
really meet.

Kept in the application package rather than the test tree because the same builders are useful
for a demo: "here is what comes back from a counterparty" is hard to show otherwise.
"""

from __future__ import annotations

import datetime as dt
import io
import shutil
import zipfile

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

_COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
_COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)


def _iso(at: dt.datetime) -> str:
    """Word writes `2026-08-20T11:30:00Z`. Appending "Z" to an already-offset isoformat
    yields `…+00:00Z`, which no parser accepts — drop the offset first."""
    if at.tzinfo is not None:
        at = at.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return at.replace(microsecond=0).isoformat() + "Z"


def _run(text: str, *, deleted: bool = False):
    run = etree.SubElement(etree.Element(f"{W}wrapper"), f"{W}r")
    node = etree.SubElement(run, f"{W}delText" if deleted else f"{W}t")
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return run


def add_tracked_insert(paragraph, text: str, *, author: str, at: dt.datetime,
                       change_id: int = 101) -> None:
    """Append text marked as a tracked insertion."""
    ins = etree.SubElement(paragraph._p, f"{W}ins")
    ins.set(f"{W}id", str(change_id))
    ins.set(f"{W}author", author)
    ins.set(f"{W}date", _iso(at))
    ins.append(_run(text))


def add_tracked_delete(paragraph, text: str, *, author: str, at: dt.datetime,
                       change_id: int = 201) -> None:
    """Append text marked as a tracked deletion.

    The text goes in `w:delText`, which is the detail that catches naive importers: a reader
    that only looks at `w:t` silently drops every deletion.
    """
    deletion = etree.SubElement(paragraph._p, f"{W}del")
    deletion.set(f"{W}id", str(change_id))
    deletion.set(f"{W}author", author)
    deletion.set(f"{W}date", _iso(at))
    deletion.append(_run(text, deleted=True))


def anchor_comment(paragraph, comment_id: int) -> None:
    """Wrap a paragraph in the range markers Word uses to attach a comment."""
    start = etree.Element(f"{W}commentRangeStart")
    start.set(f"{W}id", str(comment_id))
    paragraph._p.insert(0, start)

    end = etree.SubElement(paragraph._p, f"{W}commentRangeEnd")
    end.set(f"{W}id", str(comment_id))

    run = etree.SubElement(paragraph._p, f"{W}r")
    reference = etree.SubElement(run, f"{W}commentReference")
    reference.set(f"{W}id", str(comment_id))


def _comments_xml(comments: list[dict]) -> bytes:
    root = etree.Element(f"{W}comments", nsmap={"w": W_NS})
    for spec in comments:
        node = etree.SubElement(root, f"{W}comment")
        node.set(f"{W}id", str(spec["id"]))
        node.set(f"{W}author", spec.get("author", ""))
        node.set(f"{W}initials", spec.get("initials", ""))
        node.set(f"{W}date", _iso(spec.get("at") or dt.datetime.now(dt.timezone.utc)))
        paragraph = etree.SubElement(node, f"{W}p")
        run = etree.SubElement(paragraph, f"{W}r")
        text = etree.SubElement(run, f"{W}t")
        text.text = spec.get("text", "")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def attach_comments(docx_bytes: bytes, comments: list[dict]) -> bytes:
    """Add a `word/comments.xml` part (and its content-type + relationship) to a .docx.

    python-docx cannot author comments, so the package is rewritten directly. Every entry is
    copied across rather than patched in place because a zip cannot be edited in situ.
    """
    source = zipfile.ZipFile(io.BytesIO(docx_bytes))
    out = io.BytesIO()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            payload = source.read(item.filename)

            if item.filename == "[Content_Types].xml":
                root = etree.fromstring(payload)
                ns = root.nsmap.get(None)
                override = etree.SubElement(root, f"{{{ns}}}Override")
                override.set("PartName", "/word/comments.xml")
                override.set("ContentType", _COMMENTS_CONTENT_TYPE)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                         standalone=True)

            elif item.filename == "word/_rels/document.xml.rels":
                root = etree.fromstring(payload)
                ns = root.nsmap.get(None)
                relationship = etree.SubElement(root, f"{{{ns}}}Relationship")
                relationship.set("Id", "rIdComments900")
                relationship.set("Type", _COMMENTS_REL_TYPE)
                relationship.set("Target", "comments.xml")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                         standalone=True)

            target.writestr(item, payload)

        target.writestr("word/comments.xml", _comments_xml(comments))

    _ = shutil  # kept for callers that copy fixtures to disk
    return out.getvalue()


def counterparty_markup(*, title: str = "Master Services Agreement",
                        reference: str = "CM-2026-0001",
                        org_name: str = "MMBL") -> bytes:
    """A document shaped like one a counterparty sends back: numbered clauses, an insertion,
    a deletion, and two comments."""

    from . import export

    body = (
        "# Master Services Agreement\n"
        "1. Definitions\n"
        "1.1 In this Agreement the following terms apply.\n"
        "2. Term and Termination\n"
        "2.1 This Agreement commences on the Effective Date.\n"
        # Left unterminated on purpose: the tracked delete/insert below supply the notice
        # period, so the paragraph reads as a genuine edit rather than an appended fragment.
        "2.2 Either party may terminate on\n"
        "3. Limitation of Liability\n"
    )
    document = export.build_document(title=title, reference=reference, org_name=org_name,
                                     body=body)

    at = dt.datetime(2026, 8, 20, 11, 30, tzinfo=dt.timezone.utc)
    numbered = [p for p in document.paragraphs if p.text.strip()]

    termination = next(p for p in numbered if "may terminate on" in p.text)
    add_tracked_delete(termination, " 30 days", author="Counsel for Vendor", at=at,
                       change_id=201)
    add_tracked_insert(termination, " 90 days", author="Counsel for Vendor", at=at,
                       change_id=101)
    termination.add_run(" notice.")
    anchor_comment(termination, 1)

    liability = next(p for p in numbered if "Limitation of Liability" in p.text)
    anchor_comment(liability, 2)

    buf = io.BytesIO()
    document.save(buf)
    return attach_comments(buf.getvalue(), [
        {"id": 1, "author": "Counsel for Vendor", "initials": "CV",
         "text": "We need 90 days to wind down the integration.", "at": at},
        {"id": 2, "author": "Vendor CFO", "initials": "VC",
         "text": "Cap must be mutual.", "at": at},
    ])
