import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import record
from ..config import settings
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..storage import get_storage, tenant_key

router = APIRouter(prefix="/files", tags=["files"])

_VALID_KINDS = {"attachment", "ocr_source", "contract_pdf", "export"}


def save_upload(
    db: Session,
    *,
    tenant_id: str,
    file: UploadFile,
    kind: str = "attachment",
    created_by: str,
    parent_type: str = "",
    parent_id: str | None = None,
) -> models.FileObject:
    """Read an UploadFile, store it, and create a FileObject row (not committed)."""
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File too large (max {settings.max_upload_mb} MB).")
    if kind not in _VALID_KINDS:
        kind = "attachment"
    storage = get_storage()
    storage.ensure_ready()
    fid = uuid.uuid4().hex
    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_").strip()[:200] or "upload"
    key = tenant_key(tenant_id, kind, f"{fid}-{safe_name}")
    ctype = file.content_type or "application/octet-stream"
    storage.put(key, data, ctype)
    obj = models.FileObject(
        id=fid,
        tenant_id=tenant_id,
        key=key,
        bucket=settings.s3_bucket if settings.use_s3 else "",
        backend=storage.name,
        content_type=ctype,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        original_name=safe_name,
        kind=kind,
        parent_type=parent_type,
        parent_id=parent_id,
        created_by=created_by,
    )
    db.add(obj)
    db.flush()
    return obj


def _get_owned(db: Session, user: models.User, file_id: str) -> models.FileObject:
    obj = db.get(models.FileObject, file_id)
    if obj is None or obj.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return obj


@router.post("", response_model=schemas.FileObjectOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> schemas.FileObjectOut:
    obj = save_upload(db, tenant_id=user.tenant_id, file=file, kind="attachment", created_by=user.id)
    record(db, tenant_id=user.tenant_id, action="file.uploaded", actor=user, object_type="file", object_id=obj.id, object_label=obj.original_name, ip=client_ip(request), meta={"kind": obj.kind, "size": obj.size})
    db.commit()
    db.refresh(obj)
    return schemas.FileObjectOut.model_validate(obj)


@router.get("/{file_id}", response_model=schemas.FileObjectOut)
def get_file(file_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> schemas.FileObjectOut:
    return schemas.FileObjectOut.model_validate(_get_owned(db, user, file_id))


@router.get("/{file_id}/download")
def download_file(file_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)) -> StreamingResponse:
    obj = _get_owned(db, user, file_id)
    stream = get_storage().open_stream(obj.key)

    def _iter():
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        _iter(),
        media_type=obj.content_type,
        headers={"Content-Disposition": f'inline; filename="{obj.original_name}"'},
    )
