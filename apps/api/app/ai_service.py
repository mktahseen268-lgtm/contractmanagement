"""AI assist — clause suggestion, deviation flagging, and data capture with confirmation.

**Most of this does not need a model, and saying so is the honest engineering.** The brief asks
for three things:

- *clause suggestion from metadata* — answerable from the library itself: which approved
  clauses do comparable agreements of this type actually use, that this draft is missing?
  That is a counting question. An LLM would answer it less accurately and less repeatably,
  and would need a model deployment to answer it at all.
- *playbook-deviation flagging* — already built (`playbook_service`), deterministic, and
  explainable to an auditor line by line. Replacing it with a model would trade an
  explanation for a guess.
- *AI data capture* — extracting parties, dates, values and notice periods from a signed PDF.
  **This is the part that genuinely needs a model**, and it runs through the existing
  `ocr_provider` seam.

The residency constraint is absolute: no MMBL data may leave the deployment. So the MMBL
profile uses `OCR_PROVIDER=local` against a model hosted inside the network (vLLM, Ollama, or
anything speaking the OpenAI chat-completions shape). The hosted-Claude adapter stays available
for deployments without that constraint, and the stub stays the zero-config default.

**Nothing extracted is ever written to a contract automatically.** A confidence score is not a
fact; it is a reason to look. Every capture lands in an `ExtractionReview` a human has to
confirm field by field, and what they accepted is audited.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clause_service, models, playbook_service
from .audit import record

#: Below this, a captured value is shown but never pre-ticked for acceptance. Tuned low
#: deliberately: the cost of a missed field is a human typing it, the cost of a wrong field
#: silently accepted is a contract that misstates its own end date.
# ponytail: single global threshold; per-field thresholds if real documents show one field is
# systematically less reliable than the rest.
AUTO_SUGGEST_CONFIDENCE = 0.85

#: Fields a capture may write. Anything outside this cannot be set by extraction at all.
CAPTURABLE = {
    "title", "type", "counterparty", "effective_date", "end_date",
    "value", "currency", "renewal_type", "governing_law",
}


class AiError(ValueError):
    """Refused AI operation. Routers map to 400."""


# ---------------------------------------------------------------------------------------
# Clause suggestion
# ---------------------------------------------------------------------------------------


def suggest_clauses(db: Session, contract: models.Contract, *, limit: int = 8) -> list[dict]:
    """Approved clauses this draft is missing, ranked by how much they are needed.

    Three tiers, most important first:

    1. **Policy requires it** — the playbook says this clause must be present and it is not.
       Not a suggestion so much as a defect, but it belongs at the top of the same list.
    2. **Comparable agreements use it** — clauses that appear in other agreements of this type
       in this workspace. Evidence, not a guess.
    3. **The library recommends it** — high-risk clauses of any category the draft lacks.
    """
    body = (contract.body or "")
    present = set(clause_service.references_in(body))
    for entry in (contract.included_clauses or []):
        present.add(entry.get("key", ""))

    suggestions: dict[str, dict] = {}

    # 1. Policy-required and missing.
    review = playbook_service.review(db, contract)
    for finding in review["findings"]:
        if finding["status"] == "missing" and finding["kind"] == "required":
            suggestions[finding["clause_key"]] = {
                "key": finding["clause_key"],
                "title": finding["title"],
                "reason": f"Required by {finding['playbook']} and not present.",
                "basis": "policy",
                "severity": finding["severity"],
                "risk_level": finding["risk_level"],
                "score": 100 if finding["severity"] == "blocker" else 80,
            }

    # 2. What comparable agreements actually use.
    peers = db.scalars(
        select(models.Contract).where(
            models.Contract.tenant_id == contract.tenant_id,
            models.Contract.type == contract.type,
            models.Contract.id != contract.id,
        )
    ).all()
    usage: Counter = Counter()
    for peer in peers:
        for entry in (peer.included_clauses or []):
            key = entry.get("key")
            if key:
                usage[key] += 1

    for key, count in usage.most_common():
        if key in present or key in suggestions:
            continue
        clause = clause_service.by_key(db, contract.tenant_id, key)
        if clause is None or clause.status != "active":
            continue
        share = count / max(1, len(peers))
        suggestions[key] = {
            "key": key, "title": clause.title,
            "reason": (f"Used by {count} of {len(peers)} other "
                       f"{(contract.type or 'other').replace('_', ' ')} agreements."),
            "basis": "peers", "severity": "warning", "risk_level": clause.risk_level,
            "score": 40 + int(share * 30),
        }

    # 3. High-risk library clauses the draft simply lacks.
    for clause in db.scalars(
        select(models.Clause).where(
            models.Clause.tenant_id == contract.tenant_id,
            models.Clause.status == "active",
            models.Clause.parent_id.is_(None),
            models.Clause.risk_level.in_(("high", "critical")),
        )
    ).all():
        if clause.key in present or clause.key in suggestions:
            continue
        suggestions[clause.key] = {
            "key": clause.key, "title": clause.title,
            "reason": f"A {clause.risk_level}-risk clause in the library that this draft omits.",
            "basis": "risk", "severity": "warning", "risk_level": clause.risk_level,
            "score": 20,
        }

    ranked = sorted(suggestions.values(), key=lambda s: (-s["score"], s["title"]))
    for entry in ranked:
        clause = clause_service.by_key(db, contract.tenant_id, entry["key"])
        entry["body"] = clause_service.approved_body(db, clause) if clause else ""
        entry["guidance"] = clause.guidance if clause else ""
    return ranked[:limit]


# ---------------------------------------------------------------------------------------
# Data capture
# ---------------------------------------------------------------------------------------


def capture(db: Session, contract: models.Contract, *, file_bytes: bytes | None,
            file_name: str, content_type: str = "", actor: models.User | None = None,
            ip: str = "") -> models.ExtractionReview:
    """Run extraction over a document and file the result **for confirmation**.

    Never writes to the contract. The whole point of the confidence score is that it is not a
    fact — a document that says "the term is 12 months from the Effective Date" and a model
    that guesses which date that is produce a plausible, wrong end date. A human confirms.
    """
    from .ocr_provider import get_ocr_provider

    provider = get_ocr_provider()
    result = provider.extract(file_bytes=file_bytes, file_name=file_name,
                              content_type=content_type)

    fields = {k: v for k, v in (result.get("fields") or {}).items() if k in CAPTURABLE}
    review = models.ExtractionReview(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        file_name=file_name[:300], provider=str(result.get("provider") or provider.name),
        fields=fields, summary=str(result.get("summary") or "")[:2000],
        detected_clauses=list(result.get("detected_clauses") or []),
        status="pending", created_by=actor.id if actor else "",
    )
    db.add(review)
    db.flush()

    record(db, tenant_id=contract.tenant_id, action="contract.ai_extracted", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"provider": review.provider, "file": file_name[:120],
                 "fields": sorted(fields.keys()),
                 "note": "Captured for human confirmation; nothing written to the contract."})
    return review


def _coerce(field: str, value):  # type: ignore[no-untyped-def]
    """A captured value in the shape the contract column expects."""
    if field in ("effective_date", "end_date"):
        if isinstance(value, dt.date):
            return value
        try:
            return dt.date.fromisoformat(str(value).strip())
        except (TypeError, ValueError) as e:
            raise AiError(f"'{value}' is not a date I can use for {field}.") from e
    if field == "value":
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError) as e:
            raise AiError(f"'{value}' is not a number I can use for the contract value.") from e
    return str(value).strip()


def apply_capture(db: Session, review: models.ExtractionReview, contract: models.Contract,
                  accepted: list[str], *, actor: models.User, ip: str = "") -> dict:
    """Write only the fields a human ticked. Returns what changed.

    Refuses a field the capture did not produce, rather than silently ignoring it: a client
    asking to accept something that was never offered has a stale view, and honouring the rest
    would write a set of values nobody actually reviewed.
    """
    if review.status != "pending":
        raise AiError("This extraction has already been dealt with.")

    offered = set((review.fields or {}).keys())
    unknown = sorted(set(accepted) - offered)
    if unknown:
        raise AiError(
            "These fields were not part of this extraction: " + ", ".join(unknown)
        )

    applied: dict = {}
    for field in accepted:
        raw = (review.fields or {}).get(field, {})
        value = raw.get("value") if isinstance(raw, dict) else raw
        if value in (None, ""):
            continue
        before = getattr(contract, field, None)
        setattr(contract, field, _coerce(field, value))
        applied[field] = {"from": str(before or ""), "to": str(getattr(contract, field))}

    review.status = "applied" if applied else "discarded"
    review.applied_fields = sorted(applied.keys())
    review.reviewed_by = actor.id
    review.reviewed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    record(db, tenant_id=contract.tenant_id, action="contract.ai_capture_confirmed", actor=actor,
           object_type="contract", object_id=contract.id, object_label=contract.title, ip=ip,
           meta={"extraction_id": review.id, "provider": review.provider,
                 "applied": applied,
                 "offered": sorted(offered),
                 "note": "Confirmed by a person; the model did not write these."})
    return applied


def discard(db: Session, review: models.ExtractionReview, *, actor: models.User,
            ip: str = "") -> None:
    if review.status != "pending":
        raise AiError("This extraction has already been dealt with.")
    review.status = "discarded"
    review.reviewed_by = actor.id
    review.reviewed_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    record(db, tenant_id=review.tenant_id, action="contract.ai_capture_discarded", actor=actor,
           object_type="contract", object_id=review.contract_id, ip=ip,
           meta={"extraction_id": review.id})


def presentable(db: Session, review: models.ExtractionReview,
                contract: models.Contract) -> dict:
    """The review shaped for a human: what was found, how sure, and what it would replace."""
    rows = []
    for field, raw in (review.fields or {}).items():
        value = raw.get("value") if isinstance(raw, dict) else raw
        confidence = float(raw.get("confidence", 0.0)) if isinstance(raw, dict) else 0.0
        current = getattr(contract, field, None)
        rows.append({
            "field": field,
            "value": "" if value is None else str(value),
            "confidence": round(confidence, 2),
            "current": "" if current in (None, "") else str(current),
            "changes": str(current or "") != str(value or ""),
            #: Pre-ticked only above the threshold — and only when it would actually change
            #: something, so confirming does not become a habit of clicking through no-ops.
            "suggested": confidence >= AUTO_SUGGEST_CONFIDENCE
            and str(current or "") != str(value or ""),
        })
    rows.sort(key=lambda r: (-r["confidence"], r["field"]))
    return {
        "id": review.id,
        "contract_id": review.contract_id,
        "file_name": review.file_name,
        "provider": review.provider,
        "status": review.status,
        "summary": review.summary,
        "detected_clauses": list(review.detected_clauses or []),
        "fields": rows,
        "applied_fields": list(review.applied_fields or []),
        "created_at": review.created_at,
        "reviewed_at": review.reviewed_at,
    }
