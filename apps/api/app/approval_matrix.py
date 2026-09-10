"""Dynamic approval matrix — *who* must review, decided from the contract's own attributes.

RFP §4a: "Dynamic approval matrix — value thresholds, risk categories, dept-specific
approvers". A fixed workflow per contract type cannot express "anything over 10 million also
needs the CFO" without duplicating the whole workflow for every value band, which is how
approval matrices rot: the bands change, half the copies get updated, and nobody can say what
the rule actually is any more.

So rules **add stages** to a run rather than replacing it. The base workflow says how a
contract of this type is normally reviewed; matching rules layer on the extra scrutiny its
value, risk, jurisdiction or non-standard status demands. One rule, one concern.

Evaluated at run start, and re-evaluated when a material field changes — a contract quietly
edited from 900,000 to 9,000,000 after the CFO stage was skipped is exactly the hole this
closes, and the re-route is audited.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from . import models

log = logging.getLogger("uvicorn.error")

#: The fields a rule can key on. A change to any of these re-opens the routing question.
MATERIAL_FIELDS = ("type", "department", "currency", "value", "risk_level",
                   "governing_law", "is_non_standard")


def snapshot(contract: models.Contract) -> dict:
    """The routing-relevant state of a contract, for change detection."""
    return {
        "type": contract.type or "",
        "department": contract.department or "",
        "currency": contract.currency or "",
        "value": float(contract.value or 0.0),
        "risk_level": contract.risk_level or "",
        "governing_law": contract.governing_law or "",
        "is_non_standard": bool(contract.is_non_standard),
    }


def _matches(rule: models.ApprovalRule, contract: models.Contract,
             deviations: int = 0) -> bool:
    if rule.contract_type and rule.contract_type != contract.type:
        return False
    if rule.department and rule.department != contract.department:
        return False
    if rule.currency and rule.currency != contract.currency:
        return False
    if rule.risk_level and rule.risk_level != contract.risk_level:
        return False
    if rule.governing_law and rule.governing_law != contract.governing_law:
        return False
    if rule.non_standard_only and not contract.is_non_standard:
        return False
    if rule.min_playbook_deviations and deviations < rule.min_playbook_deviations:
        return False
    value = float(contract.value or 0.0)
    if value < (rule.min_value or 0.0):
        return False
    return not (rule.max_value is not None and value > rule.max_value)


def matching_rules(db, contract: models.Contract,
                   deviations: int = 0) -> list[models.ApprovalRule]:
    """Active rules that apply to this contract, in the order they should be inserted."""
    rules = db.scalars(
        select(models.ApprovalRule).where(
            models.ApprovalRule.tenant_id == contract.tenant_id,
            models.ApprovalRule.is_active.is_(True),
        )
    ).all()
    matched = [r for r in rules if _matches(r, contract, deviations)]
    # Higher priority first so a deliberate ordering wins; stable by name otherwise.
    return sorted(matched, key=lambda r: (-r.priority, r.name))


def _stage_from_rule(rule: models.ApprovalRule) -> dict:
    return {
        "name": rule.stage_name or rule.name,
        "policy": rule.stage_policy or "all",
        "threshold": rule.stage_threshold or 0,
        "sla_hours": rule.sla_hours or 0,
        "escalate_to_user_id": rule.escalate_to_user_id,
        "steps": list(rule.stage_steps or []),
        "from_rule_id": rule.id,
    }


def apply(db, contract: models.Contract, stages: list[dict],
          deviations: int = 0) -> tuple[list[dict], list[models.ApprovalRule], dict]:
    """Layer matching rules onto a base stage list.

    Returns (stages, applied_rules, routing_snapshot). A rule with no steps is skipped rather
    than inserting an empty stage that could never complete.
    """
    out = list(stages)
    used: list[models.ApprovalRule] = []

    for rule in matching_rules(db, contract, deviations):
        if not rule.stage_steps:
            # A rule that matches but names nobody would insert a stage that can never
            # complete, silently stalling the review. Skip it loudly instead.
            log.warning("approval rule %s (%s) matched but defines no reviewers",
                        rule.id, rule.name)
            continue
        stage = _stage_from_rule(rule)
        position = rule.insert_after_stage
        if position is None or position < 0 or position >= len(out):
            out.append(stage)
        else:
            out.insert(position + 1, stage)
        used.append(rule)

    return out, used, snapshot(contract)


def needs_rerouting(db, run: models.WorkflowRun, contract: models.Contract,
                    deviations: int = 0) -> tuple[bool, list[str]]:
    """Has a material field changed such that a different rule set now applies?

    Returns (needs_reroute, reasons). Compares both the raw fields and the resulting rule set:
    a value change that crosses no threshold is not worth disturbing an in-flight review over,
    while one that pulls in the CFO very much is.
    """
    before = run.routing_snapshot or {}
    after = snapshot(contract)
    changed = [
        f"{field}: {before.get(field)!r} → {after.get(field)!r}"
        for field in MATERIAL_FIELDS
        if before.get(field) != after.get(field)
    ]
    if not changed:
        return False, []

    previous = set(run.applied_rule_ids or [])
    # Compare like with like: `applied_rule_ids` only records rules that actually contributed
    # a stage, so a rule matching with no reviewers must not read as a routing change.
    current = {r.id for r in matching_rules(db, contract, deviations) if r.stage_steps}
    if previous == current:
        # Fields moved but the approval requirements did not.
        return False, changed
    return True, changed
