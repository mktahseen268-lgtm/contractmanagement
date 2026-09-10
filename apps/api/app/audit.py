"""Append-only audit log + tamper-evidence chain.

Every audit row stores `prev_hash` (the previous row's `row_hash` for that tenant) and
`row_hash` = HMAC-SHA256(audit_chain_key, prev_hash || canonical(this row)). The genesis
row for a tenant has `prev_hash = "0" * 64`. A later auditor can recompute the chain and
detect deletions or in-place edits: any break in the prev/row linkage, or any row whose
`row_hash` doesn't match the recomputed HMAC, signals tampering.

Concurrency model
-----------------
Concurrent audit inserts in the same tenant must serialize so they observe the same
`prev_hash`. `db_dialect.advisory_lock` takes a transaction-scoped exclusive lock keyed by
the tenant id: `pg_advisory_xact_lock` on Postgres, `sp_getapplock` on MSSQL, `DBMS_LOCK`
on Oracle. On SQLite the BEGIN…COMMIT cycle is already single-writer. Where no lock is
available we still chain (best-effort) but document the residual race window — the chain is
a tamper-evidence layer, not the only line of defence (audit_log inserts are still
append-only at the storage layer).

The chain key is `settings.effective_audit_chain_key` — either explicitly set or derived
from `SECRET_KEY` (see config.py).
"""

import datetime as _dt
import hashlib
import hmac
import json

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import db_dialect, models
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
    db_dialect.advisory_lock(db, settings.db_dialect, f"cm-audit-{tenant_id}")


def _utcnow() -> _dt.datetime:
    """The audit clock. A single function so a test can force two rows into the same tick and
    prove the chain still detects tampering when timestamps tie."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _previous_row(db: Session, tenant_id: str) -> tuple[str, int]:
    """(row_hash, seq) of the tenant's latest audit row, or the genesis sentinel.

    Ordered by `seq` — the monotonic insertion counter — not by `at`. Two rows written in the
    same clock tick share a timestamp, and ordering by `(at, id)` then falls back to a random
    uuid: the chain could skip a row, and deleting the skipped row left a chain that still
    verified. `seq` is assigned under the advisory lock this function is already called
    beneath, so concurrent writers cannot collide on it.
    """
    if not tenant_id:
        return _GENESIS_PREV_HASH, 0
    row = db.execute(
        select(models.AuditLog.row_hash, models.AuditLog.seq)
        .where(models.AuditLog.tenant_id == tenant_id)
        .order_by(desc(models.AuditLog.seq), desc(models.AuditLog.at), desc(models.AuditLog.id))
        .limit(1)
    ).first()
    if row is None:
        return _GENESIS_PREV_HASH, 0
    return (row[0] or _GENESIS_PREV_HASH), int(row[1] or 0)


def _previous_row_hash(db: Session, tenant_id: str) -> str:
    """Back-compat shim for callers that only want the hash."""
    return _previous_row(db, tenant_id)[0]


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
    entry.at = _utcnow()

    prev, prev_seq = _previous_row(db, tenant_id)
    entry.seq = prev_seq + 1
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
    # Flush now, not at commit. The session runs with `autoflush=False`, so without this the
    # `_previous_row` query in the *next* `record()` of the same transaction would not see this
    # row — two audit entries in one request would both claim seq 1 and both chain to the
    # genesis hash, and `verify_chain` would then report tampering on an honest log. Recording
    # two actions in one transaction is ordinary (a workflow decision, a grant plus a
    # break-glass), so this is the common path, not an edge case.
    db.flush()

    # Ship it to the SIEM. Best effort and never raises: a collector outage must not stop
    # somebody signing a contract, and the audit row is already durable — the gap can be
    # replayed from the chain afterwards (`/siem/replay`).
    try:
        from . import siem

        siem.emit(entry)
    except Exception:  # noqa: BLE001 — monitoring must never break the thing it monitors
        pass

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
    # Walk in `seq` order: the insertion order the chain was actually built in. Pre-0023
    # rows carry seq 0 and fall back to `(at, id)`, which is how they were chained.
    rows = list(db.scalars(
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == tenant_id)
        .order_by(models.AuditLog.seq.asc(), models.AuditLog.at.asc(),
                  models.AuditLog.id.asc())
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
