"""Comments, @mentions, and the internal-only privacy boundary.

Two RFI requirements meet here:

  §3.3  the user department sees a **consolidated** view of every internal stakeholder's
        comments and proposed amendments before anything goes to the counterparty;
  §3.4  reviewers can @mention each other, with a "mentions me" inbox filter.

The privacy flag is the part that matters most. A Legal note reading "do not concede clause 7
below 8%" reaching the counterparty is unrecoverable — you cannot un-send it, and it changes
the commercial position of the negotiation. So `internal_only` is enforced in **one** function,
`visible_to()`, which every read path goes through, and the external surfaces are asserted
against it in tests. A second implementation of this rule is a second chance to get it wrong.

The rule itself is deliberately blunt: **external audiences see nothing marked internal**.
There is no "internal but shareable with this particular counterparty" tier, because that is
the kind of nuance that gets misjudged under time pressure.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from . import audit, models

#: `@name`, `@first.last`, `@first last` (up to two words). Kept conservative — an over-eager
#: pattern turns an email address in a comment into a mention of a user who is not involved.
_MENTION_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z][\w.'-]*(?:\s+[A-Za-z][\w.'-]*)?)")

#: Audiences a comment can be read by. `internal` is staff; everything else is outside.
INTERNAL_AUDIENCE = "internal"
EXTERNAL_AUDIENCES = ("counterparty", "signer", "public", "external")


def visible_to(comments: list[models.Comment], *, audience: str) -> list[models.Comment]:
    """Filter comments for an audience. **The single enforcement point for `internal_only`.**

    Every path that shows comments outside the workspace must call this. It takes a list rather
    than building a query so the same rule covers already-loaded objects, serialised payloads
    and exports — the places a query-level filter tends to get bypassed.
    """
    if audience == INTERNAL_AUDIENCE:
        return list(comments)
    return [c for c in comments if not c.internal_only]


def assert_external_safe(comments: list[models.Comment]) -> None:
    """Raise if anything internal is about to leave the building.

    A belt-and-braces check for code paths that assemble an external payload by hand. Cheap,
    and the failure it prevents is not recoverable.
    """
    leaked = [c.id for c in comments if c.internal_only]
    if leaked:
        raise RuntimeError(
            f"Refusing to expose internal-only comments externally: {', '.join(leaked)}"
        )


# ---------------------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------------------


def extract_mentions(db, tenant_id: str, body: str) -> list[models.User]:
    """Resolve @mentions in a comment body to real users in this tenant.

    Matches on name and on the email local part, longest candidate first so "@Ali Raza"
    resolves to Ali Raza rather than to a different Ali. Unresolvable mentions are simply not
    mentions — silently ignoring them beats inventing a recipient.
    """
    if not body or "@" not in body:
        return []

    # A mention may be one token (`@ayesha.khan`) or two (`@Ayesha Khan`), and the pattern
    # cannot tell which without knowing the user list — `@ayesha.khan please` would otherwise
    # capture "ayesha.khan please". So offer BOTH readings and let the match decide.
    candidates: set[str] = set()
    for match in _MENTION_PATTERN.finditer(body):
        whole = match.group(1).strip().lower()
        candidates.add(whole)
        candidates.add(whole.split()[0])
    candidates.discard("")
    if not candidates:
        return []

    users = db.scalars(
        select(models.User).where(
            models.User.tenant_id == tenant_id, models.User.is_active.is_(True)
        )
    ).all()

    matched: dict[str, models.User] = {}
    for user in users:
        name = (user.name or "").strip().lower()
        local = (user.email or "").split("@")[0].strip().lower()
        for candidate in candidates:
            if candidate and candidate in (name, local):
                matched[user.id] = user
            elif candidate and name.startswith(candidate) and len(candidate) >= 4:
                # "@Ali" matching "Ali Raza" — only when it is specific enough to be meant.
                matched.setdefault(user.id, user)
    return list(matched.values())


def create(db, *, contract: models.Contract, author: models.User, body: str,
           internal_only: bool = False, kind: str = "comment", department: str = "",
           anchor_start: int | None = None, anchor_end: int | None = None,
           ip: str = "") -> models.Comment:
    """Add a comment, resolve its mentions, and notify the people named. Caller commits."""
    comment = models.Comment(
        tenant_id=contract.tenant_id, contract_id=contract.id,
        author_id=author.id, author_name=author.name,
        body=(body or "").strip(),
        internal_only=bool(internal_only),
        kind=kind if kind in ("comment", "amendment") else "comment",
        department=(department or author.department or "")[:100],
        anchor_start=anchor_start, anchor_end=anchor_end,
    )
    db.add(comment)
    db.flush()

    mentioned = [u for u in extract_mentions(db, contract.tenant_id, comment.body)
                 if u.id != author.id]
    for user in mentioned:
        db.add(models.Mention(
            tenant_id=contract.tenant_id, comment_id=comment.id, contract_id=contract.id,
            mentioned_user_id=user.id, mentioned_by=author.id, mentioned_by_name=author.name,
            # Carried from the comment, so an internal-only mention can never surface in an
            # external view via the mentions feed.
            internal_only=comment.internal_only,
        ))
        db.add(models.Notification(
            tenant_id=contract.tenant_id, user_id=user.id, type="contract.mentioned",
            title=f"{author.name} mentioned you",
            body=f'On "{contract.title}": {comment.body[:140]}',
            object_type="contract", object_id=contract.id,
        ))

    audit.record(
        db, tenant_id=contract.tenant_id,
        action="contract.amendment_proposed" if comment.kind == "amendment" else "contract.commented",
        actor=author, object_type="contract", object_id=contract.id,
        object_label=contract.title, ip=ip,
        meta={
            "comment_id": comment.id, "internal_only": comment.internal_only,
            "kind": comment.kind, "department": comment.department,
            "mentions": [{"id": u.id, "name": u.name} for u in mentioned],
        },
    )
    return comment


def mentions_for_user(db, tenant_id: str, user_id: str, *, unread_only: bool = False,
                      limit: int = 100) -> list[models.Mention]:
    """The "mentions me" inbox filter (RFI §3.4)."""
    stmt = select(models.Mention).where(
        models.Mention.tenant_id == tenant_id,
        models.Mention.mentioned_user_id == user_id,
    )
    if unread_only:
        stmt = stmt.where(models.Mention.read_at.is_(None))
    return list(db.scalars(
        stmt.order_by(models.Mention.created_at.desc()).limit(limit)
    ).all())


def unread_mention_count(db, tenant_id: str, user_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(models.Mention).where(
            models.Mention.tenant_id == tenant_id,
            models.Mention.mentioned_user_id == user_id,
            models.Mention.read_at.is_(None),
        )
    ) or 0


def mark_mentions_read(db, tenant_id: str, user_id: str,
                       mention_ids: list[str] | None = None) -> int:
    import datetime as dt

    stmt = select(models.Mention).where(
        models.Mention.tenant_id == tenant_id,
        models.Mention.mentioned_user_id == user_id,
        models.Mention.read_at.is_(None),
    )
    if mention_ids:
        stmt = stmt.where(models.Mention.id.in_(mention_ids))
    rows = db.scalars(stmt).all()
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for row in rows:
        row.read_at = now
    return len(rows)


# ---------------------------------------------------------------------------------------
# Consolidated review view (RFI §3.3)
# ---------------------------------------------------------------------------------------


def consolidated_review(db, contract: models.Contract, *,
                        audience: str = INTERNAL_AUDIENCE) -> dict:
    """Every stakeholder's comments and proposed amendments in one view, grouped by function.

    The screen the user department reads before deciding what goes back to the counterparty.
    Grouped by department because that is the question actually being asked — "what does Legal
    say, what does Finance say" — not "what happened in chronological order".
    """
    comments = list(db.scalars(
        select(models.Comment)
        .where(models.Comment.contract_id == contract.id)
        .order_by(models.Comment.created_at.asc())
    ).all())
    comments = visible_to(comments, audience=audience)

    groups: dict[str, list[models.Comment]] = {}
    for c in comments:
        groups.setdefault(c.department or "Unassigned", []).append(c)

    return {
        "contract_id": contract.id,
        "audience": audience,
        "total": len(comments),
        "internal_only_count": sum(1 for c in comments if c.internal_only),
        "amendments": sum(1 for c in comments if c.kind == "amendment"),
        "groups": [
            {
                "department": department,
                "comments": rows,
                "amendments": sum(1 for c in rows if c.kind == "amendment"),
                "unresolved": sum(1 for c in rows if not c.resolved),
            }
            for department, rows in sorted(groups.items())
        ],
    }


# ---------------------------------------------------------------------------------------
# Client-facing capability (RFI §3.5)
# ---------------------------------------------------------------------------------------


def can_share_externally(user: models.User) -> bool:
    """Only DFS/BBCORP coordinators may transmit anything to the counterparty.

    A capability rather than a role, because it cuts across roles: a Legal reviewer is senior
    but is deliberately not client-facing. Owners and admins retain it so a workspace cannot
    lock itself out.
    """
    return bool(user.is_client_facing) or user.role in ("owner", "admin")


def assert_can_share(user: models.User) -> None:
    if not can_share_externally(user):
        raise PermissionError(
            "Only client-facing coordinators can send anything to the counterparty. "
            "Add your comments internally and ask a coordinator to transmit."
        )
