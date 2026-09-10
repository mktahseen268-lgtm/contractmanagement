"""Delegation-of-authority matrix — who may sign what.

RFP §4a(ii) 4.1–4.2: "Signatories tagged per authority matrix" and "flexible signatory
selection". Those two pull in opposite directions, and the resolution matters:

    The matrix **proposes**; a human **decides**; a deviation is **recorded**.

A hard block would be wrong for a bank. Authorised signatories go on leave, deals close on
Fridays, and a system that makes a legitimate execution impossible gets routed around — the
agreement gets signed on paper and the digital trail dies. So `resolve()` returns the required
signatory and `check_selection()` reports deviations; the caller must supply a reason to
proceed, and the override is audited with both the required and the chosen signatory.

Matching: a rule matches a contract when each of its set conditions matches. An unset field
means "any" and never narrows. Among matching rules the **most specific** wins — the one with
the most conditions actually set — and `priority` breaks ties.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from . import audit, models

#: Role hierarchy for "at least this senior". A rule requiring `manager` is satisfied by an
#: owner or admin — otherwise every matrix would need a row per role.
_ROLE_RANK = {"viewer": 0, "auditor": 0, "reviewer": 1, "author": 2, "approver": 3,
              "manager": 4, "admin": 5, "owner": 6}


class AuthorityError(RuntimeError):
    """An override was attempted without a reason. Routers map this to 400."""


def _specificity(rule: models.SignatoryAuthority) -> tuple[int, int]:
    """How narrowly this rule is drawn; ties broken by explicit priority."""
    score = sum(
        1 for value in (rule.department, rule.contract_type, rule.currency, rule.required_user_id)
        if value
    )
    if rule.min_value or rule.max_value is not None:
        score += 1
    return score, rule.priority


def _matches(rule: models.SignatoryAuthority, contract: models.Contract) -> bool:
    if rule.department and rule.department != contract.department:
        return False
    if rule.contract_type and rule.contract_type != contract.type:
        return False
    if rule.currency and rule.currency != contract.currency:
        return False
    value = contract.value or 0.0
    if value < (rule.min_value or 0.0):
        return False
    if rule.max_value is not None and value > rule.max_value:
        return False
    return True


def resolve(db, contract: models.Contract) -> models.SignatoryAuthority | None:
    """The rule governing this contract, or None when the matrix says nothing about it."""
    rules = db.scalars(
        select(models.SignatoryAuthority).where(
            models.SignatoryAuthority.tenant_id == contract.tenant_id,
            models.SignatoryAuthority.is_active.is_(True),
        )
    ).all()
    candidates = [r for r in rules if _matches(r, contract)]
    if not candidates:
        return None
    return max(candidates, key=_specificity)


def eligible_signatories(db, rule: models.SignatoryAuthority | None,
                         tenant_id: str) -> list[models.User]:
    """Users the rule permits, most senior first. Empty when the matrix is silent."""
    if rule is None:
        return []
    if rule.required_user_id:
        user = db.get(models.User, rule.required_user_id)
        return [user] if user is not None and user.is_active else []

    if not rule.required_role:
        return []
    minimum = _ROLE_RANK.get(rule.required_role, 99)
    users = db.scalars(
        select(models.User).where(
            models.User.tenant_id == tenant_id,
            models.User.is_active.is_(True),
        )
    ).all()
    allowed = [u for u in users if _ROLE_RANK.get(u.role, -1) >= minimum]
    return sorted(allowed, key=lambda u: -_ROLE_RANK.get(u.role, 0))


def propose(db, contract: models.Contract) -> dict:
    """What the matrix says should happen for this contract. Shown when preparing an envelope."""
    rule = resolve(db, contract)
    eligible = eligible_signatories(db, rule, contract.tenant_id)
    return {
        "rule_id": rule.id if rule else None,
        "rule_name": rule.name if rule else "",
        "required_role": rule.required_role if rule else "",
        "required_user_id": rule.required_user_id if rule else None,
        "signatories_required": rule.signatories_required if rule else 0,
        "escalation_user_id": rule.escalation_user_id if rule else None,
        "eligible": [
            {"id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in eligible
        ],
        "matrix_silent": rule is None,
    }


def check_selection(db, contract: models.Contract, signer_user_ids: list[str]) -> dict:
    """Compare a chosen signatory set against the matrix.

    Returns `{compliant, rule_id, deviations[], required[]}`. `deviations` is empty when the
    selection satisfies the rule — the caller only needs an override reason when it is not.
    """
    rule = resolve(db, contract)
    if rule is None:
        return {"compliant": True, "rule_id": None, "rule_name": "", "deviations": [],
                "required": [], "matrix_silent": True}

    eligible = eligible_signatories(db, rule, contract.tenant_id)
    eligible_ids = {u.id for u in eligible}
    chosen = [uid for uid in signer_user_ids if uid]

    deviations: list[str] = []
    if rule.required_user_id and rule.required_user_id not in chosen:
        named = db.get(models.User, rule.required_user_id)
        deviations.append(
            f"{rule.name}: requires {named.name if named else rule.required_user_id} to sign."
        )
    unauthorised = [uid for uid in chosen if eligible_ids and uid not in eligible_ids]
    for uid in unauthorised:
        who = db.get(models.User, uid)
        deviations.append(
            f"{rule.name}: {who.name if who else uid} is not authorised to sign a "
            f"{contract.type} of {contract.value:,.0f} {contract.currency}"
            + (f" (requires {rule.required_role} or above)." if rule.required_role else ".")
        )
    authorised_count = len([uid for uid in chosen if uid in eligible_ids])
    if authorised_count < rule.signatories_required:
        deviations.append(
            f"{rule.name}: requires {rule.signatories_required} authorised signatory(ies); "
            f"{authorised_count} selected."
        )

    return {
        "compliant": not deviations,
        "rule_id": rule.id,
        "rule_name": rule.name,
        "deviations": deviations,
        "required": [{"id": u.id, "name": u.name, "role": u.role} for u in eligible],
        "matrix_silent": False,
    }


def enforce(db, contract: models.Contract, signer_user_ids: list[str], *,
            override_reason: str = "", actor: models.User | None = None,
            envelope_id: str | None = None) -> dict:
    """Gate envelope preparation on the matrix.

    Compliant selection → proceed silently. Non-compliant with a reason → proceed, audited as
    an override. Non-compliant without a reason → `AuthorityError`.
    """
    result = check_selection(db, contract, signer_user_ids)
    if result["compliant"]:
        return result

    if not override_reason.strip():
        raise AuthorityError(
            "This signatory selection deviates from the authority matrix: "
            + " ".join(result["deviations"])
            + " Supply an override reason to proceed."
        )

    audit.record(
        db, tenant_id=contract.tenant_id, action="signature.authority_override", actor=actor,
        object_type="contract", object_id=contract.id,
        object_label=contract.reference_no or contract.title,
        meta={
            "envelope_id": envelope_id,
            "rule_id": result["rule_id"],
            "rule_name": result["rule_name"],
            "deviations": result["deviations"],
            "required": result["required"],
            "chosen_user_ids": signer_user_ids,
            "reason": override_reason.strip(),
            "contract_value": contract.value,
            "currency": contract.currency,
        },
    )
    result["overridden"] = True
    return result


def upsert(db, tenant_id: str, data: dict, *, actor: models.User | None = None,
           rule_id: str | None = None) -> models.SignatoryAuthority:
    """Create or update a rule. Changing who can sign is itself an audited event."""
    rule = db.get(models.SignatoryAuthority, rule_id) if rule_id else None
    creating = rule is None
    if creating:
        rule = models.SignatoryAuthority(tenant_id=tenant_id, name=data.get("name", "Rule"),
                                         created_by=actor.id if actor else "")
        db.add(rule)

    for field in ("name", "department", "contract_type", "currency", "min_value", "max_value",
                  "required_role", "required_user_id", "signatories_required",
                  "escalation_user_id", "priority", "is_active", "notes"):
        if field in data and data[field] is not None:
            setattr(rule, field, data[field])
    rule.updated_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    db.flush()

    audit.record(
        db, tenant_id=tenant_id,
        action="authority.rule_created" if creating else "authority.rule_updated",
        actor=actor, object_type="signatory_authority", object_id=rule.id, object_label=rule.name,
        meta={
            "department": rule.department, "contract_type": rule.contract_type,
            "currency": rule.currency, "min_value": rule.min_value, "max_value": rule.max_value,
            "required_role": rule.required_role, "required_user_id": rule.required_user_id,
            "signatories_required": rule.signatories_required, "is_active": rule.is_active,
        },
    )
    return rule
