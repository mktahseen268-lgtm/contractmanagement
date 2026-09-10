"""Contextual help and the knowledge base (Phase 9, items 1-2).

Both live in the database, not in the front-end bundle, for one reason: the requirement is that
Legal can fix the wording without a deploy. Help text that is wrong is worse than no help,
because it is read as authoritative — and a correction that waits on a release train stays wrong
for a fortnight.

The shipped copy in `app/content/help.<locale>.json` is a **seed, not a source of truth**. It
fills gaps on first start and after an upgrade adds new keys; it never overwrites a topic
somebody has edited. Getting that backwards would silently revert the legal team's corrections
on every deploy, and they would find out by being asked about wording they had already fixed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models
from .audit import record

CONTENT_DIR = Path(__file__).parent / "content"

#: Locales the product ships strings for. Adding one is a content task, not a code change.
SUPPORTED_LOCALES = ("en", "ur")
DEFAULT_LOCALE = "en"

CATEGORIES = ("quickstart", "playbook", "faq", "release_note")


class ContentError(ValueError):
    """Bad input from the editor. Routers map to 400."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def normalise_locale(locale: str) -> str:
    """`ur-PK` and `UR` both mean `ur`. An unknown locale falls back rather than 404s."""
    base = (locale or "").strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LOCALES else DEFAULT_LOCALE


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug[:120] or "untitled"


# ---------------------------------------------------------------------------------------
# Contextual help
# ---------------------------------------------------------------------------------------


def _seed_file(locale: str) -> list[dict]:
    path = CONTENT_DIR / f"help.{locale}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A malformed content file must not stop the application booting. Help missing is a
        # degraded screen; the app refusing to start is an outage.
        return []
    return [t for t in data.get("topics", []) if t.get("key")]


def seed_help(db: Session, tenant_id: str, locale: str = DEFAULT_LOCALE) -> int:
    """Insert any shipped topic this tenant does not have yet. Returns how many were added.

    Idempotent, and deliberately additive-only: an upgrade that introduces new help keys picks
    them up, and nothing that has been edited is touched.
    """
    locale = normalise_locale(locale)
    existing = set(db.scalars(select(models.HelpTopic.key).where(
        models.HelpTopic.tenant_id == tenant_id,
        models.HelpTopic.locale == locale)).all())

    added = 0
    for topic in _seed_file(locale):
        if topic["key"] in existing:
            continue
        db.add(models.HelpTopic(
            tenant_id=tenant_id, key=topic["key"], locale=locale,
            title=topic.get("title", "")[:200], body=topic.get("body", ""),
            surface=topic.get("surface", "")[:80], is_default=True))
        added += 1
    if added:
        db.flush()
    return added


def help_map(db: Session, tenant_id: str, locale: str = DEFAULT_LOCALE,
             surface: str = "") -> dict[str, dict]:
    """Every topic for a locale, keyed by help key — one request per screen, not per field.

    Falls back to English per *topic*, not per request. A half-translated locale should show the
    translated topics it has and English for the rest; showing the whole screen in English
    because one topic is missing throws away work that was done.
    """
    locale = normalise_locale(locale)
    conditions = [models.HelpTopic.tenant_id == tenant_id]
    if surface:
        conditions.append(models.HelpTopic.surface == surface)

    rows = db.scalars(select(models.HelpTopic).where(
        *conditions,
        or_(models.HelpTopic.locale == locale,
            models.HelpTopic.locale == DEFAULT_LOCALE))).all()

    out: dict[str, dict] = {}
    for row in rows:
        if row.locale == DEFAULT_LOCALE and row.key in out:
            continue                                   # a translation already won
        if row.locale != locale and row.key in out:
            continue
        entry = {"key": row.key, "title": row.title, "body": row.body,
                 "surface": row.surface, "locale": row.locale,
                 "is_translated": row.locale == locale}
        if row.locale == locale or row.key not in out:
            out[row.key] = entry
    return out


def update_help(db: Session, tenant_id: str, key: str, *, actor: models.User,
                title: str | None = None, body: str | None = None,
                locale: str = DEFAULT_LOCALE, surface: str | None = None,
                ip: str = "") -> models.HelpTopic:
    """Edit a topic, or create it if this locale does not have it yet."""
    locale = normalise_locale(locale)
    key = (key or "").strip()
    if not key:
        raise ContentError("A help topic needs a key.")

    row = db.scalar(select(models.HelpTopic).where(
        models.HelpTopic.tenant_id == tenant_id,
        models.HelpTopic.key == key,
        models.HelpTopic.locale == locale))
    if row is None:
        row = models.HelpTopic(tenant_id=tenant_id, key=key, locale=locale)
        db.add(row)

    if title is not None:
        row.title = title[:200]
    if body is not None:
        row.body = body
    if surface is not None:
        row.surface = surface[:80]
    # No longer the shipped wording, so the seed must never touch it again.
    row.is_default = False
    row.updated_by = actor.id
    db.flush()

    record(db, tenant_id=tenant_id, action="help.updated", actor=actor,
           object_type="help_topic", object_id=row.id, object_label=key, ip=ip,
           meta={"locale": locale})
    return row


def reset_help(db: Session, tenant_id: str, key: str, *, actor: models.User,
               locale: str = DEFAULT_LOCALE, ip: str = "") -> models.HelpTopic:
    """Put a topic back to the shipped wording. The way out of a bad edit."""
    locale = normalise_locale(locale)
    shipped = next((t for t in _seed_file(locale) if t["key"] == key), None)
    if shipped is None:
        raise ContentError("There is no shipped wording for that topic to go back to.")

    row = db.scalar(select(models.HelpTopic).where(
        models.HelpTopic.tenant_id == tenant_id,
        models.HelpTopic.key == key,
        models.HelpTopic.locale == locale))
    if row is None:
        raise ContentError("That help topic does not exist.")

    row.title = shipped.get("title", "")[:200]
    row.body = shipped.get("body", "")
    row.surface = shipped.get("surface", "")[:80]
    row.is_default = True
    row.updated_by = actor.id
    db.flush()

    record(db, tenant_id=tenant_id, action="help.reset", actor=actor,
           object_type="help_topic", object_id=row.id, object_label=key, ip=ip,
           meta={"locale": locale})
    return row


# ---------------------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------------------


def list_articles(db: Session, tenant_id: str, *, locale: str = DEFAULT_LOCALE,
                  category: str = "", query: str = "", role: str = "",
                  include_unpublished: bool = False) -> list[models.KnowledgeArticle]:
    locale = normalise_locale(locale)
    conditions = [models.KnowledgeArticle.tenant_id == tenant_id]
    if not include_unpublished:
        conditions.append(models.KnowledgeArticle.is_published.is_(True))
    if category:
        conditions.append(models.KnowledgeArticle.category == category)

    if query:
        # ILIKE, matching the rest of the product's search. ponytail: swap for the tsvector
        # index in T-11 when the corpus is large enough to notice — a knowledge base is a few
        # hundred rows, and a GIN index on it would be ceremony.
        like = f"%{query.strip()}%"
        conditions.append(or_(
            models.KnowledgeArticle.title.ilike(like),
            models.KnowledgeArticle.summary.ilike(like),
            models.KnowledgeArticle.body.ilike(like)))

    rows = list(db.scalars(select(models.KnowledgeArticle).where(*conditions).order_by(
        models.KnowledgeArticle.sort_order.asc(),
        models.KnowledgeArticle.title.asc())).all())

    # Prefer the requested locale, fall back per article — same reasoning as `help_map`.
    by_slug: dict[str, models.KnowledgeArticle] = {}
    for row in rows:
        if row.locale not in (locale, DEFAULT_LOCALE):
            continue
        current = by_slug.get(row.slug)
        if current is None or (row.locale == locale and current.locale != locale):
            by_slug[row.slug] = row

    articles = list(by_slug.values())
    if role:
        # An empty audience means everyone. A role filter that hid those would show a new user
        # an empty knowledge base, which is the opposite of what it is for.
        articles = [a for a in articles if not a.audience_roles or role in a.audience_roles]
    articles.sort(key=lambda a: (a.sort_order, a.title.lower()))
    return articles


def get_article(db: Session, tenant_id: str, slug: str, *,
                locale: str = DEFAULT_LOCALE) -> models.KnowledgeArticle | None:
    locale = normalise_locale(locale)
    rows = list(db.scalars(select(models.KnowledgeArticle).where(
        models.KnowledgeArticle.tenant_id == tenant_id,
        models.KnowledgeArticle.slug == slug)).all())
    if not rows:
        return None
    return (next((r for r in rows if r.locale == locale), None)
            or next((r for r in rows if r.locale == DEFAULT_LOCALE), None)
            or rows[0])


def mark_read(db: Session, article: models.KnowledgeArticle) -> None:
    """Count a view.

    An UPDATE with an expression rather than a read-modify-write, so two people opening the
    same article at once do not lose one of the counts. It is only a view counter, but the
    correct version is the same length as the racy one.
    """
    article.view_count = models.KnowledgeArticle.view_count + 1
    db.flush()


def save_article(db: Session, tenant_id: str, *, actor: models.User,
                 title: str, body: str, slug: str = "", summary: str = "",
                 category: str = "faq", locale: str = DEFAULT_LOCALE,
                 tags: list | None = None, audience_roles: list | None = None,
                 video_file_id: str | None = None, video_duration_s: int = 0,
                 sort_order: int = 0, is_published: bool = True,
                 article_id: str = "", ip: str = "") -> models.KnowledgeArticle:
    """Create or update an article."""
    if not (title or "").strip():
        raise ContentError("An article needs a title.")
    if category not in CATEGORIES:
        raise ContentError(f"Category must be one of: {', '.join(CATEGORIES)}.")
    locale = normalise_locale(locale)

    row = None
    if article_id:
        row = db.get(models.KnowledgeArticle, article_id)
        if row is None or row.tenant_id != tenant_id:
            raise ContentError("That article does not exist.")

    target_slug = slugify(slug or title)
    clash = db.scalar(select(models.KnowledgeArticle).where(
        models.KnowledgeArticle.tenant_id == tenant_id,
        models.KnowledgeArticle.slug == target_slug,
        models.KnowledgeArticle.locale == locale))
    if clash is not None and (row is None or clash.id != row.id):
        raise ContentError(f"An article with the address '{target_slug}' already exists.")

    if row is None:
        row = models.KnowledgeArticle(tenant_id=tenant_id, created_by=actor.id)
        db.add(row)

    row.slug = target_slug
    row.locale = locale
    row.title = title.strip()[:240]
    row.summary = (summary or "").strip()[:500]
    row.body = body or ""
    row.category = category
    row.tags = list(tags or [])
    row.audience_roles = list(audience_roles or [])
    row.video_file_id = video_file_id or None
    row.video_duration_s = max(0, int(video_duration_s or 0))
    row.sort_order = int(sort_order or 0)
    row.is_published = bool(is_published)
    db.flush()

    record(db, tenant_id=tenant_id, action="kb.saved", actor=actor,
           object_type="knowledge_article", object_id=row.id, object_label=row.title, ip=ip,
           meta={"slug": row.slug, "locale": locale, "published": row.is_published})
    return row


def delete_article(db: Session, tenant_id: str, article_id: str, *, actor: models.User,
                   ip: str = "") -> None:
    row = db.get(models.KnowledgeArticle, article_id)
    if row is None or row.tenant_id != tenant_id:
        raise ContentError("That article does not exist.")
    title, slug = row.title, row.slug
    db.delete(row)
    db.flush()
    record(db, tenant_id=tenant_id, action="kb.deleted", actor=actor,
           object_type="knowledge_article", object_id=article_id, object_label=title, ip=ip,
           meta={"slug": slug})


def categories_summary(db: Session, tenant_id: str, locale: str = DEFAULT_LOCALE) -> list[dict]:
    """Counts per category, for the knowledge-base landing page."""
    locale = normalise_locale(locale)
    rows = db.execute(
        select(models.KnowledgeArticle.category, func.count())
        .where(models.KnowledgeArticle.tenant_id == tenant_id,
               models.KnowledgeArticle.is_published.is_(True),
               models.KnowledgeArticle.locale.in_({locale, DEFAULT_LOCALE}))
        .group_by(models.KnowledgeArticle.category)).all()
    counts = dict(rows)
    # Every known category is listed, including the empty ones — an absent category reads as
    # "this product has no playbooks", when it means nobody has written one yet.
    return [{"category": c, "count": int(counts.get(c, 0))} for c in CATEGORIES]


def _content_file(name: str) -> dict:
    """Load a shipped content file. A malformed one degrades the feature, never the boot."""
    path = CONTENT_DIR / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def seed_knowledge(db: Session, tenant_id: str, locale: str = DEFAULT_LOCALE) -> int:
    """Insert the shipped articles this tenant does not have. Gap-fill only.

    A knowledge base that ships empty stays empty — nobody writes the first article, and the
    feature gets judged on a blank page.
    """
    locale = normalise_locale(locale)
    existing = set(db.scalars(select(models.KnowledgeArticle.slug).where(
        models.KnowledgeArticle.tenant_id == tenant_id,
        models.KnowledgeArticle.locale == locale)).all())

    added = 0
    for article in _content_file(f"knowledge.{locale}.json").get("articles", []):
        slug = article.get("slug")
        if not slug or slug in existing:
            continue
        db.add(models.KnowledgeArticle(
            tenant_id=tenant_id, slug=slug, locale=locale,
            title=article.get("title", "")[:240],
            summary=article.get("summary", "")[:500],
            body=article.get("body", ""),
            category=article.get("category", "faq"),
            tags=list(article.get("tags") or []),
            audience_roles=list(article.get("audience_roles") or []),
            sort_order=int(article.get("sort_order") or 0),
            created_by="system"))
        added += 1
    if added:
        db.flush()
    return added


def seed_courses(db: Session, tenant_id: str) -> int:
    """Insert the shipped courses this tenant does not have. Gap-fill only.

    The answer key goes into the database and stays there — `training_service.quiz_for` strips
    it before the quiz is served.
    """
    existing = set(db.scalars(select(models.TrainingCourse.slug).where(
        models.TrainingCourse.tenant_id == tenant_id)).all())

    added = 0
    for course in _content_file("courses.en.json").get("courses", []):
        slug = course.get("slug")
        if not slug or slug in existing:
            continue
        modules = list(course.get("modules") or [])
        db.add(models.TrainingCourse(
            tenant_id=tenant_id, slug=slug,
            title=course.get("title", "")[:240],
            summary=course.get("summary", "")[:500],
            for_roles=list(course.get("for_roles") or []),
            modules=modules,
            quiz=list(course.get("quiz") or []),
            pass_mark=int(course.get("pass_mark") or 80),
            certificate_valid_months=int(course.get("certificate_valid_months") or 12),
            is_required=bool(course.get("is_required")),
            sort_order=int(course.get("sort_order") or 0),
            estimated_minutes=sum(int(m.get("minutes") or 0) for m in modules)))
        added += 1
    if added:
        db.flush()
    return added


def seed_all(db: Session, tenant_id: str, locale: str = DEFAULT_LOCALE) -> dict:
    """Everything a new workspace should start with. Safe to call on every boot."""
    return {
        "help": seed_help(db, tenant_id, locale),
        "articles": seed_knowledge(db, tenant_id, locale),
        "courses": seed_courses(db, tenant_id),
    }
