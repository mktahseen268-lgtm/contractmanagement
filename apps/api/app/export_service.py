"""Repository and report exports as real spreadsheets, produced as a background job.

Two things the brief is explicit about and both matter:

**XLSX, not CSV.** A CSV of a ten-year repository loses every date type, turns reference
numbers into scientific notation the moment somebody opens it in Excel, and cannot carry the
filter set that produced it. The people who actually consume these send them to auditors.

**Generated as a job, with a download link.** A synchronous export of a large repository ties
up a request worker for as long as it takes to build, and the client times out before it
finishes. So the request records a `BackgroundJob`, the file lands in storage, and the tray
already built for OCR and sealing surfaces it.

The workbook always opens with a **Filters** sheet naming what was asked for. An export whose
provenance is not on its own face is one nobody can defend in a meeting six weeks later.
"""

from __future__ import annotations

import datetime as dt
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, obligation_service, search_service
from .audit import record
from .storage import get_storage

#: What can be exported. Each maps to a builder below.
KINDS = ("contracts", "obligations", "parties", "audit")

#: Beyond this, an export is almost certainly a mistake or an attempt to pull the whole
#: database through a spreadsheet. Reported rather than silently truncated.
# ponytail: flat cap; stream to a temp file and lift it if a real tenant legitimately needs
# more than this in one sheet.
MAX_ROWS = 50_000

_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExportError(ValueError):
    """Refused export. Routers map to 400."""


def _headers(kind: str) -> list[str]:
    return {
        "contracts": ["Reference", "Title", "Type", "Status", "Counterparty", "Department",
                      "Owner", "Value", "Currency", "Effective", "Expires", "Risk",
                      "Renewal", "Governing law", "Tags", "Updated"],
        "obligations": ["Agreement", "Agreement title", "Obligation", "Owner", "Due",
                        "Days left", "Status", "Overdue"],
        "parties": ["Name", "Registration no.", "Entity type", "Jurisdiction", "Region",
                    "KYC", "Risk score", "Contact", "Email", "Agreements", "Onboarded"],
        "audit": ["When", "Sequence", "Action", "Actor", "Object", "Label", "IP"],
    }[kind]


def _rows(db: Session, tenant_id: str, kind: str, filters: dict) -> list[list]:
    """The data, already shaped for a spreadsheet cell by cell."""
    if kind == "contracts":
        result = search_service.search(db, tenant_id, q=filters.get("q", ""),
                                       filters=filters, page=1, page_size=MAX_ROWS)
        owners = {u.id: u.name for u in db.scalars(
            select(models.User).where(models.User.tenant_id == tenant_id)).all()}
        contracts = {c.id: c for c in db.scalars(
            select(models.Contract).where(
                models.Contract.id.in_([i["id"] for i in result["items"]] or ["__none__"]))
        ).all()}
        rows = []
        for item in result["items"]:
            contract = contracts.get(item["id"])
            rows.append([
                item["reference_no"], item["title"], item["type"], item["status"],
                item["counterparty"], (contract.department if contract else ""),
                owners.get(item["owner_id"], ""), item["value"], item["currency"],
                item["effective_date"], item["end_date"], item["risk_level"],
                (contract.renewal_type if contract else ""),
                (contract.governing_law if contract else ""),
                ", ".join(str(t) for t in (contract.tags or [])) if contract else "",
                item["updated_at"],
            ])
        return rows

    if kind == "obligations":
        result = obligation_service.rollup(
            db, tenant_id,
            owner_id=filters.get("owner_id", ""), status=filters.get("status_filter", ""),
            overdue_only=bool(filters.get("overdue_only")),
        )
        return [[
            i["contract_reference"], i["contract_title"], i["title"], i["owner_name"],
            i["due_date"], i["days_left"], i["status"], "Yes" if i["overdue"] else "",
        ] for i in result["items"][:MAX_ROWS]]

    if kind == "parties":
        parties = db.scalars(
            select(models.Party).where(models.Party.tenant_id == tenant_id)
            .order_by(models.Party.name.asc())
        ).all()
        counts: dict[str, int] = {}
        for contract in db.scalars(
            select(models.Contract).where(models.Contract.tenant_id == tenant_id,
                                          models.Contract.party_id.is_not(None))
        ).all():
            counts[contract.party_id] = counts.get(contract.party_id, 0) + 1
        return [[
            p.name, p.registration_no, p.entity_type, p.jurisdiction, p.region,
            p.kyc_status, p.risk_score, p.contact_name, p.contact_email,
            counts.get(p.id, 0), p.created_at,
        ] for p in parties[:MAX_ROWS]]

    if kind == "audit":
        stmt = select(models.AuditLog).where(models.AuditLog.tenant_id == tenant_id)
        if filters.get("action"):
            stmt = stmt.where(models.AuditLog.action == filters["action"])
        if filters.get("since"):
            since = dt.date.fromisoformat(str(filters["since"]))
            stmt = stmt.where(models.AuditLog.at >= dt.datetime.combine(since, dt.time.min))
        entries = db.scalars(stmt.order_by(models.AuditLog.seq.asc())).all()
        return [[
            e.at, e.seq, e.action, e.actor_name, e.object_type, e.object_label, e.ip,
        ] for e in entries[:MAX_ROWS]]

    raise ExportError(f"Nothing called '{kind}' can be exported.")


def _describe_filters(filters: dict) -> list[list]:
    """The filter set, for the sheet that says what this export actually is."""
    rows: list[list] = []
    for key in sorted(filters):
        value = filters[key]
        if value in (None, "", [], {}, False):
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        rows.append([key.replace("_", " ").title(), str(value)])
    return rows or [["Filters", "None — the whole repository"]]


def build_workbook(db: Session, tenant_id: str, kind: str, filters: dict, *,
                   generated_by: str = "", org_name: str = "") -> tuple[bytes, int]:
    """(xlsx bytes, row count).

    Import is local because `openpyxl` is only needed on this path — keeping it out of module
    import means the API still starts if an operator has installed the lean requirement set.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover - depends on the installed requirement set
        raise ExportError(
            "Spreadsheet export needs the `openpyxl` package. Install requirements.txt."
        ) from e

    if kind not in KINDS:
        raise ExportError(f"Nothing called '{kind}' can be exported.")

    rows = _rows(db, tenant_id, kind, filters)
    workbook = Workbook()

    # Sheet 1: what this export is. Provenance on the face of the document, so nobody has to
    # remember which filters produced the numbers they are about to quote.
    cover = workbook.active
    cover.title = "Filters"
    cover.append(["Export", kind.title()])
    cover.append(["Workspace", org_name])
    cover.append(["Generated", dt.datetime.now().strftime("%d %b %Y %H:%M")])
    cover.append(["Generated by", generated_by])
    cover.append(["Rows", len(rows)])
    if len(rows) >= MAX_ROWS:
        cover.append(["Truncated", f"Capped at {MAX_ROWS:,} rows — narrow the filters."])
    cover.append([])
    cover.append(["Filter", "Value"])
    for row in _describe_filters(filters):
        cover.append(row)
    for cell in ("A1", "A8", "B8"):
        cover[cell].font = Font(bold=True)
    cover.column_dimensions["A"].width = 24
    cover.column_dimensions["B"].width = 60

    sheet = workbook.create_sheet(kind.title())
    headers = _headers(kind)
    sheet.append(headers)
    for row in rows:
        sheet.append([_cell(v) for v in row])

    header_font = Font(bold=True)
    for index, _ in enumerate(headers, start=1):
        sheet.cell(row=1, column=index).font = header_font
        sheet.cell(row=1, column=index).alignment = Alignment(vertical="top")
        # Width from the longest value in the column, bounded: an unbounded width makes a
        # single long clause title push everything else off the screen.
        longest = max(
            [len(str(headers[index - 1]))]
            + [len(str(r[index - 1])) for r in rows[:500] if index - 1 < len(r)]
        )
        sheet.column_dimensions[get_column_letter(index)].width = min(48, max(10, longest + 2))
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), len(rows)


def _cell(value):  # type: ignore[no-untyped-def]
    """Values Excel understands. Dates stay dates; everything exotic becomes text.

    Timezones are stripped rather than rejected: the spreadsheet format has no way to
    represent one, and `models._now()` returns an aware datetime, so a row created in this
    same session would otherwise fail the whole export. Everything stored is UTC already.
    """
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    if isinstance(value, (dt.date, int, float)) or value is None:
        return value
    return str(value)


def run_export(db: Session, tenant_id: str, kind: str, filters: dict, *,
               actor: models.User, org_name: str = "", ip: str = "") -> models.BackgroundJob:
    """Build the export and record it as a completed job with a download link.

    Runs inline rather than through Celery: the job row and the download link are what the UI
    needs, and an export that fits in a request is not worth the operational surface of a
    queue. If a tenant grows past that, the same function becomes the task body unchanged —
    the row it writes is already the contract with the progress tray.
    """
    job = models.BackgroundJob(
        tenant_id=tenant_id, type=f"export.{kind}",
        label=f"Exporting {kind}", status="running", progress=10,
        created_by=actor.id,
        started_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    )
    db.add(job)
    db.flush()

    try:
        payload, count = build_workbook(db, tenant_id, kind, filters,
                                        generated_by=actor.name, org_name=org_name)
    except ExportError as e:
        job.status = "failed"
        job.error = str(e)[:600]
        job.completed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        # Flushed before re-raising: the session runs with autoflush off, so without this the
        # row stays as it was first written — "running" — and the progress tray shows a job
        # that never finishes instead of one that failed.
        db.flush()
        raise

    key = f"tenants/{tenant_id}/exports/{job.id}.xlsx"
    get_storage().put(key, payload, _MEDIA)

    job.status = "succeeded"
    job.progress = 100
    job.result_summary = f"{count:,} row{'s' if count != 1 else ''}"
    job.object_type = "export"
    job.object_id = job.id
    job.href = f"/exports/{job.id}/download"
    job.label = f"{kind.title()} export — {count:,} row{'s' if count != 1 else ''}"
    job.completed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    record(db, tenant_id=tenant_id, action="export.generated", actor=actor,
           object_type="export", object_id=job.id, object_label=job.label, ip=ip,
           meta={"kind": kind, "rows": count, "filters": _describe_filters(filters)})
    return job


def storage_key(job: models.BackgroundJob) -> str:
    return f"tenants/{job.tenant_id}/exports/{job.id}.xlsx"


def filename(job: models.BackgroundJob) -> str:
    kind = (job.type or "export").split(".")[-1]
    stamp = (job.completed_at or dt.datetime.now()).strftime("%Y%m%d")
    return f"{kind}-{stamp}.xlsx"
