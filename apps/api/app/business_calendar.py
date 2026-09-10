"""The business calendar the SLA clock runs on.

An SLA measured in wall-clock hours is wrong for a bank. A review raised at 16:00 on the
Friday before Eid is not overdue on Saturday morning, and telling a reviewer it is destroys
trust in the escalation feed within a week — after which everyone ignores it and the whole
mechanism is decoration.

So "48-hour SLA" means 48 **working** hours: skipping weekends, non-working hours, and the
public holidays an administrator has entered. Configurable because the working week is not
universal — Pakistan's is Monday–Friday but the Gulf branches of the same group are not, and
the RFP asks for configurable working days and hours explicitly.

Weekday numbering follows `date.weekday()`: Monday is 0, Sunday is 6.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from .config import settings


def working_days() -> set[int]:
    """Configured working weekdays. Defaults to Mon–Fri."""
    raw = (settings.business_working_days or "0,1,2,3,4").split(",")
    days = {int(d.strip()) for d in raw if d.strip().isdigit()}
    return {d for d in days if 0 <= d <= 6} or {0, 1, 2, 3, 4}


def _holidays(db, tenant_id: str, start: dt.date, end: dt.date) -> set[dt.date]:
    """Holiday dates in a window. Fetched once per calculation rather than per day — an SLA
    sweep over a few hundred open steps would otherwise be a few thousand queries."""
    if db is None:
        return set()
    from . import models

    rows = db.scalars(
        select(models.Holiday.day).where(
            models.Holiday.tenant_id == tenant_id,
            models.Holiday.day >= start,
            models.Holiday.day <= end,
        )
    ).all()
    return set(rows)


def is_working_day(day: dt.date, *, holidays: set[dt.date], days: set[int] | None = None) -> bool:
    return day.weekday() in (days or working_days()) and day not in holidays


def add_business_hours(db, tenant_id: str, start: dt.datetime, hours: float) -> dt.datetime:
    """`start` plus `hours` of working time.

    Walks forward in whole working days, consuming the working window of each. Deliberately
    iterative rather than arithmetic: a closed-form calculation has to special-case the
    partial first day, holidays and a start outside working hours, and gets one of them wrong.
    A loop over a few dozen days is not the bottleneck in an SLA sweep — the database round
    trip is, and that is already hoisted out.
    """
    if hours <= 0:
        return start

    day_start = settings.business_day_start_hour
    day_end = settings.business_day_end_hour
    if day_end <= day_start:
        # Misconfigured; fall back to wall-clock rather than looping forever.
        return start + dt.timedelta(hours=hours)

    hours_per_day = day_end - day_start
    days = working_days()
    # Generous window: `hours` working hours can never span more than this many calendar days.
    horizon = int(hours / hours_per_day) + 30
    holidays = _holidays(db, tenant_id, start.date(), start.date() + dt.timedelta(days=horizon))

    remaining = float(hours)
    cursor = start

    for _ in range(horizon * 2):
        if not is_working_day(cursor.date(), holidays=holidays, days=days):
            cursor = dt.datetime.combine(
                cursor.date() + dt.timedelta(days=1), dt.time(hour=day_start)
            )
            continue

        window_open = cursor.replace(hour=day_start, minute=0, second=0, microsecond=0)
        window_close = cursor.replace(hour=day_end, minute=0, second=0, microsecond=0)

        if cursor < window_open:
            cursor = window_open
        if cursor >= window_close:
            cursor = dt.datetime.combine(
                cursor.date() + dt.timedelta(days=1), dt.time(hour=day_start)
            )
            continue

        available = (window_close - cursor).total_seconds() / 3600.0
        if remaining <= available:
            return cursor + dt.timedelta(hours=remaining)
        remaining -= available
        cursor = dt.datetime.combine(
            cursor.date() + dt.timedelta(days=1), dt.time(hour=day_start)
        )

    # Should be unreachable; returning the cursor beats looping.
    return cursor


def business_hours_between(db, tenant_id: str, start: dt.datetime, end: dt.datetime) -> float:
    """Working hours elapsed between two instants — the numerator for cycle-time metrics.

    Reporting "this approval took 62 hours" when 40 of them were a weekend makes the whole
    analytics layer misleading, so the same calendar is used for measurement as for deadlines.
    """
    if end <= start:
        return 0.0

    day_start = settings.business_day_start_hour
    day_end = settings.business_day_end_hour
    if day_end <= day_start:
        return (end - start).total_seconds() / 3600.0

    days = working_days()
    holidays = _holidays(db, tenant_id, start.date(), end.date())

    total = 0.0
    cursor = start.date()
    while cursor <= end.date():
        if is_working_day(cursor, holidays=holidays, days=days):
            window_open = dt.datetime.combine(cursor, dt.time(hour=day_start))
            window_close = dt.datetime.combine(cursor, dt.time(hour=day_end))
            overlap_start = max(start, window_open)
            overlap_end = min(end, window_close)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds() / 3600.0
        cursor += dt.timedelta(days=1)
    return round(total, 3)


def next_working_moment(db, tenant_id: str, at: dt.datetime) -> dt.datetime:
    """`at` if it is inside working hours, otherwise the next moment that is. Used so a
    reminder raised overnight lands when someone is actually there to act on it."""
    return add_business_hours(db, tenant_id, at, 0.0001)
