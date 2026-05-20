"""Append-only audit log + tamper-evidence chain.

Every audit row stores `prev_hash` (the previous row's `row_hash` for that tenant) and
`row_hash` = HMAC-SHA256(audit_chain_key, prev_hash || canonical(this row)). The genesis
row for a tenant has `prev_hash = "0" * 64`. A later auditor can recompute the chain and
detect deletions or in-place edits: any break in the prev/row linkage, or any row whose
`row_hash` doesn't match the recomputed HMAC, signals tampering.

Concurrency model
-----------------
Concurrent audit inserts in the same tenant must serialize so they observe the same
`prev_hash`. We use a Postgres advisory lock (`pg_advisory_xact_lock`) keyed by a stable
hash of the tenant id; the lock is held only for the duration of the surrounding
transaction. On SQLite the BEGIN…COMMIT cycle is already single-writer. On MSSQL we fall
back to `sp_getapplock`. If neither is available we still chain (best-effort) but document
the residual race window — the chain is a tamper-evidence layer, not the only line of
defence (audit_log inserts are still append-only at the storage layer).

The chain key is `settings.effective_audit_chain_key` — either explicitly set or derived
from `SECRET_KEY` (see config.py).
"""

import hashlib
import hmac
import json

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from . import models
from .config import settings

_GENESIS_PREV_HASH = "0" * 64


def _canonical_row(
    *,
    tenant_id: str,
    actor_id: str | None,
    actor_name: str,
    action: str,
    object_type: str,
    object_id: str | None,
    object_label: str,
    meta: dict,
    ip: str,
    at_iso: str,
) -> bytes:
    """Deterministic byte representation of an audit row. Keys are sorted, separators are
    fixed, datetime is ISO-8601 — same input always serialises to the same bytes."""
    payload = {
        "tenant_id": tenant_id,
        "actor_id": actor_id or "",
        "actor_name": actor_name,
        "action": action,
        "object_type": object_type,
        "object_id": object_id or "",
        "object_label": object_label,
        "meta": meta or {},
        "ip": ip,
        "at": at_iso,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _hmac_chain(prev_hash: str, canonical: bytes) -> str:
    key = settings.effective_audit_chain_key.encode("utf-8")
    return hmac.new(key, (prev_hash or _GENESIS_PREV_HASH).encode("ascii") + canonical, hashlib.sha256).hexdigest()


def _acquire_tenant_lock(db: Session, tenant_id: str) -> None:
    """Serialize audit inserts per tenant for the lifetime of the current transaction."""
    if not tenant_id:
        return
    dialect = settings.db_dialect
    if dialect == "postgresql":
        # Advisory locks take a bigint — derive one from the tenant id (stable across replicas).
        n = int.from_bytes(hashlib.sha256(tenant_id.encode("utf-8")).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:n)"), {"n": n})
    elif dialect == "mssql":
        db.execute(text("EXEC sp_getapplock @Resource = :r, @LockMode = 'Exclusive', @LockOwner = 'Transaction'"),
                   {"r": f"cm-audit-{tenant_id}"})
    # SQLite: no advisory lock; engine is single-writer.


def _previous_row_hash(db: Session, tenant_id: str) -> str:
    """Latest row_hash for the tenant, or the genesis sentinel."""
    if not tenant_id:
        return _GENESIS_PREV_HASH
    row = db.scalar(
        select(models.AuditLog.row_hash)
        .where(models.AuditLog.tenant_id == tenant_id)
        .order_by(desc(models.AuditLog.at), desc(models.AuditLog.id))
        .limit(1)
    )
    return row or _GENESIS_PREV_HASH


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
    """Append an audit row with a chained HMAC, and optionally fan out a Notification.

    Caller commits. The chain is computed under a per-tenant advisory lock so concurrent
    audit writes serialize (see module docstring)."""
    _acquire_tenant_lock(db, tenant_id)

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
    # `at` is normally populated by the column default at flush time; for chain determinism
    # we set it explicitly *before* the hash so the canonical form matches what's persisted.
    import datetime as dt
    entry.at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    prev = _previous_row_hash(db, tenant_id)
    canonical = _canonical_row(
        tenant_id=tenant_id,
        actor_id=entry.actor_id,
        actor_name=entry.actor_name,
        action=entry.action,
        object_type=entry.object_type,
        object_id=entry.object_id,
        object_label=entry.object_label,
        meta=entry.meta,
        ip=entry.ip,
        at_iso=entry.at.isoformat(),
    )
    entry.prev_hash = prev
    entry.row_hash = _hmac_chain(prev, canonical)

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


# ---------- chain verification (operator / test tool) ----------


def verify_chain(db: Session, tenant_id: str) -> tuple[bool, list[dict]]:
    """Walk every audit row for `tenant_id` in chronological order, recompute the HMAC chain,
    and report any inconsistencies. Returns (ok, problems[]). A `problem` is a dict shaped
    {row_id, kind: 'prev_mismatch'|'hmac_mismatch'|'genesis_break', expected, found}.

    Pre-chain rows (created before 0013_hardening) carry empty `prev_hash` and `row_hash`;
    they are skipped silently — the chain is checked only across rows that have hashes.
    """
    problems: list[dict] = []
    rows = list(db.scalars(
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == tenant_id)
        .order_by(models.AuditLog.at.asc(), models.AuditLog.id.asc())
    ).all())
    expected_prev = _GENESIS_PREV_HASH
    seen_first_chained = False
    for r in rows:
        if not r.row_hash and not r.prev_hash:
            continue  # pre-chain row, ignore
        if not seen_first_chained:
            if r.prev_hash and r.prev_hash != _GENESIS_PREV_HASH:
                # First chained row should point to genesis. Allow if it points to the
                # last pre-chain row's row_hash (which is empty) — but that'd already be
                # caught by hmac_mismatch below.
                pass
            seen_first_chained = True
        if r.prev_hash != expected_prev:
            problems.append({
                "row_id": r.id, "kind": "prev_mismatch",
                "expected": expected_prev, "found": r.prev_hash,
            })
        canonical = _canonical_row(
            tenant_id=r.tenant_id, actor_id=r.actor_id, actor_name=r.actor_name,
            action=r.action, object_type=r.object_type, object_id=r.object_id,
            object_label=r.object_label, meta=r.meta or {}, ip=r.ip,
            at_iso=r.at.isoformat(),
        )
        recomputed = _hmac_chain(r.prev_hash or _GENESIS_PREV_HASH, canonical)
        if recomputed != r.row_hash:
            problems.append({
                "row_id": r.id, "kind": "hmac_mismatch",
                "expected": recomputed, "found": r.row_hash,
            })
        expected_prev = r.row_hash
    return (not problems), problems
