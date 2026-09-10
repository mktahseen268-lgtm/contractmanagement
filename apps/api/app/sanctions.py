"""Sanctions screening against OFAC, UN, EU and HMT lists.

**The lists live locally.** The RFP forbids a runtime dependency on a foreign-hosted service,
and screening is exactly where that constraint bites: a screening call that fails open because
a US endpoint was unreachable is a control that does not exist. So list snapshots are imported
into `sanctions_entries` by an operator (or a scheduled job inside the network) and every
screen is a local query. The snapshot's date is recorded and surfaced, because a screen
against a list nobody has refreshed for eight months is a different fact from a current one.

**Matching is fuzzy and it says why.** Sanctions lists carry transliterated names, so exact
matching finds almost nothing — "Mohammed", "Muhammad" and "Mohamad" are the same person.
Matching too loosely instead buries the analyst in noise until they stop reading. So each hit
carries a score and the reason it matched, and the threshold is configuration.

**A hit never blocks silently.** It raises a review item a human clears or confirms, and the
decision is audited. Automatic rejection on a fuzzy name match would strand legitimate
counterparties with no recourse and no record of why.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
import unicodedata

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models
from .audit import record

#: Recognised list sources.
SOURCES = ("OFAC", "UN", "EU", "HMT", "LOCAL")

#: At or above this a name is reported as a possible match. Below it, nothing is shown.
# ponytail: one global threshold. Per-list tuning if a real screening run shows one source's
# transliteration conventions producing systematically more noise than the others.
MATCH_THRESHOLD = 0.85

#: At or above this the match is strong enough to call "probable" rather than "possible".
STRONG_THRESHOLD = 0.95

#: Words that carry no identity and would otherwise inflate every score.
_NOISE = {
    "mr", "mrs", "ms", "dr", "the", "of", "and", "co", "company", "limited", "ltd", "llc",
    "inc", "corporation", "corp", "trading", "general", "international", "group", "holdings",
    "est", "establishment", "sons", "brothers", "bros",
}


class SanctionsError(ValueError):
    """Refused screening operation. Routers map to 400."""


def normalise(name: str) -> str:
    """A comparable form: unaccented, lower case, noise words dropped.

    Unicode is folded to ASCII because sanctions lists and customer records transliterate
    differently — "Ünal" in one and "Unal" in the other is the same person, and a byte
    comparison says otherwise.
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s]", " ", ascii_only.lower())
    words = [w for w in cleaned.split() if w and w not in _NOISE]
    return " ".join(words)


def search_key(name: str, aliases=()) -> str:
    """The blob the candidate query matches against: the name and every alias, normalised.

    Aliases have to be in here. Sanctions entries are routinely listed under a formal
    registered name with the trading name only as an alias — narrowing candidates on the
    primary name alone means an alias-only match is never even scored, which is a screening
    system that silently misses the case it exists for.
    """
    parts = [normalise(name)] + [normalise(str(a)) for a in (aliases or [])]
    return " | ".join(p for p in parts if p)


def _tokens(name: str) -> set[str]:
    return set(normalise(name).split())


def score(query: str, candidate: str) -> float:
    """0..1 similarity, taking the better of whole-string and token-overlap.

    Both are needed. Whole-string similarity handles a misspelling; token overlap handles a
    reordering or a dropped middle name, which is the common case in transliterated records
    and which sequence comparison alone scores far too low.
    """
    a, b = normalise(query), normalise(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    sequence = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()

    tokens_a, tokens_b = _tokens(query), _tokens(candidate)
    if tokens_a and tokens_b:
        shared = tokens_a & tokens_b
        # Against the smaller set: "Ali Hassan" inside "Ali Hassan Al Mansouri" should score
        # high, because the shorter name being a subset is exactly the case that matters.
        overlap = len(shared) / min(len(tokens_a), len(tokens_b))
        # A single shared common token is not a match on its own.
        if len(shared) == 1 and min(len(tokens_a), len(tokens_b)) > 1:
            overlap *= 0.6
    else:
        overlap = 0.0

    return round(max(sequence, overlap), 3)


def screen_name(db: Session, tenant_id: str, name: str, *,
                threshold: float = MATCH_THRESHOLD) -> list[dict]:
    """Possible matches for one name, best first.

    Candidates are narrowed in SQL by first token before scoring in Python: scoring every row
    of a sanctions list on every screen is the difference between milliseconds and minutes
    once the lists are real.
    """
    tokens = _tokens(name)
    if not tokens:
        return []

    conditions = [models.SanctionsEntry.name_key.like(f"%{token}%") for token in tokens]
    candidates = db.scalars(
        select(models.SanctionsEntry).where(
            models.SanctionsEntry.is_active.is_(True),
            or_(*conditions),
        )
    ).all()

    hits = []
    for entry in candidates:
        best = score(name, entry.name)
        matched_on = "name"
        for alias in (entry.aliases or []):
            alias_score = score(name, str(alias))
            if alias_score > best:
                best, matched_on = alias_score, f"alias '{alias}'"
        if best >= threshold:
            hits.append({
                "entry_id": entry.id,
                "name": entry.name,
                "source": entry.source,
                "list_name": entry.list_name,
                "programme": entry.programme,
                "entity_type": entry.entity_type,
                "country": entry.country,
                "score": best,
                "confidence": "probable" if best >= STRONG_THRESHOLD else "possible",
                "matched_on": matched_on,
                "reference": entry.reference,
                # ISO string, not a date: this dict is persisted into a JSON column, and a
                # date object fails on write. Pydantic parses it back to a date on the way out.
                "snapshot_date": entry.snapshot_date.isoformat() if entry.snapshot_date else None,
            })

    hits.sort(key=lambda h: -h["score"])
    return hits


def screen_party(db: Session, party: models.Party, *, actor: models.User | None = None,
                 threshold: float = MATCH_THRESHOLD, ip: str = "") -> models.SanctionsScreening:
    """Screen a party and file the result, whether or not anything matched.

    A clean screen is recorded too: "we checked and found nothing on this date" is the fact an
    auditor asks for, and it cannot be reconstructed from an absence of records.
    """
    hits = screen_name(db, party.tenant_id, party.name, threshold=threshold)
    snapshot = latest_snapshot(db)

    screening = models.SanctionsScreening(
        tenant_id=party.tenant_id, party_id=party.id, party_name=party.name,
        hits=hits, hit_count=len(hits),
        status="review" if hits else "clear",
        threshold=threshold,
        list_snapshot_date=snapshot,
        screened_by=actor.id if actor else "",
    )
    db.add(screening)
    db.flush()

    record(db, tenant_id=party.tenant_id,
           action="party.sanctions_hit" if hits else "party.sanctions_clear",
           actor=actor, object_type="party", object_id=party.id, object_label=party.name,
           ip=ip,
           meta={"screening_id": screening.id, "hits": len(hits),
                 "top": hits[0]["name"] if hits else "",
                 "snapshot_date": str(snapshot or ""),
                 "threshold": threshold})
    return screening


def decide(db: Session, screening: models.SanctionsScreening, *, actor: models.User,
           cleared: bool, note: str, ip: str = "") -> models.SanctionsScreening:
    """Record an analyst's decision on a hit.

    A note is required either way. "Cleared" with no reason is indistinguishable from
    "somebody clicked through it", and that distinction is the entire point of a review queue.
    """
    if screening.status != "review":
        raise SanctionsError("This screening has already been decided.")
    if not note.strip():
        raise SanctionsError("A decision needs a note explaining it.")

    screening.status = "cleared" if cleared else "confirmed"
    screening.decision_note = note.strip()[:1000]
    screening.decided_by = actor.id
    screening.decided_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    party = db.get(models.Party, screening.party_id)
    if party is not None and not cleared:
        # A confirmed match is not a note on a file — it has to stop the party being used.
        party.is_active = False
        party.kyc_status = "rejected"
        party.kyc_note = f"Sanctions match confirmed: {note.strip()[:400]}"

    record(db, tenant_id=screening.tenant_id, action="party.sanctions_decided", actor=actor,
           object_type="party", object_id=screening.party_id,
           object_label=screening.party_name, ip=ip,
           meta={"screening_id": screening.id,
                 "decision": screening.status, "note": note[:200]})
    return screening


def queue(db: Session, tenant_id: str, *, status: str = "review") -> list[models.SanctionsScreening]:
    """The analyst's work queue, oldest first — a hit that has waited longest is the one
    holding somebody's onboarding up."""
    stmt = select(models.SanctionsScreening).where(
        models.SanctionsScreening.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(models.SanctionsScreening.status == status)
    return list(db.scalars(stmt.order_by(models.SanctionsScreening.created_at.asc())).all())


# ---------------------------------------------------------------------------------------
# List snapshots
# ---------------------------------------------------------------------------------------


def import_entries(db: Session, source: str, entries: list[dict], *,
                   snapshot_date: dt.date | None = None, list_name: str = "",
                   actor: models.User | None = None, ip: str = "") -> dict:
    """Load a list snapshot, replacing the previous one from that source.

    Replacement rather than merge: a sanctions list is a statement about a moment, and merging
    an old snapshot into a new one would silently keep delisted people on it — which produces
    false positives that an analyst then has to clear, repeatedly, forever.
    """
    if source not in SOURCES:
        raise SanctionsError(f"Unknown sanctions source '{source}'.")
    day = snapshot_date or dt.date.today()

    superseded = 0
    for existing in db.scalars(
        select(models.SanctionsEntry).where(
            models.SanctionsEntry.source == source,
            models.SanctionsEntry.is_active.is_(True),
        )
    ).all():
        existing.is_active = False
        superseded += 1

    added = 0
    for raw in entries:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        db.add(models.SanctionsEntry(
            source=source, list_name=list_name or source,
            name=name[:400],
            name_key=search_key(name, raw.get("aliases") or [])[:400],
            aliases=[str(a) for a in (raw.get("aliases") or [])],
            entity_type=str(raw.get("entity_type") or "unknown")[:30],
            country=str(raw.get("country") or "")[:100],
            programme=str(raw.get("programme") or "")[:200],
            reference=str(raw.get("reference") or "")[:100],
            snapshot_date=day, is_active=True,
        ))
        added += 1
    db.flush()

    if actor is not None:
        record(db, tenant_id=actor.tenant_id, action="sanctions.list_imported", actor=actor,
               object_type="sanctions_list", object_label=f"{source} {day}", ip=ip,
               meta={"source": source, "added": added, "superseded": superseded,
                     "snapshot_date": str(day)})
    return {"source": source, "added": added, "superseded": superseded,
            "snapshot_date": day}


def latest_snapshot(db: Session) -> dt.date | None:
    """The oldest active snapshot across all sources.

    Oldest, not newest, on purpose: the screen is only as current as its stalest list, and
    reporting the freshest one would overstate how good the check was.
    """
    rows = db.execute(
        select(models.SanctionsEntry.source, func.max(models.SanctionsEntry.snapshot_date))
        .where(models.SanctionsEntry.is_active.is_(True))
        .group_by(models.SanctionsEntry.source)
    ).all()
    dates = [d for _s, d in rows if d]
    return min(dates) if dates else None


def snapshot_status(db: Session, *, today: dt.date | None = None,
                    stale_after_days: int = 30) -> dict:
    """Per-source freshness, and whether anything has gone stale.

    Surfaced because a screen against a list nobody has refreshed for eight months is a
    different fact from a current one, and the UI has to be able to say so.
    """
    day = today or dt.date.today()
    rows = db.execute(
        select(models.SanctionsEntry.source,
               func.max(models.SanctionsEntry.snapshot_date),
               func.count(models.SanctionsEntry.id))
        .where(models.SanctionsEntry.is_active.is_(True))
        .group_by(models.SanctionsEntry.source)
    ).all()

    sources = []
    for source, snapshot, count in rows:
        age = (day - snapshot).days if snapshot else None
        sources.append({
            "source": source, "snapshot_date": snapshot, "entries": count,
            "age_days": age, "stale": age is not None and age > stale_after_days,
        })
    sources.sort(key=lambda s: s["source"])
    return {
        "sources": sources,
        "loaded": bool(sources),
        "oldest": min((s["snapshot_date"] for s in sources if s["snapshot_date"]),
                      default=None),
        "any_stale": any(s["stale"] for s in sources),
    }
