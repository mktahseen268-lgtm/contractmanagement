"""Contextual help, knowledge base, training and guided actions (Phase 9, items 1-4).

Requirements: SOW-32, SOW-33.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app import content_service as cs
from app import guidance, models
from app import training_service as ts


@pytest.fixture()
def tenant(db, make_user):
    user, tenant = make_user()
    return db.merge(user), tenant


# ---------------------------------------------------------------------------------------
# Contextual help
# ---------------------------------------------------------------------------------------


def test_seeding_is_idempotent(db, tenant):
    """A deploy runs this again. It must not duplicate anything."""
    user, t = tenant
    first = cs.seed_help(db, t.id)
    assert first > 0
    assert cs.seed_help(db, t.id) == 0
    assert len(cs.help_map(db, t.id)) == first


def test_a_deploy_does_not_revert_an_edit(db, tenant):
    """The whole point of putting help in the database.

    If re-seeding overwrote edited copy, every deploy would silently undo Legal's corrections
    and they would find out by being asked about wording they had already fixed.
    """
    user, t = tenant
    cs.seed_help(db, t.id)
    cs.update_help(db, t.id, "contract.notice_period_days", actor=user,
                   body="MMBL policy: always 60 days unless Legal agrees otherwise.")
    db.commit()

    assert cs.seed_help(db, t.id) == 0
    assert cs.help_map(db, t.id)["contract.notice_period_days"]["body"].startswith("MMBL policy")


def test_an_edit_can_be_undone(db, tenant):
    user, t = tenant
    cs.seed_help(db, t.id)
    original = cs.help_map(db, t.id)["contract.effective_date"]["body"]

    cs.update_help(db, t.id, "contract.effective_date", actor=user, body="wrong")
    assert cs.help_map(db, t.id)["contract.effective_date"]["body"] == "wrong"

    cs.reset_help(db, t.id, "contract.effective_date", actor=user)
    assert cs.help_map(db, t.id)["contract.effective_date"]["body"] == original


def test_editing_help_is_audited(db, tenant):
    user, t = tenant
    cs.seed_help(db, t.id)
    cs.update_help(db, t.id, "contract.value", actor=user, body="in PKR")
    db.flush()

    actions = [a.action for a in db.query(models.AuditLog).filter(
        models.AuditLog.tenant_id == t.id).all()]
    assert "help.updated" in actions


def test_a_missing_translation_falls_back_per_topic(db, tenant):
    """Not per request. A half-translated locale should show what it has, and English for the
    rest — falling back wholesale throws away translation work that was already done."""
    user, t = tenant
    cs.seed_help(db, t.id, "en")
    cs.update_help(db, t.id, "contract.value", actor=user, locale="ur",
                   title="معاہدے کی مالیت", body="کل مالیت")
    db.flush()

    urdu = cs.help_map(db, t.id, "ur")
    assert urdu["contract.value"]["is_translated"] is True
    assert urdu["contract.value"]["title"] == "معاہدے کی مالیت"
    # Everything else is still there, in English, flagged as untranslated.
    assert urdu["contract.effective_date"]["is_translated"] is False
    assert urdu["contract.effective_date"]["body"]


def test_an_unknown_locale_falls_back_rather_than_failing(db):
    assert cs.normalise_locale("ur-PK") == "ur"
    assert cs.normalise_locale("fr") == "en"
    assert cs.normalise_locale("") == "en"


def test_help_can_be_filtered_to_one_screen(db, tenant):
    user, t = tenant
    cs.seed_help(db, t.id)
    only = cs.help_map(db, t.id, surface="Contract form")
    assert only
    assert all(v["surface"] == "Contract form" for v in only.values())


# ---------------------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------------------


def test_an_article_round_trips(db, tenant):
    user, t = tenant
    article = cs.save_article(db, t.id, actor=user, title="Raising an NDA",
                              body="Step one...", category="quickstart")
    db.commit()

    assert article.slug == "raising-an-nda"
    found = cs.get_article(db, t.id, "raising-an-nda")
    assert found is not None and found.body == "Step one..."


def test_two_articles_cannot_share_an_address(db, tenant):
    user, t = tenant
    cs.save_article(db, t.id, actor=user, title="Playbook", body="x", category="playbook")
    db.flush()
    with pytest.raises(cs.ContentError, match="already exists"):
        cs.save_article(db, t.id, actor=user, title="Playbook", body="y", category="playbook")


def test_an_article_with_no_audience_is_for_everyone(db, tenant):
    """A role filter that hid audience-less articles would show a new user an empty knowledge
    base, which is the opposite of what it is for."""
    user, t = tenant
    cs.save_article(db, t.id, actor=user, title="For all", body="x", category="faq")
    cs.save_article(db, t.id, actor=user, title="Legal only", body="x", category="faq",
                    audience_roles=["manager"])
    db.flush()

    titles = {a.title for a in cs.list_articles(db, t.id, role="author")}
    assert "For all" in titles
    assert "Legal only" not in titles
    assert "Legal only" in {a.title for a in cs.list_articles(db, t.id, role="manager")}


def test_unpublished_articles_are_not_listed(db, tenant):
    user, t = tenant
    cs.save_article(db, t.id, actor=user, title="Draft note", body="x", category="faq",
                    is_published=False)
    db.flush()
    assert cs.list_articles(db, t.id) == []
    assert len(cs.list_articles(db, t.id, include_unpublished=True)) == 1


def test_search_looks_in_the_body(db, tenant):
    user, t = tenant
    cs.save_article(db, t.id, actor=user, title="Vendor onboarding",
                    body="Screen the counterparty against sanctions lists first.",
                    category="playbook")
    db.flush()
    assert len(cs.list_articles(db, t.id, query="sanctions")) == 1
    assert cs.list_articles(db, t.id, query="mortgage") == []


def test_every_category_is_listed_even_when_empty(db, tenant):
    """An absent category reads as 'this product has no playbooks' when it means nobody has
    written one yet."""
    user, t = tenant
    summary = cs.categories_summary(db, t.id)
    assert {c["category"] for c in summary} == set(cs.CATEGORIES)
    assert all(c["count"] == 0 for c in summary)


# ---------------------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------------------


QUIZ = [
    {"q": "When does the notice period start?", "options": ["At signature", "Before expiry"],
     "answer": 1, "why": "It is counted backwards from the expiry date."},
    {"q": "What does auto-renew mean?", "options": ["It rolls over", "It ends"],
     "answer": 0, "why": "It continues unless somebody stops it."},
    {"q": "Who may approve above their limit?", "options": ["Nobody", "Anyone"],
     "answer": 0, "why": "The approval matrix is the limit."},
]


@pytest.fixture()
def course(db, tenant):
    user, t = tenant
    row = ts.save_course(db, t.id, actor=user, title="Contract basics",
                         modules=[{"title": "Lifecycle", "minutes": 10},
                                  {"title": "Renewals", "minutes": 5}],
                         quiz=QUIZ, pass_mark=67, certificate_valid_months=12,
                         is_required=True)
    db.commit()
    return row


def test_the_answer_key_never_leaves_the_server(db, course):
    """The one thing in the training module that must not be got wrong.

    Serving the answers alongside the questions would make every certificate evidence that
    somebody opened developer tools, and nobody would notice until an auditor asked how the
    quiz was marked.
    """
    served = ts.quiz_for(course)

    assert len(served) == len(QUIZ)
    for question in served:
        assert set(question) == {"q", "options"}
        assert "answer" not in question
        assert "why" not in question


def test_passing_issues_a_certificate_that_expires(db, tenant, course):
    user, t = tenant
    result = ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    db.commit()

    assert result["passed"] is True
    assert result["score"] == 100
    assert result["certificate_no"]
    assert result["expires_at"] is not None
    assert ts.certificate_state(ts.progress_for(db, t.id, user.id, course.id)) == "valid"


def test_a_lapsed_certificate_reports_as_expired(db, tenant, course):
    """Computed from the date, never stored as a status — a status needs a sweep to stay true,
    and a certificate that stays 'valid' because the sweep did not run is the failure this is
    meant to prevent."""
    user, t = tenant
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    progress = ts.progress_for(db, t.id, user.id, course.id)
    progress.expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=1)
    db.flush()

    assert ts.certificate_state(progress) == "expired"


def test_failing_reports_only_the_questions_that_were_wrong(db, tenant, course):
    user, t = tenant
    result = ts.submit_quiz(db, t.id, user, course, [0, 1, 1])

    assert result["passed"] is False
    assert result["score"] == 0
    assert {r["index"] for r in result["review"]} == {0, 1, 2}
    # Feedback explains, it does not hand over the marking scheme.
    assert all("answer" not in r for r in result["review"])


def test_a_failed_retake_does_not_revoke_a_certificate(db, tenant, course):
    """Losing a valid certification by trying to improve on it would teach people not to
    retake, which is the opposite of what the hub is for."""
    user, t = tenant
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    number = ts.progress_for(db, t.id, user.id, course.id).certificate_no

    ts.submit_quiz(db, t.id, user, course, [0, 0, 0])
    progress = ts.progress_for(db, t.id, user.id, course.id)

    assert progress.status == "passed"
    assert progress.certificate_no == number
    assert progress.best_score == 100
    assert progress.last_score < 100


def test_a_repeat_pass_keeps_the_same_certificate_number(db, tenant, course):
    """It is the same certification renewed. A new number each time would make the training
    register look like more distinct certifications than were actually earned."""
    user, t = tenant
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    first = ts.progress_for(db, t.id, user.id, course.id).certificate_no
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])

    assert ts.progress_for(db, t.id, user.id, course.id).certificate_no == first


def test_a_wrong_number_of_answers_is_refused(db, tenant, course):
    user, t = tenant
    with pytest.raises(ts.TrainingError, match="3 questions"):
        ts.submit_quiz(db, t.id, user, course, [1, 0])


def test_a_trivial_quiz_is_refused(db, tenant):
    """With one question a lucky guess is 100%."""
    user, t = tenant
    with pytest.raises(ts.TrainingError, match="at least"):
        ts.save_course(db, t.id, actor=user, title="Too short",
                       quiz=[{"q": "?", "options": ["a", "b"], "answer": 0}])


def test_a_question_pointing_nowhere_is_refused(db, tenant):
    """Caught at save time, not at marking time — after somebody has already sat the course."""
    user, t = tenant
    bad = [*QUIZ[:2], {"q": "?", "options": ["a", "b"], "answer": 7}]
    with pytest.raises(ts.TrainingError, match="does not point at"):
        ts.save_course(db, t.id, actor=user, title="Broken", quiz=bad)


def test_module_progress_accumulates(db, tenant, course):
    user, t = tenant
    ts.complete_module(db, t.id, user, course, 0)
    ts.complete_module(db, t.id, user, course, 0)      # again — must not double-count
    ts.complete_module(db, t.id, user, course, 1)
    db.commit()

    progress = ts.progress_for(db, t.id, user.id, course.id)
    assert progress.completed_modules == [0, 1]
    assert progress.status == "in_progress"


def test_a_module_outside_the_course_is_refused(db, tenant, course):
    user, t = tenant
    with pytest.raises(ts.TrainingError, match="not part of"):
        ts.complete_module(db, t.id, user, course, 99)


def test_my_training_reports_what_is_outstanding(db, tenant, course):
    user, t = tenant
    before = ts.my_training(db, t.id, user)
    assert before["required_total"] == 1
    assert before["required_done"] == 0

    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    db.commit()
    after = ts.my_training(db, t.id, user)
    assert after["required_done"] == 1
    assert after["items"][0]["certificate"] == "valid"


def test_the_report_counts_people_not_enrolments(db, tenant, course, make_user):
    """'Have fifteen resources been trained' is a question about people."""
    user, t = tenant
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    db.commit()

    report = ts.completion_report(db, t.id)
    assert report["people_with_a_valid_certificate"] == 1
    assert report["courses"][0]["passed"] == 1


def test_an_expired_certificate_is_not_counted_as_trained(db, tenant, course):
    """Reporting somebody as trained on a process their certificate predates is how a training
    register becomes fiction."""
    user, t = tenant
    ts.submit_quiz(db, t.id, user, course, [1, 0, 0])
    progress = ts.progress_for(db, t.id, user.id, course.id)
    progress.expires_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=1)
    db.commit()

    report = ts.completion_report(db, t.id)
    assert report["people_with_a_valid_certificate"] == 0
    assert report["courses"][0]["expired"] == 1


# ---------------------------------------------------------------------------------------
# Live sessions
# ---------------------------------------------------------------------------------------


@pytest.fixture()
def session(db, tenant):
    user, t = tenant
    row = ts.save_session(db, t.id, actor=user, title="Kick-off",
                          starts_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                          + dt.timedelta(days=7), kind="onsite", capacity=2)
    db.commit()
    return row


def test_registering_twice_does_not_take_two_places(db, tenant, session):
    user, t = tenant
    ts.register(db, session, user)
    ts.register(db, session, user)
    assert session.registered_user_ids == [user.id]


def test_a_full_session_is_refused(db, tenant, session, make_user):
    user, t = tenant
    session.capacity = 1
    ts.register(db, session, user)
    db.commit()          # `make_user` writes on its own connection; SQLite deadlocks otherwise

    other, _ = make_user()
    with pytest.raises(ts.TrainingError, match="full"):
        ts.register(db, session, db.merge(other))


def test_a_past_session_cannot_be_joined(db, tenant, session):
    user, t = tenant
    session.starts_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=1)
    db.flush()
    with pytest.raises(ts.TrainingError, match="already run"):
        ts.register(db, session, user)


def test_attendance_is_separate_from_registration(db, tenant, session):
    """Registering is an intention. The training plan has to report who turned up."""
    user, t = tenant
    ts.register(db, session, user)
    db.flush()
    assert ts.attendance_summary(db, t.id)["people_attended"] == 0

    ts.mark_attendance(db, t.id, session, [user.id], actor=user)
    db.commit()
    assert ts.attendance_summary(db, t.id)["people_attended"] == 1


def test_attendance_for_somebody_outside_the_workspace_is_refused(db, tenant, session, make_user):
    user, t = tenant
    outsider, _ = make_user()
    with pytest.raises(ts.TrainingError, match="not in this workspace"):
        ts.mark_attendance(db, t.id, session, [outsider.id], actor=user)


def test_certificate_validity_clamps_the_day(db):
    """31 January + 1 month is 28 February, not 3 March. An expiry that drifts later than the
    policy allows is the wrong direction to be wrong in."""
    assert ts._add_months(dt.datetime(2026, 1, 31), 1).date() == dt.date(2026, 2, 28)
    assert ts._add_months(dt.datetime(2024, 1, 31), 1).date() == dt.date(2024, 2, 29)
    assert ts._add_months(dt.datetime(2026, 12, 15), 12).date() == dt.date(2027, 12, 15)


# ---------------------------------------------------------------------------------------
# Guided actions
# ---------------------------------------------------------------------------------------


@pytest.fixture()
def contract(db, tenant):
    user, t = tenant
    row = models.Contract(tenant_id=t.id, reference_no="C-1", title="Vendor agreement",
                          owner_id=user.id, created_by=user.id, status="draft")
    db.add(row)
    db.commit()
    return row


def test_a_closed_agreement_gets_no_suggestions(db, tenant, contract):
    """Suggesting work on something that is over is the fastest way to have the panel ignored."""
    user, t = tenant
    contract.status = "terminated"
    db.flush()
    assert guidance.next_actions(db, contract, user) == []


def test_missing_dates_are_raised_before_they_bite(db, tenant, contract):
    user, t = tenant
    keys = {a["key"] for a in guidance.next_actions(db, contract, user)}
    assert "set_effective_date" in keys
    assert "set_counterparty" in keys


def test_auto_renew_without_an_expiry_is_critical(db, tenant, contract):
    """It will roll over silently and no notice-period reminder can be calculated."""
    user, t = tenant
    contract.renewal_type = "auto"
    contract.end_date = None
    db.flush()

    actions = guidance.next_actions(db, contract, user)
    critical = next(a for a in actions if a["key"] == "auto_renew_no_end")
    assert critical["severity"] == "critical"
    assert actions[0]["severity"] == "critical"       # sorted most urgent first


def test_an_expiring_agreement_says_how_long_is_left(db, tenant, contract):
    user, t = tenant
    contract.status = "active"
    contract.effective_date = dt.date.today() - dt.timedelta(days=300)
    contract.end_date = dt.date.today() + dt.timedelta(days=20)
    db.flush()

    action = next(a for a in guidance.next_actions(db, contract, user)
                  if a["key"] == "expiring_soon")
    assert "20 day" in action["title"]
    assert action["severity"] == "critical"           # inside 30 days


def test_a_running_workflow_redirects_rather_than_offering_a_status_change(db, tenant, contract):
    """A status change here would step around the approvers."""
    user, t = tenant
    contract.status = "in_review"
    run = models.WorkflowRun(tenant_id=t.id, contract_id=contract.id, status="running",
                             started_by=user.id)
    db.add(run)
    db.flush()

    keys = {a["key"] for a in guidance.next_actions(db, contract, user)}
    assert "awaiting_approval" in keys
    assert "submit_for_review" not in keys


def test_the_stage_tracker_marks_where_it_is(db, contract):
    contract.status = "out_for_signature"
    progress = guidance.stage_progress(contract)

    assert progress["stage"] == "signature"
    states = [s["state"] for s in progress["stages"]]
    assert states == ["done", "done", "done", "done", "current", "todo"]


def test_prefill_says_nothing_when_there_is_nothing_to_say(db, tenant):
    """A guess the user does not notice is worse than an empty field: an empty field gets
    filled in, a wrong one gets signed."""
    user, t = tenant
    assert guidance.prefill_for(db, t.id, user) == {}


def test_prefill_comes_from_what_this_user_did_last(db, tenant, contract):
    user, t = tenant
    contract.department = "Operations"
    contract.currency = "PKR"
    contract.governing_law = "Pakistan"
    db.commit()

    prefill = guidance.prefill_for(db, t.id, user)
    assert prefill["currency"] == "PKR"
    assert prefill["department"] == "Operations"
    assert prefill["_source"] == "your last agreement"


def test_renewal_type_is_not_carried_across_agreement_types(db, tenant, contract):
    """Vendor agreements auto-renew and employment contracts do not. Copying that across types
    would be a guess, not a hint."""
    user, t = tenant
    contract.type = "vendor"
    contract.renewal_type = "auto"
    db.commit()

    assert "renewal_type" in guidance.prefill_for(db, t.id, user, "vendor")
    assert "renewal_type" not in guidance.prefill_for(db, t.id, user, "employment")


def test_workspace_actions_surface_stalled_drafts(db, tenant, contract):
    user, t = tenant
    contract.updated_at = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
                           - dt.timedelta(days=30))
    db.commit()

    keys = {a["key"] for a in guidance.workspace_actions(db, t.id, user)}
    assert "stalled_drafts" in keys


def test_overdue_obligations_are_read_from_the_date_not_the_status(db, tenant, contract):
    """The sweep that flips `pending` to `overdue` runs on a beat. Between the due date passing
    and the next sweep, an obligation is late and still says `pending` — reading the status
    alone would miss exactly the window somebody needs telling."""
    user, t = tenant
    db.add(models.Obligation(
        tenant_id=t.id, contract_id=contract.id, title="Submit the quarterly report",
        owner_id=user.id, created_by=user.id, status="pending",
        due_date=dt.date.today() - dt.timedelta(days=3)))
    db.commit()

    keys = {a["key"] for a in guidance.next_actions(db, contract, user)}
    assert "overdue_obligations" in keys
    assert "my_overdue" in {a["key"] for a in guidance.workspace_actions(db, t.id, user)}


# ---------------------------------------------------------------------------------------
# Shipped content
# ---------------------------------------------------------------------------------------


def test_a_new_workspace_starts_with_real_content(db, tenant):
    """A knowledge base that ships empty stays empty — nobody writes the first article, and the
    feature gets judged on a blank page."""
    user, t = tenant
    added = cs.seed_all(db, t.id)
    db.commit()

    assert added["help"] > 20
    assert added["articles"] >= 6
    assert added["courses"] >= 2
    assert cs.seed_all(db, t.id) == {"help": 0, "articles": 0, "courses": 0}


def test_seeded_courses_carry_a_markable_quiz(db, tenant):
    """Validated here rather than discovered when somebody sits the course."""
    user, t = tenant
    cs.seed_all(db, t.id)
    db.commit()

    for course in ts.list_courses(db, t.id):
        assert len(course.quiz) >= ts.MIN_QUIZ_QUESTIONS
        for question in course.quiz:
            assert 0 <= question["answer"] < len(question["options"])
            assert question["why"]                       # a wrong answer must be explainable
        # And the served form still hides the key.
        assert all("answer" not in q for q in ts.quiz_for(course))


def test_a_seeded_course_can_actually_be_passed(db, tenant):
    user, t = tenant
    cs.seed_all(db, t.id)
    db.commit()

    course = ts.get_course(db, t.id, "contract-lifecycle-essentials")
    result = ts.submit_quiz(db, t.id, user, course, [q["answer"] for q in course.quiz])
    db.commit()

    assert result["passed"] is True
    assert result["score"] == 100
