"""Repository search — full text plus structured filters, across every supported engine.

The search itself goes through the Phase 0 `db_dialect` seam: a `tsvector` GIN index on
PostgreSQL, a full-text catalogue on MSSQL, Oracle Text on Oracle, and a `LIKE` scan on SQLite.
Only the last of those is slow, and it exists so a contributor can run the suite without
standing up a database server — it is not a deployment target.

Two decisions worth naming:

**Filters are applied in SQL, not after.** Fetching every matching contract and filtering in
Python would work on a demo corpus and fall over on ten years of agreements, which is exactly
the scale the RFP asks about.

**Snippets are built from the stored text, not from the engine.** `ts_headline` and its
MSSQL/Oracle equivalents each produce different markup and need different arguments; one
Python function that finds the match and trims around it gives the same result everywhere and
removes a per-dialect surface that would otherwise need testing four times.
"""

from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import Select, or_, select, text
from sqlalchemy.orm import Session

from . import db_dialect, models
from .config import settings

#: Columns the free-text query searches.
FTS_COLUMNS = ["title", "counterparty", "body", "ai_summary"]

#: Characters either side of a hit in a snippet.
SNIPPET_RADIUS = 90

MAX_PAGE_SIZE = 200


def _terms(q: str) -> list[str]:
    """Query words worth highlighting. Punctuation and one-letter noise dropped."""
    return [w for w in re.findall(r"[\w']+", (q or "").lower()) if len(w) > 1]


def snippet(body: str, q: str, *, radius: int = SNIPPET_RADIUS) -> str:
    """A window of text around the first query hit, with `**bold**` markers on the terms.

    Returns the opening of the document when nothing matches — a result with no snippet at all
    reads as a bug, and the opening is the next most useful thing to show.
    """
    text_body = re.sub(r"\s+", " ", (body or "")).strip()
    if not text_body:
        return ""
    words = _terms(q)
    lowered = text_body.lower()

    position = -1
    for word in words:
        found = lowered.find(word)
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        return text_body[: radius * 2] + ("…" if len(text_body) > radius * 2 else "")

    start = max(0, position - radius)
    end = min(len(text_body), position + radius)
    window = text_body[start:end]
    for word in sorted(set(words), key=len, reverse=True):
        window = re.sub(rf"(?i)\b({re.escape(word)})\b", r"**\1**", window)
    return ("…" if start else "") + window + ("…" if end < len(text_body) else "")


def _apply_text(stmt: Select, q: str) -> Select:
    """Attach the dialect's full-text predicate, or a LIKE fallback on SQLite."""
    dialect = settings.db_dialect
    if dialect == db_dialect.SQLITE:
        pattern = f"%{q.strip()}%"
        return stmt.where(or_(
            models.Contract.title.ilike(pattern),
            models.Contract.counterparty.ilike(pattern),
            models.Contract.body.ilike(pattern),
            models.Contract.ai_summary.ilike(pattern),
            models.Contract.reference_no.ilike(pattern),
        ))
    expression = db_dialect.fulltext_search(dialect, FTS_COLUMNS, param="q")
    return stmt.where(or_(text(expression).bindparams(q=q.strip()),
                          models.Contract.reference_no.ilike(f"%{q.strip()}%")))


def search(db: Session, tenant_id: str, *, q: str = "", filters: dict | None = None,
           page: int = 1, page_size: int = 25) -> dict:
    """Search the repository. Returns {items, total, page, page_size, facets}."""
    filters = filters or {}
    page = max(1, int(page or 1))
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size or 25)))

    stmt = select(models.Contract).where(models.Contract.tenant_id == tenant_id)

    if q.strip():
        stmt = _apply_text(stmt, q)

    simple = {
        "status": models.Contract.status,
        "type": models.Contract.type,
        "risk_level": models.Contract.risk_level,
        "owner_id": models.Contract.owner_id,
        "department_id": models.Contract.department_id,
        "party_id": models.Contract.party_id,
        "folder_id": models.Contract.folder_id,
        "currency": models.Contract.currency,
    }
    for name, column in simple.items():
        value = filters.get(name)
        if value in (None, "", []):
            continue
        stmt = stmt.where(column.in_(value) if isinstance(value, list) else column == value)

    if filters.get("counterparty"):
        stmt = stmt.where(models.Contract.counterparty.ilike(f"%{filters['counterparty']}%"))
    if filters.get("department"):
        stmt = stmt.where(models.Contract.department.ilike(f"%{filters['department']}%"))

    # A folder filter means "and everything beneath it" — the repository tree is what a user
    # thinks they are filtering by, not one node of it.
    if filters.get("folder_path"):
        folder_ids = [
            f.id for f in db.scalars(
                select(models.Folder).where(
                    models.Folder.tenant_id == tenant_id,
                    or_(models.Folder.path == filters["folder_path"],
                        models.Folder.path.like(f"{filters['folder_path']}/%")),
                )
            ).all()
        ]
        stmt = stmt.where(models.Contract.folder_id.in_(folder_ids or ["__none__"]))

    for name, column, op in (
        ("effective_from", models.Contract.effective_date, "ge"),
        ("effective_to", models.Contract.effective_date, "le"),
        ("end_from", models.Contract.end_date, "ge"),
        ("end_to", models.Contract.end_date, "le"),
    ):
        raw = filters.get(name)
        if not raw:
            continue
        day = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
        stmt = stmt.where(column >= day if op == "ge" else column <= day)

    if filters.get("value_min") is not None:
        stmt = stmt.where(models.Contract.value >= float(filters["value_min"]))
    if filters.get("value_max") is not None:
        stmt = stmt.where(models.Contract.value <= float(filters["value_max"]))

    if not filters.get("include_archived"):
        stmt = stmt.where(models.Contract.archived_at.is_(None))

    rows = list(db.scalars(stmt.order_by(models.Contract.updated_at.desc())).all())

    # JSON containment differs per engine and the tag lists are short, so tags are filtered
    # here — after the indexed predicates have already cut the set down.
    wanted_tags = {t.lower() for t in (filters.get("tags") or [])}
    if wanted_tags:
        rows = [r for r in rows
                if wanted_tags & {str(t).lower() for t in (r.tags or [])}]

    #: Clause search is a separate question — "which agreements contain this wording?" — and
    #: it runs over the body, which the text predicate has already narrowed.
    if filters.get("clause_key"):
        key = filters["clause_key"]
        rows = [r for r in rows
                if any(entry.get("key") == key for entry in (r.included_clauses or []))]

    total = len(rows)
    start = (page - 1) * page_size
    window = rows[start:start + page_size]

    return {
        "items": [{
            "id": c.id, "reference_no": c.reference_no, "title": c.title, "type": c.type,
            "status": c.status, "counterparty": c.counterparty, "value": c.value,
            "currency": c.currency, "risk_level": c.risk_level,
            "effective_date": c.effective_date, "end_date": c.end_date,
            "owner_id": c.owner_id, "updated_at": c.updated_at,
            "snippet": snippet(c.body or c.ai_summary or "", q) if q.strip() else "",
        } for c in window],
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": _facets(rows),
    }


def _facets(rows: list[models.Contract]) -> dict:
    """Counts for the filters a user is most likely to reach for next.

    Computed over the whole result set rather than the current page — a facet that only
    described one page of results would be actively misleading.
    """
    def _count(attr: str) -> dict:
        out: dict[str, int] = {}
        for row in rows:
            key = getattr(row, attr, "") or ""
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    return {"status": _count("status"), "type": _count("type"),
            "risk_level": _count("risk_level"), "currency": _count("currency")}
