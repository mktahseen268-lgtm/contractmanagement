"""The training hub (Phase 9, item 3).

MMBL scores "Training Mechanism" at 8% and requires onsite training for at least fifteen
resources. Onsite training happens once; the people who attended move on, change role, or forget.
This is the durable half of that answer — the thing still there in eighteen months when a new
joiner needs what the fifteen were taught.

Three decisions worth stating, because each one is the difference between a training record that
means something and a checkbox:

1. **The answer key never leaves the server.** `quiz_for` strips it. A quiz whose answers ship to
   the browser certifies that somebody opened developer tools.
2. **Certificates expire.** A certificate that is valid forever stops being evidence of anything
   the moment the process it covers changes. `certificate_valid_months` is per course.
3. **Attendance is recorded separately from registration.** "Fifteen people were trained" is a
   question about who turned up, and a register of who *intended* to come cannot answer it.
"""

from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .audit import record

#: Below this, a "score" is noise: with three questions, one lucky guess is 33 points.
MIN_QUIZ_QUESTIONS = 3


class TrainingError(ValueError):
    """Bad input or a refused action. Routers map to 400."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _add_months(when: dt.datetime, months: int) -> dt.datetime:
    """Calendar months without pulling in `dateutil`.

    Clamps the day, so a certificate earned on 31 January expires on 28 February rather than
    silently rolling into March — an expiry that drifts later than the policy allows is the
    wrong direction to be wrong in.
    """
    month_index = when.month - 1 + months
    year = when.year + month_index // 12
    month = month_index % 12 + 1
    day = min(when.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                         else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return when.replace(year=year, month=month, day=day)


# ---------------------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------------------


def list_courses(db: Session, tenant_id: str, *, role: str = "",
                 include_unpublished: bool = False) -> list[models.TrainingCourse]:
    conditions = [models.TrainingCourse.tenant_id == tenant_id]
    if not include_unpublished:
        conditions.append(models.TrainingCourse.is_published.is_(True))
    courses = list(db.scalars(select(models.TrainingCourse).where(*conditions).order_by(
        models.TrainingCourse.sort_order.asc(),
        models.TrainingCourse.title.asc())).all())
    if role:
        # No audience means everyone — see the same rule in `content_service.list_articles`.
        courses = [c for c in courses if not c.for_roles or role in c.for_roles]
    return courses


def get_course(db: Session, tenant_id: str, course_id_or_slug: str) -> models.TrainingCourse | None:
    row = db.get(models.TrainingCourse, course_id_or_slug)
    if row is not None and row.tenant_id == tenant_id:
        return row
    return db.scalar(select(models.TrainingCourse).where(
        models.TrainingCourse.tenant_id == tenant_id,
        models.TrainingCourse.slug == course_id_or_slug))


def save_course(db: Session, tenant_id: str, *, actor: models.User, title: str,
                slug: str = "", summary: str = "", for_roles: list | None = None,
                modules: list | None = None, quiz: list | None = None,
                pass_mark: int = 80, certificate_valid_months: int = 12,
                is_required: bool = False, is_published: bool = True,
                sort_order: int = 0, course_id: str = "",
                ip: str = "") -> models.TrainingCourse:
    """Create or update a course. Validates the quiz shape — a malformed question would
    otherwise fail at marking time, after somebody has already sat the course."""
    from .content_service import slugify

    if not (title or "").strip():
        raise TrainingError("A course needs a title.")
    if not 1 <= int(pass_mark) <= 100:
        raise TrainingError("The pass mark must be between 1 and 100.")

    quiz = list(quiz or [])
    if quiz:
        if len(quiz) < MIN_QUIZ_QUESTIONS:
            raise TrainingError(
                f"A quiz needs at least {MIN_QUIZ_QUESTIONS} questions to mean anything.")
        for index, question in enumerate(quiz, start=1):
            options = question.get("options") or []
            if not question.get("q"):
                raise TrainingError(f"Question {index} has no text.")
            if len(options) < 2:
                raise TrainingError(f"Question {index} needs at least two options.")
            answer = question.get("answer")
            if not isinstance(answer, int) or not 0 <= answer < len(options):
                raise TrainingError(f"Question {index} does not point at one of its options.")

    row = None
    if course_id:
        row = db.get(models.TrainingCourse, course_id)
        if row is None or row.tenant_id != tenant_id:
            raise TrainingError("That course does not exist.")

    target_slug = slugify(slug or title)
    clash = db.scalar(select(models.TrainingCourse).where(
        models.TrainingCourse.tenant_id == tenant_id,
        models.TrainingCourse.slug == target_slug))
    if clash is not None and (row is None or clash.id != row.id):
        raise TrainingError(f"A course with the address '{target_slug}' already exists.")

    if row is None:
        row = models.TrainingCourse(tenant_id=tenant_id)
        db.add(row)

    modules = list(modules or [])
    row.slug = target_slug
    row.title = title.strip()[:240]
    row.summary = (summary or "").strip()[:500]
    row.for_roles = list(for_roles or [])
    row.modules = modules
    row.quiz = quiz
    row.pass_mark = int(pass_mark)
    row.certificate_valid_months = max(0, int(certificate_valid_months or 0))
    row.is_required = bool(is_required)
    row.is_published = bool(is_published)
    row.sort_order = int(sort_order or 0)
    row.estimated_minutes = sum(int(m.get("minutes") or 0) for m in modules)
    db.flush()

    record(db, tenant_id=tenant_id, action="training.course_saved", actor=actor,
           object_type="training_course", object_id=row.id, object_label=row.title, ip=ip,
           meta={"modules": len(modules), "questions": len(quiz),
                 "published": row.is_published})
    return row


def quiz_for(course: models.TrainingCourse) -> list[dict]:
    """The quiz as the candidate may see it — **without the answer key**.

    The one thing in this module that must not be got wrong. `answer` and `why` are the marking
    scheme; serving them alongside the questions would make every certificate meaningless and
    nobody would notice until an auditor asked how the quiz was marked.
    """
    return [
        {"q": q.get("q", ""), "options": list(q.get("options") or [])}
        for q in (course.quiz or [])
    ]


# ---------------------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------------------


def progress_for(db: Session, tenant_id: str, user_id: str,
                 course_id: str) -> models.TrainingProgress:
    """The user's progress row, created on first sight."""
    row = db.scalar(select(models.TrainingProgress).where(
        models.TrainingProgress.tenant_id == tenant_id,
        models.TrainingProgress.user_id == user_id,
        models.TrainingProgress.course_id == course_id))
    if row is None:
        row = models.TrainingProgress(
            tenant_id=tenant_id, user_id=user_id, course_id=course_id)
        db.add(row)
        db.flush()
    return row


def complete_module(db: Session, tenant_id: str, user: models.User, course: models.TrainingCourse,
                    module_index: int) -> models.TrainingProgress:
    if not 0 <= module_index < len(course.modules or []):
        raise TrainingError("That module is not part of this course.")

    row = progress_for(db, tenant_id, user.id, course.id)
    if row.started_at is None:
        row.started_at = _now()
    done = set(row.completed_modules or [])
    done.add(module_index)
    # Reassigned rather than mutated: SQLAlchemy does not see an in-place change to a JSON
    # column, so the update would be dropped at commit with no error anywhere.
    row.completed_modules = sorted(done)
    if row.status == "not_started":
        row.status = "in_progress"
    db.flush()
    return row


def submit_quiz(db: Session, tenant_id: str, user: models.User, course: models.TrainingCourse,
                answers: list[int], *, ip: str = "") -> dict:
    """Mark an attempt. Returns the score, the outcome, and per-question feedback.

    Feedback is only returned for questions that were wrong, and only after the attempt is
    recorded. Someone who passed does not need the answer key, and someone who failed needs to
    know which part to go back to — not a printable copy of the marking scheme.
    """
    questions = course.quiz or []
    if not questions:
        raise TrainingError("This course has no quiz.")
    if len(answers) != len(questions):
        raise TrainingError(
            f"This quiz has {len(questions)} questions and {len(answers)} were answered.")

    correct = 0
    feedback: list[dict] = []
    for index, (question, given) in enumerate(zip(questions, answers)):
        expected = question.get("answer")
        if given == expected:
            correct += 1
        else:
            feedback.append({
                "index": index,
                "question": question.get("q", ""),
                "why": question.get("why", ""),
            })

    score = round(correct * 100 / len(questions))
    passed = score >= course.pass_mark

    row = progress_for(db, tenant_id, user.id, course.id)
    if row.started_at is None:
        row.started_at = _now()
    row.attempts += 1
    row.last_score = score
    row.best_score = max(row.best_score, score)

    if passed:
        # A repeat pass refreshes the validity window but keeps the original certificate
        # number: it is the same certification, renewed. A new number each time would make the
        # training register look like more distinct certifications than were actually earned.
        row.status = "passed"
        row.passed_at = _now()
        if not row.certificate_no:
            row.certificate_no = f"CM-{secrets.token_hex(4).upper()}"
        row.expires_at = (_add_months(row.passed_at, course.certificate_valid_months)
                          if course.certificate_valid_months else None)
    elif row.status != "passed":
        # A failed retake never revokes a certificate already earned. Losing a valid
        # certification by trying to improve on it would teach people not to retake.
        row.status = "failed"
    db.flush()

    record(db, tenant_id=tenant_id, action="training.quiz_submitted", actor=user,
           object_type="training_course", object_id=course.id, object_label=course.title, ip=ip,
           meta={"score": score, "passed": passed, "attempt": row.attempts,
                 "pass_mark": course.pass_mark})

    return {
        "score": score,
        "passed": passed,
        "pass_mark": course.pass_mark,
        "correct": correct,
        "total": len(questions),
        "attempt": row.attempts,
        "certificate_no": row.certificate_no if passed else "",
        "expires_at": row.expires_at,
        "review": feedback,
    }


def certificate_state(progress: models.TrainingProgress | None) -> str:
    """`none` | `valid` | `expired`. Expiry is computed, never stored as a status — a status
    would need a sweep to keep it true, and a certificate that stays 'valid' because the sweep
    did not run is exactly the failure this is meant to prevent."""
    if progress is None or progress.status != "passed" or not progress.certificate_no:
        return "none"
    if progress.expires_at and progress.expires_at < _now():
        return "expired"
    return "valid"


def my_training(db: Session, tenant_id: str, user: models.User) -> dict:
    """The hub as one user sees it."""
    courses = list_courses(db, tenant_id, role=user.role)
    rows = {p.course_id: p for p in db.scalars(select(models.TrainingProgress).where(
        models.TrainingProgress.tenant_id == tenant_id,
        models.TrainingProgress.user_id == user.id)).all()}

    items = []
    for course in courses:
        progress = rows.get(course.id)
        total = len(course.modules or [])
        done = len(progress.completed_modules or []) if progress else 0
        items.append({
            "course": course,
            "progress": progress,
            "modules_total": total,
            "modules_done": done,
            "percent": round(done * 100 / total) if total else 0,
            "certificate": certificate_state(progress),
        })

    required = [i for i in items if i["course"].is_required]
    return {
        "items": items,
        "required_total": len(required),
        "required_done": sum(1 for i in required if i["certificate"] == "valid"),
    }


def completion_report(db: Session, tenant_id: str) -> dict:
    """Who has been trained — the question the RFP actually asks.

    Counts people, not enrolments, and counts *valid* certificates. Someone whose certificate
    lapsed last month has not been trained on the current process, and reporting them as trained
    is how a training register becomes fiction.
    """
    courses = {c.id: c for c in list_courses(db, tenant_id, include_unpublished=True)}
    users = {u.id: u for u in db.scalars(select(models.User).where(
        models.User.tenant_id == tenant_id, models.User.is_active.is_(True))).all()}
    rows = db.scalars(select(models.TrainingProgress).where(
        models.TrainingProgress.tenant_id == tenant_id)).all()

    per_course: dict[str, dict] = {
        cid: {"course_id": cid, "title": c.title, "required": c.is_required,
              "passed": 0, "expired": 0, "in_progress": 0}
        for cid, c in courses.items()}
    certified_people: set[str] = set()

    for row in rows:
        bucket = per_course.get(row.course_id)
        if bucket is None or row.user_id not in users:
            continue                                   # deleted course or departed user
        state = certificate_state(row)
        if state == "valid":
            bucket["passed"] += 1
            certified_people.add(row.user_id)
        elif state == "expired":
            bucket["expired"] += 1
        elif row.status == "in_progress":
            bucket["in_progress"] += 1

    return {
        "active_users": len(users),
        "people_with_a_valid_certificate": len(certified_people),
        "courses": sorted(per_course.values(), key=lambda c: c["title"].lower()),
    }


# ---------------------------------------------------------------------------------------
# Live sessions — the webinar calendar, and the onsite record
# ---------------------------------------------------------------------------------------


def list_sessions(db: Session, tenant_id: str, *, upcoming_only: bool = False,
                  limit: int = 100) -> list[models.TrainingSession]:
    conditions = [models.TrainingSession.tenant_id == tenant_id]
    if upcoming_only:
        conditions.append(models.TrainingSession.starts_at >= _now())
        conditions.append(models.TrainingSession.is_cancelled.is_(False))
    return list(db.scalars(select(models.TrainingSession).where(*conditions).order_by(
        models.TrainingSession.starts_at.asc()).limit(limit)).all())


def save_session(db: Session, tenant_id: str, *, actor: models.User, title: str,
                 starts_at: dt.datetime, kind: str = "webinar", description: str = "",
                 duration_minutes: int = 60, location: str = "", trainer: str = "",
                 capacity: int = 0, session_id: str = "",
                 ip: str = "") -> models.TrainingSession:
    if not (title or "").strip():
        raise TrainingError("A session needs a title.")
    if kind not in ("webinar", "onsite", "office_hours"):
        raise TrainingError("Kind must be webinar, onsite or office_hours.")

    row = None
    if session_id:
        row = db.get(models.TrainingSession, session_id)
        if row is None or row.tenant_id != tenant_id:
            raise TrainingError("That session does not exist.")
    if row is None:
        row = models.TrainingSession(tenant_id=tenant_id)
        db.add(row)

    row.title = title.strip()[:240]
    row.description = description or ""
    row.kind = kind
    row.starts_at = starts_at
    row.duration_minutes = max(1, int(duration_minutes or 60))
    row.location = (location or "")[:300]
    row.trainer = (trainer or "")[:200]
    row.capacity = max(0, int(capacity or 0))
    db.flush()

    record(db, tenant_id=tenant_id, action="training.session_saved", actor=actor,
           object_type="training_session", object_id=row.id, object_label=row.title, ip=ip,
           meta={"kind": kind, "starts_at": starts_at.isoformat()})
    return row


def register(db: Session, session: models.TrainingSession, user: models.User) -> models.TrainingSession:
    if session.is_cancelled:
        raise TrainingError("That session was cancelled.")
    if session.starts_at < _now():
        raise TrainingError("That session has already run.")

    registered = list(session.registered_user_ids or [])
    if user.id in registered:
        return session
    if session.capacity and len(registered) >= session.capacity:
        raise TrainingError("That session is full.")
    session.registered_user_ids = [*registered, user.id]
    db.flush()
    return session


def unregister(db: Session, session: models.TrainingSession,
               user: models.User) -> models.TrainingSession:
    session.registered_user_ids = [
        uid for uid in (session.registered_user_ids or []) if uid != user.id]
    db.flush()
    return session


def mark_attendance(db: Session, tenant_id: str, session: models.TrainingSession,
                    user_ids: list[str], *, actor: models.User,
                    ip: str = "") -> models.TrainingSession:
    """Record who actually attended.

    Kept apart from registration on purpose. "Have fifteen resources been trained" is a question
    about attendance, and a register of who intended to come cannot answer it — which is the
    difference between a training report and a claim.
    """
    known = set(db.scalars(select(models.User.id).where(
        models.User.tenant_id == tenant_id,
        models.User.id.in_(user_ids or []))).all())
    unknown = [uid for uid in (user_ids or []) if uid not in known]
    if unknown:
        raise TrainingError("Some of those people are not in this workspace.")

    session.attended_user_ids = sorted(known)
    db.flush()
    record(db, tenant_id=tenant_id, action="training.attendance_recorded", actor=actor,
           object_type="training_session", object_id=session.id, object_label=session.title,
           ip=ip, meta={"attended": len(known), "registered": len(session.registered_user_ids or [])})
    return session


def attendance_summary(db: Session, tenant_id: str) -> dict:
    """Totals for the training plan: sessions run, and how many distinct people attended one."""
    sessions = db.scalars(select(models.TrainingSession).where(
        models.TrainingSession.tenant_id == tenant_id,
        models.TrainingSession.is_cancelled.is_(False))).all()
    now = _now()
    attended: set[str] = set()
    delivered = 0
    for session in sessions:
        if session.starts_at <= now:
            delivered += 1
        attended.update(session.attended_user_ids or [])
    return {
        "sessions_scheduled": len(sessions),
        "sessions_delivered": delivered,
        "people_attended": len(attended),
    }


def count_courses(db: Session, tenant_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(models.TrainingCourse).where(
        models.TrainingCourse.tenant_id == tenant_id)) or 0)
