"""Adoption: contextual help, the knowledge base, training, and guided actions (Phase 9).

One router because these are one concern — helping somebody get the job done — and splitting
them into four would produce four files that only ever get opened together.

The read endpoints are deliberately cheap and unguarded beyond authentication: help text and
quick-start guides are not secrets, and a permission check on a tooltip is a permission check
that will be worked around by hard-coding the tooltip.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from .. import access_control as ac
from .. import content_service, guidance, models, schemas, training_service
from ..access_control import AccessDenied
from ..content_service import ContentError
from ..database import get_db
from ..deps import client_ip, get_current_user
from ..training_service import TrainingError

router = APIRouter(tags=["adoption"])


def _guard(action, *args, **kwargs):  # type: ignore[no-untyped-def]
    try:
        return action(*args, **kwargs)
    except AccessDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except (ContentError, TrainingError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _locale(request: Request, override: str = "") -> str:
    """The locale to answer in.

    An explicit query parameter wins; otherwise `Accept-Language`. Falls back to English rather
    than failing — a missing translation is a degraded screen, not an error.
    """
    if override:
        return content_service.normalise_locale(override)
    header = request.headers.get("accept-language", "")
    first = header.split(",")[0].strip() if header else ""
    return content_service.normalise_locale(first)


# ---------------------------------------------------------------------------------------
# Contextual help
# ---------------------------------------------------------------------------------------


@router.get("/help", response_model=dict[str, schemas.HelpTopicOut])
def get_help(request: Request, surface: str = "", locale: str = "",
             db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)) -> dict:
    """Every help topic for a screen, in one request.

    One call per screen rather than one per field: a tooltip that arrives after the user has
    already moved on is not help.
    """
    resolved = _locale(request, locale)
    # Seed on first read rather than at signup. A tenant created before this feature existed
    # would otherwise have no help at all, and nobody would think to run a backfill.
    if content_service.seed_help(db, user.tenant_id, resolved):
        db.commit()
    return content_service.help_map(db, user.tenant_id, resolved, surface=surface)


@router.get("/help/admin", response_model=list[schemas.HelpAdminOut])
def list_help_topics(request: Request, locale: str = "", db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> list[models.HelpTopic]:
    """Every topic as stored, for the editor."""
    from sqlalchemy import select

    _guard(ac.require, db, user, "content.manage")
    resolved = _locale(request, locale)
    content_service.seed_help(db, user.tenant_id, resolved)
    db.commit()
    return list(db.scalars(select(models.HelpTopic).where(
        models.HelpTopic.tenant_id == user.tenant_id,
        models.HelpTopic.locale == resolved).order_by(
        models.HelpTopic.surface.asc(), models.HelpTopic.key.asc())).all())


@router.put("/help/{key}", response_model=schemas.HelpAdminOut)
def put_help_topic(key: str, data: schemas.HelpTopicIn, request: Request,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> models.HelpTopic:
    """Edit the wording. This is the endpoint the whole 'no deploy' requirement rests on."""
    _guard(ac.require, db, user, "content.manage")
    row = _guard(content_service.update_help, db, user.tenant_id, key, actor=user,
                 title=data.title, body=data.body, surface=data.surface,
                 locale=data.locale, ip=client_ip(request))
    db.commit()
    db.refresh(row)
    return row


@router.post("/help/{key}/reset", response_model=schemas.HelpAdminOut)
def reset_help_topic(key: str, request: Request, locale: str = "en",
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)) -> models.HelpTopic:
    """Put a topic back to the shipped wording — the way out of a bad edit."""
    _guard(ac.require, db, user, "content.manage")
    row = _guard(content_service.reset_help, db, user.tenant_id, key, actor=user,
                 locale=locale, ip=client_ip(request))
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------------------


@router.get("/knowledge", response_model=schemas.KnowledgeIndexOut)
def knowledge_index(request: Request, category: str = "", q: str = "", locale: str = "",
                    db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.KnowledgeIndexOut:
    resolved = _locale(request, locale)
    articles = content_service.list_articles(
        db, user.tenant_id, locale=resolved, category=category, query=q, role=user.role)
    return schemas.KnowledgeIndexOut(
        categories=content_service.categories_summary(db, user.tenant_id, resolved),
        articles=[schemas.ArticleOut.model_validate(a) for a in articles])


@router.get("/knowledge/{slug}", response_model=schemas.ArticleDetailOut)
def read_article(slug: str, request: Request, locale: str = "",
                 db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)) -> models.KnowledgeArticle:
    resolved = _locale(request, locale)
    article = content_service.get_article(db, user.tenant_id, slug, locale=resolved)
    if article is None or (not article.is_published
                           and "content.manage" not in ac.permissions_for(db, user)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    if article.audience_roles and user.role not in article.audience_roles:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    content_service.mark_read(db, article)
    db.commit()
    db.refresh(article)
    return article


@router.post("/knowledge", response_model=schemas.ArticleDetailOut,
             status_code=status.HTTP_201_CREATED)
def create_article(data: schemas.ArticleIn, request: Request, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> models.KnowledgeArticle:
    _guard(ac.require, db, user, "content.manage")
    row = _guard(content_service.save_article, db, user.tenant_id, actor=user,
                 ip=client_ip(request), **data.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.put("/knowledge/{article_id}", response_model=schemas.ArticleDetailOut)
def update_article(article_id: str, data: schemas.ArticleIn, request: Request,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> models.KnowledgeArticle:
    _guard(ac.require, db, user, "content.manage")
    row = _guard(content_service.save_article, db, user.tenant_id, actor=user,
                 article_id=article_id, ip=client_ip(request), **data.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.delete("/knowledge/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: str, request: Request, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> None:
    _guard(ac.require, db, user, "content.manage")
    _guard(content_service.delete_article, db, user.tenant_id, article_id, actor=user,
           ip=client_ip(request))
    db.commit()


# ---------------------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------------------


@router.get("/training", response_model=schemas.MyTrainingOut)
def my_training(db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> schemas.MyTrainingOut:
    """The hub as this user sees it: their courses, their progress, their certificates."""
    data = training_service.my_training(db, user.tenant_id, user)
    return schemas.MyTrainingOut(
        items=[schemas.TrainingItemOut(
            course=schemas.CourseOut.model_validate(i["course"]),
            progress=(schemas.ProgressOut.model_validate(i["progress"])
                      if i["progress"] else None),
            modules_total=i["modules_total"], modules_done=i["modules_done"],
            percent=i["percent"], certificate=i["certificate"]) for i in data["items"]],
        required_total=data["required_total"], required_done=data["required_done"])


@router.get("/training/courses/{course_id}", response_model=schemas.CourseDetailOut)
def get_course(course_id: str, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)) -> schemas.CourseDetailOut:
    course = training_service.get_course(db, user.tenant_id, course_id)
    if course is None or (not course.is_published
                          and "content.manage" not in ac.permissions_for(db, user)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    out = schemas.CourseDetailOut.model_validate(course)
    # Never `course.quiz` — that carries the answer key.
    out.quiz = training_service.quiz_for(course)
    out.modules = list(course.modules or [])
    return out


@router.post("/training/courses", response_model=schemas.CourseDetailOut,
             status_code=status.HTTP_201_CREATED)
def create_course(data: schemas.CourseIn, request: Request, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.CourseDetailOut:
    _guard(ac.require, db, user, "content.manage")
    row = _guard(training_service.save_course, db, user.tenant_id, actor=user,
                 ip=client_ip(request), **data.model_dump())
    db.commit()
    db.refresh(row)
    out = schemas.CourseDetailOut.model_validate(row)
    out.quiz = training_service.quiz_for(row)
    out.modules = list(row.modules or [])
    return out


@router.put("/training/courses/{course_id}", response_model=schemas.CourseDetailOut)
def update_course(course_id: str, data: schemas.CourseIn, request: Request,
                  db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> schemas.CourseDetailOut:
    _guard(ac.require, db, user, "content.manage")
    row = _guard(training_service.save_course, db, user.tenant_id, actor=user,
                 course_id=course_id, ip=client_ip(request), **data.model_dump())
    db.commit()
    db.refresh(row)
    out = schemas.CourseDetailOut.model_validate(row)
    out.quiz = training_service.quiz_for(row)
    out.modules = list(row.modules or [])
    return out


@router.post("/training/courses/{course_id}/modules/{index}", response_model=schemas.ProgressOut)
def complete_module(course_id: str, index: int, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> models.TrainingProgress:
    course = training_service.get_course(db, user.tenant_id, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    row = _guard(training_service.complete_module, db, user.tenant_id, user, course, index)
    db.commit()
    db.refresh(row)
    return row


@router.post("/training/courses/{course_id}/quiz", response_model=schemas.QuizResultOut)
def submit_quiz(course_id: str, data: schemas.QuizSubmitIn, request: Request,
                db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)) -> dict:
    course = training_service.get_course(db, user.tenant_id, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    result = _guard(training_service.submit_quiz, db, user.tenant_id, user, course,
                    data.answers, ip=client_ip(request))
    db.commit()
    return result


@router.get("/training/certificate/{course_id}")
def certificate(course_id: str, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    """The certificate as a PDF.

    Refuses to issue one for a lapsed certification. A downloadable certificate that does not
    say it has expired is a document somebody will present as current.
    """
    from fastapi.responses import Response

    from ..pdf import render_training_certificate

    course = training_service.get_course(db, user.tenant_id, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    progress = training_service.progress_for(db, user.tenant_id, user.id, course.id)
    state = training_service.certificate_state(progress)
    if state == "none":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="You have not passed this course yet.")
    if state == "expired":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That certification has lapsed. Retake the course to renew it.")

    pdf = render_training_certificate(user=user, course=course, progress=progress)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="certificate-{course.slug}.pdf"'})


@router.get("/training/sessions", response_model=list[schemas.TrainingSessionOut])
def list_sessions(upcoming: bool = True, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> list[models.TrainingSession]:
    return training_service.list_sessions(db, user.tenant_id, upcoming_only=upcoming)


@router.post("/training/sessions", response_model=schemas.TrainingSessionOut,
             status_code=status.HTTP_201_CREATED)
def create_session(data: schemas.TrainingSessionIn, request: Request,
                   db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)) -> models.TrainingSession:
    _guard(ac.require, db, user, "content.manage")
    row = _guard(training_service.save_session, db, user.tenant_id, actor=user,
                 ip=client_ip(request), **data.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.post("/training/sessions/{session_id}/register",
             response_model=schemas.TrainingSessionOut)
def register_for_session(session_id: str, db: Session = Depends(get_db),
                         user: models.User = Depends(get_current_user)) -> models.TrainingSession:
    row = db.get(models.TrainingSession, session_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    _guard(training_service.register, db, row, user)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/training/sessions/{session_id}/register",
               response_model=schemas.TrainingSessionOut)
def leave_session(session_id: str, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)) -> models.TrainingSession:
    row = db.get(models.TrainingSession, session_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    training_service.unregister(db, row, user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/training/sessions/{session_id}/attendance",
             response_model=schemas.TrainingSessionOut)
def record_attendance(session_id: str, data: schemas.AttendanceIn, request: Request,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> models.TrainingSession:
    """Who actually turned up — the number the training plan has to report."""
    _guard(ac.require, db, user, "content.manage")
    row = db.get(models.TrainingSession, session_id)
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    _guard(training_service.mark_attendance, db, user.tenant_id, row, data.user_ids,
           actor=user, ip=client_ip(request))
    db.commit()
    db.refresh(row)
    return row


@router.get("/training/report", response_model=schemas.TrainingReportOut)
def training_report(db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)) -> schemas.TrainingReportOut:
    """Evidence for the training plan: certificates held now, and sessions actually delivered."""
    _guard(ac.require, db, user, "content.manage")
    completion = training_service.completion_report(db, user.tenant_id)
    attendance = training_service.attendance_summary(db, user.tenant_id)
    return schemas.TrainingReportOut(**completion, **attendance)


# ---------------------------------------------------------------------------------------
# Guided actions
# ---------------------------------------------------------------------------------------


@router.get("/contracts/{contract_id}/guidance", response_model=schemas.GuidanceOut)
def contract_guidance(contract_id: str, db: Session = Depends(get_db),
                      user: models.User = Depends(get_current_user)) -> schemas.GuidanceOut:
    """Where this agreement is, and what to do next."""
    contract = db.get(models.Contract, contract_id)
    if contract is None or contract.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return schemas.GuidanceOut(
        progress=schemas.StageOut(**guidance.stage_progress(contract)),
        actions=[schemas.SuggestionOut(**a) for a in guidance.next_actions(db, contract, user)])


@router.get("/guidance/next", response_model=list[schemas.SuggestionOut])
def workspace_guidance(db: Session = Depends(get_db),
                       user: models.User = Depends(get_current_user)) -> list[dict]:
    """Next-best-actions across the workspace, for the dashboard."""
    return guidance.workspace_actions(db, user.tenant_id, user)


@router.get("/guidance/prefill", response_model=dict)
def prefill(contract_type: str = Query(default=""), db: Session = Depends(get_db),
            user: models.User = Depends(get_current_user)) -> dict:
    """Starting values for a new agreement, taken from what this user did last."""
    return guidance.prefill_for(db, user.tenant_id, user, contract_type)


@router.get("/guidance/stages", response_model=list[dict])
def stages(user: models.User = Depends(get_current_user)) -> list[dict]:
    """The stage vocabulary, so the front end does not hard-code a second copy of it."""
    return [{"key": s, "label": guidance.STAGE_LABELS[s]} for s in guidance.STAGES]


@router.get("/locales", response_model=dict)
def locales(request: Request, user: models.User = Depends(get_current_user)) -> dict:
    """Which locales this deployment serves, and which one the caller resolves to."""
    return {
        "supported": list(content_service.SUPPORTED_LOCALES),
        "default": content_service.DEFAULT_LOCALE,
        "resolved": _locale(request),
        "now": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
