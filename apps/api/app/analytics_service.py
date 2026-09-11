"""Metrics: executive KPIs, operational load, compliance posture and MIS trends.

**Where the numbers come from.** Cycle times and stage timings are derived from the audit log,
not from a separate metrics table. That is deliberate: the audit log is the tamper-evident
record of what actually happened, so a cycle time computed from it is defensible in a way that
a number written by whichever code path happened to remember is not. `contract.status_changed`
already carries `{from, to}` and the chain gives it an ordering, which is everything needed.

**Where pre-aggregation genuinely earns its place.** Point-in-time KPIs (what is pending, who
is loaded, what deviates from policy) are grouped queries over indexed columns and stay fast.
The expensive question is the *time series* — "volume by month for ten years, year on year" —
because that is a scan of every agreement ever created, repeated on every dashboard load. So
those, and only those, are rolled into `MetricSnapshot` by a daily beat. Rolling up the rest
would add a refresh dependency and a staleness bug for no gain.

**On honesty in metrics.** Several of these can only be computed for agreements that have
actually reached the relevant state. An "average cycle time" that silently includes in-flight
drafts as zero is worse than no number — so every figure reports the sample it was computed
from, and the API returns that alongside the value.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, playbook_service

#: The statuses that mean "this agreement got over the line".
EXECUTED = ("signed", "active", "expiring", "expired", "renewed", "terminated")

#: What counts as still in the pipeline for bottleneck purposes.
IN_FLIGHT = ("draft", "in_review", "approved", "out_for_signature", "changes_requested")


def _today() -> dt.date:
    return dt.date.today()


def _mean(values: list[float]) -> float | None:
    """None rather than 0 for an empty sample — a zero average reads as "instant"."""
    return round(sum(values) / len(values), 1) if values else None


def _percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile. Medians and p90s survive one pathological agreement in a way
    an average does not, and cycle-time data always has one."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(p / 100 * len(ordered) + 0.5) - 1))
    return round(ordered[index], 1)


# ---------------------------------------------------------------------------------------
# Status history, reconstructed from the audit log
# ---------------------------------------------------------------------------------------


def _status_events(db: Session, tenant_id: str) -> dict[str, list[tuple[dt.datetime, str, str]]]:
    """{contract_id: [(when, from_status, to_status)]}, in chain order.

    One query for the whole workspace rather than per contract: every metric below needs this,
    and doing it per agreement turns a dashboard into a few thousand round trips.
    """
    rows = db.scalars(
        select(models.AuditLog).where(
            models.AuditLog.tenant_id == tenant_id,
            models.AuditLog.action.in_(("contract.status_changed", "contract.submitted",
                                        "contract.created")),
        ).order_by(models.AuditLog.seq.asc(), models.AuditLog.at.asc())
    ).all()

    history: dict[str, list[tuple[dt.datetime, str, str]]] = defaultdict(list)
    for row in rows:
        if not row.object_id:
            continue
        meta = row.meta or {}
        if row.action == "contract.created":
            history[row.object_id].append((row.at, "", "draft"))
        else:
            history[row.object_id].append(
                (row.at, str(meta.get("from") or ""),
                 str(meta.get("to") or ("in_review" if row.action == "contract.submitted" else "")))
            )
    return history


def _first_time_at(events: list[tuple[dt.datetime, str, str]],
                   statuses: tuple[str, ...]) -> dt.datetime | None:
    for when, _from, to in events:
        if to in statuses:
            return when
    return None


# ---------------------------------------------------------------------------------------
# Executive KPIs
# ---------------------------------------------------------------------------------------


def cycle_times(db: Session, tenant_id: str, *, since: dt.date | None = None) -> dict:
    """Days from raised to executed, per agreement type.

    Only agreements that actually reached execution are counted. Including in-flight drafts
    as zero would report a cycle time that improves every time somebody starts a new draft.
    """
    history = _status_events(db, tenant_id)
    contracts = db.scalars(
        select(models.Contract).where(models.Contract.tenant_id == tenant_id)
    ).all()

    by_type: dict[str, list[float]] = defaultdict(list)
    overall: list[float] = []
    excluded = 0

    for contract in contracts:
        events = history.get(contract.id, [])
        executed_at = _first_time_at(events, EXECUTED)
        if executed_at is None:
            excluded += 1
            continue
        raised_at = events[0][0] if events else contract.created_at
        if since and executed_at.date() < since:
            continue
        days = max(0.0, (executed_at - raised_at).total_seconds() / 86400)
        by_type[contract.type or "other"].append(days)
        overall.append(days)

    return {
        "overall": {"mean": _mean(overall), "median": _percentile(overall, 50),
                    "p90": _percentile(overall, 90), "sample": len(overall)},
        "by_type": {
            key: {"mean": _mean(values), "median": _percentile(values, 50),
                  "p90": _percentile(values, 90), "sample": len(values)}
            for key, values in sorted(by_type.items())
        },
        #: Agreements with no execution yet. Reported so nobody mistakes the sample for
        #: the whole repository.
        "still_in_flight": excluded,
    }


def stage_performance(db: Session, tenant_id: str) -> dict:
    """Where approvals actually sit, and whether the SLA was met.

    The bottleneck heatmap the brief asks for is this ordered by mean hours: the stage at the
    top is where agreements wait.
    """
    steps = db.scalars(
        select(models.WorkflowRunStep).where(models.WorkflowRunStep.tenant_id == tenant_id)
    ).all()

    durations: dict[str, list[float]] = defaultdict(list)
    on_time: dict[str, list[bool]] = defaultdict(list)
    waiting: Counter = Counter()
    escalations: Counter = Counter()

    for step in steps:
        name = step.name or f"Stage {step.stage_index + 1}"
        if step.status == "active":
            waiting[name] += 1
        if step.escalated_at is not None:
            escalations[name] += 1
        if step.decided_at and step.activated_at:
            durations[name].append(
                max(0.0, (step.decided_at - step.activated_at).total_seconds() / 3600))
        if step.decided_at and step.due_at:
            on_time[name].append(step.decided_at <= step.due_at)

    stages = []
    for name in sorted(set(durations) | set(waiting) | set(on_time) | set(escalations)):
        decided = on_time.get(name, [])
        stages.append({
            "stage": name,
            "mean_hours": _mean(durations.get(name, [])),
            "p90_hours": _percentile(durations.get(name, []), 90),
            "decided": len(durations.get(name, [])),
            "awaiting": waiting.get(name, 0),
            "escalations": escalations.get(name, 0),
            "sla_adherence": (round(100 * sum(decided) / len(decided), 1) if decided else None),
            "sla_sample": len(decided),
        })

    stages.sort(key=lambda s: (s["mean_hours"] is None, -(s["mean_hours"] or 0)))
    return {"stages": stages,
            "bottleneck": stages[0]["stage"] if stages and stages[0]["mean_hours"] else None}


def renewal_pipeline(db: Session, tenant_id: str, *, today: dt.date | None = None) -> dict:
    """What is coming up for renewal, bucketed the way a renewals meeting runs."""
    day = today or _today()
    buckets = {"overdue": [], "30": [], "60": [], "90": [], "later": []}

    for contract in db.scalars(
        select(models.Contract).where(
            models.Contract.tenant_id == tenant_id,
            models.Contract.status.in_(("active", "signed", "expiring")),
            models.Contract.end_date.is_not(None),
        ).order_by(models.Contract.end_date.asc())
    ).all():
        days = (contract.end_date - day).days
        key = ("overdue" if days < 0 else "30" if days <= 30 else "60" if days <= 60
               else "90" if days <= 90 else "later")
        buckets[key].append({
            "id": contract.id, "reference_no": contract.reference_no,
            "title": contract.title, "counterparty": contract.counterparty,
            "end_date": contract.end_date, "days": days,
            "value": contract.value, "currency": contract.currency,
            "renewal_type": contract.renewal_type,
        })

    return {
        "buckets": {k: v for k, v in buckets.items()},
        "counts": {k: len(v) for k, v in buckets.items()},
        "value_at_risk": round(sum(
            c["value"] for k in ("overdue", "30", "60", "90") for c in buckets[k]), 2),
    }


def escalation_trend(db: Session, tenant_id: str, *, months: int = 12) -> dict:
    """Escalations per month and how long they took to clear.

    Mean time to resolve is measured from escalation to decision — the question being asked is
    "once something escalated, how long did it then take?", not how long the whole step took.
    """
    steps = db.scalars(
        select(models.WorkflowRunStep).where(
            models.WorkflowRunStep.tenant_id == tenant_id,
            models.WorkflowRunStep.escalated_at.is_not(None),
        )
    ).all()

    per_month: Counter = Counter()
    resolution_hours: list[float] = []
    for step in steps:
        per_month[step.escalated_at.strftime("%Y-%m")] += 1
        if step.decided_at:
            resolution_hours.append(
                max(0.0, (step.decided_at - step.escalated_at).total_seconds() / 3600))

    cutoff = (_today().replace(day=1) - dt.timedelta(days=31 * months)).strftime("%Y-%m")
    series = [{"month": m, "count": c}
              for m, c in sorted(per_month.items()) if m >= cutoff]

    return {
        "series": series,
        "total": sum(per_month.values()),
        "mean_resolution_hours": _mean(resolution_hours),
        "resolution_sample": len(resolution_hours),
    }


# ---------------------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------------------


def reviewer_workload(db: Session, tenant_id: str) -> list[dict]:
    """Who is carrying the review load, and who is late.

    Ordered by what is *open*, not by what has been done: the point of this view is to find
    the person about to become a bottleneck, not to rank throughput.
    """
    users = {u.id: u for u in db.scalars(
        select(models.User).where(models.User.tenant_id == tenant_id)).all()}
    steps = db.scalars(
        select(models.WorkflowRunStep).where(models.WorkflowRunStep.tenant_id == tenant_id)
    ).all()

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    stats: dict[str, dict] = defaultdict(
        lambda: {"open": 0, "overdue": 0, "decided": 0, "hours": []})

    for step in steps:
        # A decided step belongs to whoever decided it. An open one belongs to the person it
        # was assigned to — or, where it was routed to a role, to that role's queue. Dropping
        # role-routed steps left this blank on any workspace that routes by role, which is
        # most of them.
        if step.decided_by:
            key = step.decided_by
        elif step.assignee_kind == "user" and step.assignee_value:
            key = step.assignee_value
        elif step.assignee_value:
            key = f"role:{step.assignee_value}"
        else:
            continue
        entry = stats[key]
        if step.status == "active":
            entry["open"] += 1
            if step.due_at and step.due_at < now:
                entry["overdue"] += 1
        if step.decided_at:
            entry["decided"] += 1
            if step.activated_at:
                entry["hours"].append(
                    max(0.0, (step.decided_at - step.activated_at).total_seconds() / 3600))

    out = []
    for key, value in stats.items():
        if key.startswith("role:"):
            # Named as a queue, not as a person: nobody has picked these up yet, and showing
            # them against an individual would invent an assignment the workflow never made.
            role = key[5:]
            out.append({"user_id": "", "name": f"{role.title()} queue", "role": role,
                        "open": value["open"], "overdue": value["overdue"],
                        "decided": value["decided"], "mean_hours": _mean(value["hours"])})
            continue
        out.append({
            "user_id": key,
            "name": users[key].name if key in users else "(unknown)",
            "role": users[key].role if key in users else "",
            "open": value["open"], "overdue": value["overdue"], "decided": value["decided"],
            "mean_hours": _mean(value["hours"]),
        })
    out.sort(key=lambda r: (-r["open"], -r["overdue"], r["name"]))
    return out


def negotiation_effort(db: Session, tenant_id: str) -> dict:
    """How much back-and-forth agreements actually take.

    Redline iterations are counted from the version records a redline leaves behind, and
    "most negotiated clause" from the deviations policy review finds — both are byproducts of
    work already recorded, not a separate thing anyone has to remember to log.
    """
    versions = db.scalars(
        select(models.ContractVersion).where(models.ContractVersion.tenant_id == tenant_id)
    ).all()

    redlines: Counter = Counter()
    imports: Counter = Counter()
    for version in versions:
        summary = version.change_summary or ""
        if summary.startswith("Redline:"):
            redlines[version.contract_id] += 1
        elif "Word import" in summary:
            imports[version.contract_id] += 1

    counts = list(redlines.values())
    contracts = {c.id: c for c in db.scalars(
        select(models.Contract).where(models.Contract.tenant_id == tenant_id)).all()}

    most = [{
        "contract_id": cid, "reference_no": contracts[cid].reference_no if cid in contracts else "",
        "title": contracts[cid].title if cid in contracts else "(deleted)",
        "redlines": n, "counterparty_returns": imports.get(cid, 0),
    } for cid, n in redlines.most_common(10) if cid in contracts]

    return {
        "mean_redline_rounds": _mean([float(c) for c in counts]),
        "max_redline_rounds": max(counts) if counts else 0,
        "contracts_negotiated": len(redlines),
        "counterparty_returns": sum(imports.values()),
        "most_negotiated": most,
    }


def clause_pressure(db: Session, tenant_id: str) -> list[dict]:
    """Which clauses get changed most often across the repository.

    Answers the question a legal team actually wants from a clause library: not "what do we
    have?" but "what do counterparties keep pushing back on?" — which is the list to fix.
    """
    contracts = db.scalars(
        select(models.Contract).where(
            models.Contract.tenant_id == tenant_id,
            models.Contract.status.in_(EXECUTED + IN_FLIGHT),
        )
    ).all()

    altered: Counter = Counter()
    missing: Counter = Counter()
    used: Counter = Counter()
    titles: dict[str, str] = {}

    for contract in contracts:
        for entry in (contract.included_clauses or []):
            if entry.get("key"):
                used[entry["key"]] += 1
                titles.setdefault(entry["key"], entry.get("title") or entry["key"])
        review = playbook_service.review(db, contract)
        for finding in review["findings"]:
            titles.setdefault(finding["clause_key"], finding["title"])
            if finding["status"] == "altered":
                altered[finding["clause_key"]] += 1
            elif finding["status"] == "missing":
                missing[finding["clause_key"]] += 1

    keys = set(altered) | set(missing) | set(used)
    out = [{
        "clause_key": key,
        "title": titles.get(key, key),
        "used": used.get(key, 0),
        "altered": altered.get(key, 0),
        "missing": missing.get(key, 0),
        "pressure": altered.get(key, 0) + missing.get(key, 0),
    } for key in keys]
    out.sort(key=lambda r: (-r["pressure"], -r["used"], r["title"]))
    return out


# ---------------------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------------------


def compliance_posture(db: Session, tenant_id: str, *, today: dt.date | None = None) -> dict:
    """The compliance report: deviations, gaps, and what is being chased.

    Runs the real policy engine over live agreements rather than reading a cached verdict —
    a compliance number computed from a stale snapshot is the one number that must not be.
    """
    day = today or _today()
    contracts = db.scalars(
        select(models.Contract).where(
            models.Contract.tenant_id == tenant_id,
            models.Contract.status.in_(EXECUTED + IN_FLIGHT),
        )
    ).all()

    deviating: list[dict] = []
    blocker_count = missing_mandatory = checked = 0

    for contract in contracts:
        review = playbook_service.review(db, contract)
        if review["checked"]:
            checked += 1
        if not review["deviation_count"]:
            continue
        blocker_count += review["blocker_count"]
        missing_mandatory += sum(
            1 for f in review["findings"]
            if f["status"] == "missing" and f["kind"] == "required")
        deviating.append({
            "contract_id": contract.id, "reference_no": contract.reference_no,
            "title": contract.title, "status": contract.status,
            "deviations": review["deviation_count"], "blockers": review["blocker_count"],
            "findings": [f["title"] for f in review["findings"]
                         if f["status"] in ("missing", "altered", "prohibited")][:6],
        })
    deviating.sort(key=lambda r: (-r["blockers"], -r["deviations"]))

    overdue_obligations = db.scalar(select(func.count(models.Obligation.id)).where(
        models.Obligation.tenant_id == tenant_id,
        models.Obligation.status.in_(("pending", "overdue")),
        models.Obligation.due_date.is_not(None),
        models.Obligation.due_date < day,
    )) or 0

    non_standard = db.scalar(select(func.count(models.Contract.id)).where(
        models.Contract.tenant_id == tenant_id,
        models.Contract.is_non_standard.is_(True),
    )) or 0

    return {
        "checked": checked,
        "compliant": checked - len(deviating),
        "deviating": len(deviating),
        "blockers": blocker_count,
        "missing_mandatory_clauses": missing_mandatory,
        "non_standard": non_standard,
        "overdue_obligations": overdue_obligations,
        "worst": deviating[:20],
    }


# ---------------------------------------------------------------------------------------
# MIS: trends and segmentation
# ---------------------------------------------------------------------------------------


def volume_trend(db: Session, tenant_id: str, *, granularity: str = "month",
                 months: int = 24) -> dict:
    """Agreements raised and executed over time, plus the same period a year earlier.

    Year-on-year is aligned by period key rather than by offset in the series, so a missing
    month does not silently shift the comparison by one.
    """
    if granularity not in ("day", "week", "month"):
        raise ValueError(f"Unknown granularity '{granularity}'.")

    def _key(when: dt.datetime | dt.date) -> str:
        day = when.date() if isinstance(when, dt.datetime) else when
        if granularity == "day":
            return day.isoformat()
        if granularity == "week":
            iso = day.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        return day.strftime("%Y-%m")

    history = _status_events(db, tenant_id)
    raised: Counter = Counter()
    executed: Counter = Counter()

    for contract in db.scalars(
        select(models.Contract).where(models.Contract.tenant_id == tenant_id)
    ).all():
        raised[_key(contract.created_at)] += 1
        executed_at = _first_time_at(history.get(contract.id, []), EXECUTED)
        if executed_at:
            executed[_key(executed_at)] += 1

    keys = sorted(set(raised) | set(executed))[-(months if granularity == "month" else 120):]
    series = []
    for key in keys:
        prior = None
        if granularity == "month" and len(key) == 7:
            prior = f"{int(key[:4]) - 1}{key[4:]}"
        series.append({
            "period": key,
            "raised": raised.get(key, 0),
            "executed": executed.get(key, 0),
            "raised_year_ago": raised.get(prior) if prior else None,
        })
    return {"granularity": granularity, "series": series}


def segmentation(db: Session, tenant_id: str) -> dict:
    """Volume and value cut the ways the RFI asks for: department, region, type, entity, status.

    Region comes from the party record, which is the point of having one — a free-text
    counterparty cannot be segmented at all.
    """
    contracts = db.scalars(
        select(models.Contract).where(models.Contract.tenant_id == tenant_id)
    ).all()
    parties = {p.id: p for p in db.scalars(
        select(models.Party).where(models.Party.tenant_id == tenant_id)).all()}
    departments = {d.id: d.name for d in db.scalars(
        select(models.Department).where(models.Department.tenant_id == tenant_id)).all()}

    def _bucket(label_of) -> list[dict]:  # type: ignore[no-untyped-def]
        counts: Counter = Counter()
        values: Counter = Counter()
        for contract in contracts:
            label = label_of(contract) or "Unassigned"
            counts[label] += 1
            values[label] += float(contract.value or 0)
        return [{"label": k, "count": v, "value": round(values[k], 2)}
                for k, v in counts.most_common()]

    return {
        "by_department": _bucket(
            lambda c: departments.get(c.department_id) or c.department),
        "by_region": _bucket(
            lambda c: parties[c.party_id].region if c.party_id in parties else ""),
        "by_entity_type": _bucket(
            lambda c: parties[c.party_id].entity_type if c.party_id in parties else ""),
        "by_type": _bucket(lambda c: (c.type or "other").replace("_", " ").title()),
        "by_status": _bucket(lambda c: (c.status or "").replace("_", " ").title()),
        "by_currency": _bucket(lambda c: c.currency),
    }


def most_requested_types(db: Session, tenant_id: str, *, limit: int = 10) -> list[dict]:
    """Which agreement types get raised most — the RFI's "most-requested agreement types"."""
    rows = db.execute(
        select(models.Contract.type, func.count(models.Contract.id))
        .where(models.Contract.tenant_id == tenant_id)
        .group_by(models.Contract.type)
        .order_by(func.count(models.Contract.id).desc())
        .limit(limit)
    ).all()
    return [{"type": t or "other", "count": n} for t, n in rows]


# ---------------------------------------------------------------------------------------
# Role dashboards
# ---------------------------------------------------------------------------------------


def my_dashboard(db: Session, user: models.User, *, today: dt.date | None = None) -> dict:
    """"My tasks", "escalations", "renewals", "reviews due today" for one person.

    One call rather than four: this is the first screen after login, and four round trips is
    the difference between a dashboard that feels instant and one that flickers.
    """
    day = today or _today()
    now = dt.datetime.combine(day, dt.time.max)
    tenant_id = user.tenant_id

    steps = db.scalars(
        select(models.WorkflowRunStep).where(
            models.WorkflowRunStep.tenant_id == tenant_id,
            models.WorkflowRunStep.status == "active",
        )
    ).all()
    mine = [s for s in steps
            if (s.assignee_kind == "user" and s.assignee_value == user.id)
            or (s.assignee_kind == "role" and s.assignee_value == user.role)]

    contracts = {c.id: c for c in db.scalars(
        select(models.Contract).where(models.Contract.tenant_id == tenant_id)).all()}
    runs = {r.id: r for r in db.scalars(
        select(models.WorkflowRun).where(models.WorkflowRun.tenant_id == tenant_id)).all()}

    def _step_row(step: models.WorkflowRunStep) -> dict:
        run = runs.get(step.run_id)
        contract = contracts.get(run.contract_id) if run else None
        return {
            "step_id": step.id, "name": step.name,
            "contract_id": contract.id if contract else "",
            "reference_no": contract.reference_no if contract else "",
            "title": contract.title if contract else "(deleted)",
            "due_at": step.due_at,
            "overdue": bool(step.due_at and step.due_at < now),
            "escalated": step.escalated_at is not None,
        }

    obligations = db.scalars(
        select(models.Obligation).where(
            models.Obligation.tenant_id == tenant_id,
            models.Obligation.owner_id == user.id,
            models.Obligation.status.in_(("pending", "overdue")),
        ).order_by(models.Obligation.due_date.asc())
    ).all()

    owned_renewals = [
        c for c in contracts.values()
        if c.owner_id == user.id and c.end_date
        and c.status in ("active", "signed", "expiring")
        and (c.end_date - day).days <= 90
    ]
    owned_renewals.sort(key=lambda c: c.end_date)

    return {
        "reviews": [_step_row(s) for s in mine],
        "reviews_due_today": [
            _step_row(s) for s in mine
            if s.due_at and s.due_at.date() <= day
        ],
        "escalations": [_step_row(s) for s in steps if s.escalated_at is not None
                        and s.escalated_to == user.id],
        "obligations": [{
            "id": o.id, "title": o.title, "due_date": o.due_date,
            "contract_id": o.contract_id,
            "reference_no": contracts[o.contract_id].reference_no
            if o.contract_id in contracts else "",
            "overdue": bool(o.due_date and o.due_date < day),
        } for o in obligations],
        "renewals": [{
            "id": c.id, "reference_no": c.reference_no, "title": c.title,
            "end_date": c.end_date, "days": (c.end_date - day).days,
            "renewal_type": c.renewal_type,
        } for c in owned_renewals],
        "counts": {
            "reviews": len(mine),
            "overdue_reviews": sum(1 for s in mine if s.due_at and s.due_at < now),
            "obligations": len(obligations),
            "overdue_obligations": sum(1 for o in obligations
                                       if o.due_date and o.due_date < day),
            "renewals": len(owned_renewals),
        },
    }


def executive_summary(db: Session, tenant_id: str, *, today: dt.date | None = None) -> dict:
    """The headline set, in one call, for the executive dashboard."""
    return {
        "cycle_times": cycle_times(db, tenant_id),
        "stages": stage_performance(db, tenant_id),
        "renewals": renewal_pipeline(db, tenant_id, today=today),
        "escalations": escalation_trend(db, tenant_id),
        "compliance": compliance_posture(db, tenant_id, today=today),
        "most_requested": most_requested_types(db, tenant_id),
    }
