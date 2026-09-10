"""Playbooks — "is this draft within policy?", answered on every revision.

A clause library on its own is a well-organised text store. The playbook is what makes it a
control: for a given kind of agreement it declares which clauses must be present, which must
never be, and which are merely preferred — and `review()` measures an actual draft against
that, reporting three distinct findings that are usually conflated:

- **missing** — a required clause is not in the document at all;
- **altered** — a required clause is there, but the wording has been changed from what was
  approved (the interesting case: this is how liability caps quietly grow);
- **prohibited** — language that policy says must not appear.

Only `altered` needs anything clever. Text comparison uses `difflib` from the standard library
rather than a similarity service: the question "is this paragraph still the approved one?" is
a string question, and an answer that needs a network call is an answer that fails when the
network does.

A blocker-severity finding classifies the agreement **non-standard**, which the workflow
engine already routes differently — so policy deviation changes who has to approve it, without
anyone remembering to tick a box.
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clause_service, models

# ponytail: similarity thresholds are heuristics, tuned against the seeded corpus. They are
# named here rather than inlined so an operator can move them once real MMBL paperwork shows
# where they sit. Raise MATCH to catch subtler edits at the cost of flagging reformatting.
#: At or above this, the wording counts as unchanged (tolerates whitespace/case only).
UNCHANGED_RATIO = 0.98
#: At or above this, it is recognisably the same clause — so the difference is an *edit*,
#: not an absence. Below it, the clause is simply not there.
PRESENT_RATIO = 0.55

RULE_KINDS = ("required", "prohibited", "preferred")
SEVERITIES = ("blocker", "warning")


class PlaybookError(ValueError):
    """Invalid playbook definition. Routers map to 400."""


def _normalise(text: str) -> str:
    """Collapse everything that does not change what the words say.

    Markdown emphasis, heading marks, list bullets and whitespace all vary between a template,
    a Word round-trip and a hand edit without altering the obligation. Comparing raw text
    would flag every one of those as a deviation and train reviewers to ignore the report.
    """
    text = re.sub(r"[*_`#>]+", " ", text or "")
    text = re.sub(r"^\s*(?:\d+(?:\.\d+)*\.?|[-•])\s+", " ", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip().lower()


def _blocks(body: str) -> list[str]:
    """The document split into comparable chunks (paragraphs, then sentences-ish runs)."""
    raw = [b.strip() for b in re.split(r"\n\s*\n", body or "") if b.strip()]
    return raw or ([body.strip()] if (body or "").strip() else [])


def _best_match(needle: str, blocks: list[str]) -> tuple[float, str]:
    """Closest block to `needle`, and how close.

    Also tries consecutive runs of blocks: an approved clause is often two paragraphs, and
    comparing it against one of them alone would read as a large edit.
    """
    target = _normalise(needle)
    if not target:
        return 0.0, ""
    best_ratio, best_text = 0.0, ""
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(target)

    for start in range(len(blocks)):
        for end in range(start + 1, min(start + 4, len(blocks)) + 1):
            candidate = "\n\n".join(blocks[start:end])
            matcher.set_seq1(_normalise(candidate))
            # quick_ratio is an upper bound and much cheaper — skip the real comparison when
            # it cannot beat what we already have.
            if matcher.quick_ratio() <= best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio, best_text = ratio, candidate
    return best_ratio, best_text


def diff_summary(approved: str, found: str, *, max_lines: int = 12) -> list[str]:
    """A readable word-level diff, so a reviewer sees the change rather than two paragraphs."""
    before = _normalise(approved).split()
    after = _normalise(found).split()
    out: list[str] = []
    for group in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        tag, i1, i2, j1, j2 = group
        if tag == "equal":
            continue
        if tag in ("replace", "delete"):
            out.append("- " + " ".join(before[i1:i2])[:200])
        if tag in ("replace", "insert"):
            out.append("+ " + " ".join(after[j1:j2])[:200])
        if len(out) >= max_lines:
            out.append("…")
            break
    return out


# ---------------------------------------------------------------------------------------
# Definition
# ---------------------------------------------------------------------------------------


def validate_rules(db: Session, tenant_id: str, rules: list) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules or [], start=1):
        if not isinstance(rule, dict):
            problems.append(f"Rule {index} is not a rule.")
            continue
        key = str(rule.get("clause_key") or "").strip()
        kind = str(rule.get("kind") or "required")
        severity = str(rule.get("severity") or "warning")
        where = key or f"rule {index}"
        if not key:
            problems.append(f"Rule {index} does not name a clause.")
        elif key in seen:
            problems.append(f"{where}: the same clause appears twice.")
        elif clause_service.by_key(db, tenant_id, key) is None:
            problems.append(f"{where}: no such clause in the library.")
        seen.add(key)
        if kind not in RULE_KINDS:
            problems.append(f"{where}: unknown rule kind '{kind}'.")
        if severity not in SEVERITIES:
            problems.append(f"{where}: unknown severity '{severity}'.")
    return problems


def _matches_scope(playbook: models.Playbook, contract: models.Contract) -> bool:
    """Does this playbook apply to this agreement?"""
    if playbook.contract_type and playbook.contract_type != contract.type:
        return False
    when = playbook.applies_when or {}
    value = float(contract.value or 0.0)
    if when.get("min_value") is not None and value < float(when["min_value"]):
        return False
    if when.get("max_value") is not None and value > float(when["max_value"]):
        return False
    if when.get("department") and when["department"] != (contract.department or ""):
        return False
    if when.get("risk_level") and when["risk_level"] != (contract.risk_level or ""):
        return False
    return True


def applicable(db: Session, contract: models.Contract) -> list[models.Playbook]:
    """Every active playbook covering this agreement.

    Plural on purpose: a house-wide policy and a type-specific one both apply, and taking only
    the most specific would silently drop the general rules.
    """
    rows = db.scalars(
        select(models.Playbook)
        .where(models.Playbook.tenant_id == contract.tenant_id,
               models.Playbook.status == "active")
        .order_by(models.Playbook.contract_type.asc(), models.Playbook.name.asc())
    ).all()
    return [p for p in rows if _matches_scope(p, contract)]


# ---------------------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------------------


def review(db: Session, contract: models.Contract) -> dict:
    """Measure the draft against every applicable playbook.

    Returns {ok, checked, findings[], playbooks[]}. A finding is
    {clause_key, title, kind, severity, status, ratio, guidance, diff[]} where `status` is one
    of `missing` | `altered` | `present` | `prohibited`.
    """
    books = applicable(db, contract)
    blocks = _blocks(contract.body or "")
    findings: list[dict] = []
    checked = 0
    seen: set[tuple[str, str]] = set()

    for book in books:
        for rule in book.rules or []:
            if not isinstance(rule, dict):
                continue
            key = str(rule.get("clause_key") or "").strip()
            kind = str(rule.get("kind") or "required")
            if not key or (key, kind) in seen:
                continue          # two playbooks naming the same rule is one finding
            seen.add((key, kind))

            clause = clause_service.by_key(db, contract.tenant_id, key)
            if clause is None:
                continue
            approved = clause_service.approved_body(db, clause)
            if not approved:
                continue          # unapproved clause: nothing authoritative to compare against
            checked += 1

            ratio, found = _best_match(approved, blocks)
            severity = str(rule.get("severity") or "warning")
            base = {
                "clause_key": key, "clause_id": clause.id,
                "title": clause.title or key, "kind": kind, "severity": severity,
                "guidance": str(rule.get("guidance") or clause.guidance or ""),
                "risk_level": clause.risk_level, "ratio": round(ratio, 3),
                "playbook": book.name, "diff": [],
            }

            if kind == "prohibited":
                if ratio >= PRESENT_RATIO:
                    findings.append({**base, "status": "prohibited"})
                continue

            if ratio >= UNCHANGED_RATIO:
                findings.append({**base, "status": "present"})
            elif ratio >= PRESENT_RATIO:
                findings.append({**base, "status": "altered",
                                 "diff": diff_summary(approved, found)})
            else:
                findings.append({**base, "status": "missing"})

    deviations = [f for f in findings
                  if f["status"] in ("missing", "altered", "prohibited")]
    blockers = [f for f in deviations if f["severity"] == "blocker"]
    return {
        "ok": not deviations,
        "checked": checked,
        "deviation_count": len(deviations),
        "blocker_count": len(blockers),
        "findings": findings,
        "playbooks": [{"id": b.id, "name": b.name} for b in books],
    }


def review_and_classify(db: Session, contract: models.Contract, *,
                        actor: models.User | None = None, ip: str = "") -> dict:
    """Review, and classify the agreement non-standard if policy was broken.

    The classification is the point. A deviation that only produces a report is a deviation
    somebody can approve without noticing; one that changes the approval route cannot be.
    """
    from . import workflow_service

    result = review(db, contract)
    if result["blocker_count"]:
        worst = next(f for f in result["findings"]
                     if f["severity"] == "blocker"
                     and f["status"] in ("missing", "altered", "prohibited"))
        workflow_service.mark_non_standard(
            db, contract,
            reason=(f"Playbook deviation: {worst['title']} is {worst['status']} "
                    f"({result['blocker_count']} blocking finding(s))."),
            actor=actor, ip=ip,
        )
        result["classified_non_standard"] = True
    else:
        result["classified_non_standard"] = False
    return result
