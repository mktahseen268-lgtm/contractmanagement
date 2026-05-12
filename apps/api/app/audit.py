from sqlalchemy.orm import Session

from . import models


def record(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    actor: models.User | None = None,
    object_type: str = "",
    object_id: str | None = None,
    object_label: str = "",
    meta: dict | None = None,
    ip: str = "",
    notify_user_id: str | None = None,
    notify_title: str | None = None,
    notify_body: str = "",
) -> models.AuditLog:
    entry = models.AuditLog(
        tenant_id=tenant_id,
        actor_id=actor.id if actor else None,
        actor_name=actor.name if actor else "system",
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        meta=meta or {},
        ip=ip,
    )
    db.add(entry)
    if notify_user_id and notify_title:
        db.add(
            models.Notification(
                tenant_id=tenant_id,
                user_id=notify_user_id,
                type=action,
                title=notify_title,
                body=notify_body,
                object_type=object_type,
                object_id=object_id,
            )
        )
    return entry
