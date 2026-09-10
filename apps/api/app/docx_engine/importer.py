"""Read a returned .docx back in — including what the counterparty *changed* and *said*.

This is the half of the round-trip that earns its keep. External counterparties will not
negotiate inside a portal; they open the Word file, turn on track changes, mark it up, add
comments, and email it back. If we can only read the final text, all of that intent is lost
and someone has to diff two documents by eye.

So the importer extracts three things:

  body            the text, with clause structure reconstructed from Word's numbering data
                  rather than by parsing digits out of the text
  tracked changes every `w:ins` and `w:del`, with author and timestamp, mapped to revision
                  records the redline view can accept or reject
  comments        `word/comments.xml` plus the anchors in `document.xml`, so a comment lands
                  against the clause it was made on rather than floating at the end

`w:del` is the subtle one: deleted text lives in `w:delText`, *not* `w:t`. A naive reader that
only looks at `w:t` silently drops every deletion, and the import looks like it worked.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import zipfile
from dataclasses import dataclass, field

from docx import Document

from . import numbering as numbering_mod

log = logging.getLogger("uvicorn.error")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class TrackedChange:
    kind: str                 # "insert" | "delete"
    text: str
    author: str = ""
    at: dt.datetime | None = None
    paragraph_index: int = 0
    #: The paragraph's text with this change applied — context for the reviewer.
    context: str = ""


@dataclass
class DocxComment:
    comment_id: str
    author: str
    initials: str
    text: str
    at: dt.datetime | None = None
    #: The text the comment was anchored to, empty when the anchor could not be resolved.
    anchor_text: str = ""
    paragraph_index: int | None = None


@dataclass
class ImportResult:
    body: str = ""
    changes: list[TrackedChange] = field(default_factory=list)
    comments: list[DocxComment] = field(default_factory=list)
    #: Non-fatal problems worth telling the user about — a comment whose anchor was deleted,
    #: an unreadable date. Surfaced rather than swallowed.
    warnings: list[str] = field(default_factory=list)
    paragraphs: int = 0
    tables: int = 0

    @property
    def has_revisions(self) -> bool:
        return bool(self.changes)


def _parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(cleaned)
        return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _run_text(run_element) -> str:
    """All text in a run, from either `w:t` or `w:delText`.

    Deleted text lives in `w:delText`. Reading only `w:t` is the classic bug here: every
    deletion vanishes and the import appears to have succeeded.
    """
    parts = []
    for node in run_element.iter():
        if node.tag in (f"{W}t", f"{W}delText"):
            parts.append(node.text or "")
        elif node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
    return "".join(parts)


def _element_text(element) -> str:
    return "".join(
        node.text or ""
        for node in element.iter()
        if node.tag in (f"{W}t", f"{W}delText")
    )


def _paragraph_text(paragraph_element, *, include_deleted: bool = False) -> str:
    """The paragraph as it reads. Deletions are excluded by default — the accepted-changes
    view is the sensible default for "what does this document now say"."""
    out: list[str] = []
    for child in paragraph_element.iter():
        if child.tag == f"{W}t":
            out.append(child.text or "")
        elif child.tag == f"{W}delText" and include_deleted:
            out.append(child.text or "")
        elif child.tag == f"{W}tab":
            out.append("\t")
    return "".join(out)


# ---------------------------------------------------------------------------------------
# Tracked changes
# ---------------------------------------------------------------------------------------


def _extract_changes(document) -> list[TrackedChange]:
    changes: list[TrackedChange] = []
    for index, paragraph in enumerate(document.paragraphs):
        element = paragraph._p
        context = _paragraph_text(element)
        for node in element.iter():
            if node.tag == f"{W}ins":
                text = _element_text(node)
                if text.strip():
                    changes.append(TrackedChange(
                        kind="insert", text=text,
                        author=node.get(f"{W}author") or "",
                        at=_parse_date(node.get(f"{W}date")),
                        paragraph_index=index, context=context,
                    ))
            elif node.tag == f"{W}del":
                text = _element_text(node)
                if text.strip():
                    changes.append(TrackedChange(
                        kind="delete", text=text,
                        author=node.get(f"{W}author") or "",
                        at=_parse_date(node.get(f"{W}date")),
                        paragraph_index=index, context=context,
                    ))
    return changes


# ---------------------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------------------


def _extract_comments(raw: bytes, document) -> tuple[list[DocxComment], list[str]]:
    """Comments plus their anchors.

    `word/comments.xml` is not modelled by python-docx, so it is read from the package
    directly — which is also version-proof.
    """
    warnings: list[str] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        if "word/comments.xml" not in archive.namelist():
            return [], warnings
        payload = archive.read("word/comments.xml")
    except Exception:  # noqa: BLE001
        return [], ["The comments part could not be read; comments were not imported."]

    from lxml import etree

    try:
        root = etree.fromstring(payload)
    except Exception:  # noqa: BLE001
        return [], ["The comments part is malformed; comments were not imported."]

    anchors = _comment_anchors(document)

    comments: list[DocxComment] = []
    for node in root.findall(f"{W}comment"):
        comment_id = node.get(f"{W}id") or ""
        anchor = anchors.get(comment_id, {})
        comments.append(DocxComment(
            comment_id=comment_id,
            author=node.get(f"{W}author") or "",
            initials=node.get(f"{W}initials") or "",
            text=_element_text(node).strip(),
            at=_parse_date(node.get(f"{W}date")),
            anchor_text=anchor.get("text", ""),
            paragraph_index=anchor.get("paragraph_index"),
        ))
        if not anchor:
            warnings.append(
                f"Comment by {node.get(f'{W}author') or 'unknown'} could not be anchored — "
                "the text it referred to may have been deleted."
            )
    return comments, warnings


def _comment_anchors(document) -> dict[str, dict]:
    """Map comment id → the paragraph and text it was attached to.

    Word marks the span with `w:commentRangeStart` / `w:commentRangeEnd`. When only a
    reference exists (a comment on a point rather than a range), the paragraph is still a
    useful anchor, which is better than dropping the comment.
    """
    anchors: dict[str, dict] = {}
    for index, paragraph in enumerate(document.paragraphs):
        element = paragraph._p
        text = _paragraph_text(element)
        for node in element.iter():
            if node.tag in (f"{W}commentRangeStart", f"{W}commentReference"):
                comment_id = node.get(f"{W}id")
                if comment_id and comment_id not in anchors:
                    anchors[comment_id] = {"paragraph_index": index, "text": text}
    return anchors


# ---------------------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------------------


def _body_markdown(document) -> str:
    """Reconstruct the app's markdown body.

    Clause depth comes from Word's numbering data (`w:numPr/w:ilvl`), not from parsing digits
    out of the text — which is exactly why the exporter stores numbering as data. A document
    the counterparty renumbered by inserting a clause still imports with the right hierarchy.
    """
    lines: list[str] = []
    counters: list[int] = []

    for paragraph in document.paragraphs:
        text = _paragraph_text(paragraph._p).strip()
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        level = numbering_mod.read_number_level(paragraph)

        if not text:
            continue

        if level is not None and not style.startswith("List Bullet"):
            while len(counters) <= level:
                counters.append(0)
            counters = counters[: level + 1]
            counters[level] += 1
            number = ".".join(str(c) for c in counters[: level + 1])
            # Top-level clauses carry a trailing dot ("1."), deeper ones do not ("1.1") —
            # matching how they are authored, so a round trip does not churn the body text.
            lines.append(f"{number}. {text}" if level == 0 else f"{number} {text}")
            continue

        counters = []

        if style.startswith("Heading"):
            try:
                depth = int(style.split()[-1])
            except (ValueError, IndexError):
                depth = 1
            lines.append(f"{'#' * max(1, min(depth, 4))} {text}")
        elif style == "Title":
            lines.append(f"# {text}")
        elif style.startswith("List Bullet"):
            lines.append(f"- {text}")
        else:
            lines.append(text)
        lines.append("")

    # Tables, appended in document order after the prose. Word's object model does not
    # interleave them with paragraphs without walking the body XML, and for a contract body
    # the schedules sit at the end anyway.
    for table in document.tables:
        lines.append("")
        for row_index, row in enumerate(table.rows):
            cells = [c.text.strip().replace("|", "\\|") for c in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
            if row_index == 0:
                lines.append("|" + "|".join("---" for _ in cells) + "|")

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------------------


def import_docx(raw: bytes) -> ImportResult:
    """Parse a .docx into body text, tracked changes and comments.

    Raises ValueError on something that is not a readable Word document — the caller turns
    that into a 400 rather than a 500, because the usual cause is someone uploading a PDF.
    """
    try:
        document = Document(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            "That file could not be read as a Word document (.docx). If it is a .doc or a "
            "PDF, re-save it as .docx first."
        ) from e

    comments, warnings = _extract_comments(raw, document)
    result = ImportResult(
        body=_body_markdown(document),
        changes=_extract_changes(document),
        comments=comments,
        warnings=warnings,
        paragraphs=len(document.paragraphs),
        tables=len(document.tables),
    )
    return result


def summarise(result: ImportResult) -> dict:
    """A short human summary — what the UI shows after an upload."""
    inserts = sum(1 for c in result.changes if c.kind == "insert")
    deletes = sum(1 for c in result.changes if c.kind == "delete")
    authors = sorted({c.author for c in result.changes if c.author}
                     | {c.author for c in result.comments if c.author})
    return {
        "paragraphs": result.paragraphs,
        "tables": result.tables,
        "insertions": inserts,
        "deletions": deletes,
        "comments": len(result.comments),
        "authors": authors,
        "has_revisions": result.has_revisions,
        "warnings": result.warnings,
    }
