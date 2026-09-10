"""Bulk send — dispatch one approved template to many signers (RFP BB-09).

The HTTP layer only. Validation, fan-out and failure isolation live in `bulk_send_service`;
this translates its refusals into status codes and its records into responses.

There is no CSV upload endpoint on purpose. The browser parses the file and posts rows as
JSON, which keeps a user-supplied file out of the server entirely — no multipart handler, no
temporary file, nothing for the antivirus seam to have an opinion about. The validation that
matters happens on the rows either way.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import bulk_send_service, models, schemas
from ..bulk_send_service import BulkSendError
from ..database import get_db
from ..deps import client_ip, get_current_user

router = APIRouter(prefix="/bulk-send", tags=["bulk-send"])

#: Sending on behalf of the workspace to hundreds of counterparties is not an authoring action.
#: `author` can raise a contract; dispatching a batch needs someone accountable for the mailout.
_SEND_ROLES = {"owner", "admin", "manager"}


def _batch(db: Session, user: models.User, batch_id: str) -> models.BulkSendBatch:
    b = db.get(models.BulkSendBatch, batch_id)
    if b is None or b.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return b


def _template(db: Session, user: models.User, template_id: str) -> models.ContractTemplate:
    t = db.get(models.ContractTemplate, template_id)
    if t is None or t.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


def _require_sender(user: models.User) -> None:
    if user.role not in _SEND_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You don't have permission to send in bulk.")


def _rows(data: schemas.BulkSendIn) -> list[dict]:
    return [{"name": r.name, "email": r.email, "values": r.values} for r in data.rows]


def _items(db: Session, batch: models.BulkSendBatch) -> list[schemas.BulkSendItemOut]:
    rows = db.scalars(
        select(models.BulkSendItem)
        .where(models.BulkSendItem.batch_id == batch.id)
        .order_by(models.BulkSendItem.sequence)
    ).all()
    return [schemas.BulkSendItemOut.model_validate(r) for r in rows]


def _detail(db: Session, batch: models.BulkSendBatch) -> schemas.BulkSendBatchDetail:
    t = db.get(models.ContractTemplate, batch.template_id)
    out = schemas.BulkSendBatchDetail.model_validate(batch)
    out.template_name = t.name if t else ""
    out.items = _items(db, batch)
    return out


@router.post("/validate", response_model=schemas.BulkSendValidateOut)
def validate(data: schemas.BulkSendIn, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> schemas.BulkSendValidateOut:
    """Check the sheet without sending anything.

    Separate from the send so an operator can paste 500 rows, see the twelve that are broken,
    and fix them — rather than finding out by having 488 envelopes go out and twelve not.
    """
    _require_sender(user)
    t = _template(db, user, data.template_id)
    try:
        problems = bulk_send_service.validate_rows(t, _rows(data), data.shared_values)
    except BulkSendError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return schemas.BulkSendValidateOut(rows=len(data.rows), problems=problems)


@router.post("", response_model=schemas.BulkSendBatchDetail,
             status_code=status.HTTP_201_CREATED)
def create(data: schemas.BulkSendIn, request: Request, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)) -> schemas.BulkSendBatchDetail:
    _require_sender(user)
    t = _template(db, user, data.template_id)
    try:
        batch = bulk_send_service.create_batch(
            db, template=t, actor=user, rows=_rows(data), name=data.name,
            message=data.message, shared_values=data.shared_values,
            reminder_interval_days=data.reminder_interval_days,
            max_reminders=data.max_reminders, expiry_days=data.expiry_days,
            ip=client_ip(request),
        )
    except BulkSendError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"message": str(e), "problems": e.problems}) from e
    db.commit()

    batch_id = batch.id
    # Enqueued after the commit, never inside the transaction: a task that starts before the
    # rows are visible reads an empty batch and reports it finished with nothing sent.
    from ..tasks import run_bulk_send

    run_bulk_send.delay(batch_id)

    db.expire_all()
    return _detail(db, _batch(db, user, batch_id))


@router.get("", response_model=list[schemas.BulkSendBatchOut])
def list_batches(limit: int = 50, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> list[schemas.BulkSendBatchOut]:
    rows = db.scalars(
        select(models.BulkSendBatch)
        .where(models.BulkSendBatch.tenant_id == user.tenant_id)
        .order_by(desc(models.BulkSendBatch.created_at))
        .limit(max(1, min(200, limit)))
    ).all()
    return [schemas.BulkSendBatchOut.model_validate(r) for r in rows]


@router.get("/{batch_id}", response_model=schemas.BulkSendBatchDetail)
def get_batch(batch_id: str, db: Session = Depends(get_db),
              user: models.User = Depends(get_current_user)) -> schemas.BulkSendBatchDetail:
    return _detail(db, _batch(db, user, batch_id))


@router.post("/{batch_id}/cancel", response_model=schemas.BulkSendBatchDetail)
def cancel(batch_id: str, request: Request, db: Session = Depends(get_db),
           user: models.User = Depends(get_current_user)) -> schemas.BulkSendBatchDetail:
    _require_sender(user)
    batch = _batch(db, user, batch_id)
    try:
        bulk_send_service.cancel(db, batch, actor=user, ip=client_ip(request))
    except BulkSendError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    db.commit()
    return _detail(db, batch)


@router.post("/{batch_id}/retry", response_model=schemas.BulkSendBatchDetail)
def retry(batch_id: str, request: Request, db: Session = Depends(get_db),
          user: models.User = Depends(get_current_user)) -> schemas.BulkSendBatchDetail:
    _require_sender(user)
    batch = _batch(db, user, batch_id)
    try:
        bulk_send_service.retry_failed(db, batch, actor=user, ip=client_ip(request))
    except BulkSendError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    db.commit()

    from ..tasks import run_bulk_send

    run_bulk_send.delay(batch.id)
    db.expire_all()
    return _detail(db, _batch(db, user, batch_id))
