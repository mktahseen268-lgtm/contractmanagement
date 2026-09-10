"""Consolidated internal review, @mentions, and the internal-only privacy boundary.

The privacy tests are the important ones. A Legal note reading "do not concede clause 7 below
8%" reaching the counterparty is unrecoverable — you cannot un-send it, and it moves the
commercial position of the negotiation. So `internal_only` is enforced in one place and
asserted here against every shape an external payload can take.

Requirements: SOW-08, SOW-09.
"""

from __future__ import annotations

import uuid

import pytest

from app import comment_service, models, security


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(name="DFS Coordinator")
    owner.is_client_facing = True
    owner.department = "DFS"
    contract = models.Contract(
        tenant_id=tenant.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Merchant Agreement", type="service", status="in_review",
        owner_id=owner.id, created_by=owner.id, value=1_000_000, currency="PKR",
    )
    db.add(contract)
    db.commit()
    return {"tenant": tenant, "owner": owner, "contract": contract}


def _user(db, ws, name, department="", role="approver", client_facing=False):
    u = models.User(
        tenant_id=ws["tenant"].id, email=f"{uuid.uuid4().hex[:8]}@example.com", name=name,
        password_hash=security.hash_password("Str0ng!Passw0rd1"), role=role,
        department=department, is_client_facing=client_facing,
    )
    db.add(u)
    db.commit()
    return u


# ---------------------------------------------------------------------------- privacy


class TestInternalOnlyBoundary:
    def test_internal_comments_are_hidden_from_every_external_audience(self, db, workspace):
        legal = _user(db, workspace, "Legal Reviewer", department="Legal")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="Do not concede clause 7 below 8%.", internal_only=True)
        comment_service.create(db, contract=workspace["contract"], author=workspace["owner"],
                               body="We have reviewed and can proceed.", internal_only=False)
        db.commit()

        comments = db.query(models.Comment).filter(
            models.Comment.contract_id == workspace["contract"].id
        ).all()

        internal = comment_service.visible_to(comments, audience=comment_service.INTERNAL_AUDIENCE)
        assert len(internal) == 2

        for audience in comment_service.EXTERNAL_AUDIENCES:
            visible = comment_service.visible_to(comments, audience=audience)
            assert len(visible) == 1, f"{audience} must not see the internal note"
            assert all(not c.internal_only for c in visible)
            assert not any("clause 7" in c.body for c in visible)

    def test_unknown_audience_is_treated_as_external(self, db, workspace):
        """Fail closed. A new surface added later must not leak by default just because
        nobody remembered to add it to the external list."""
        legal = _user(db, workspace, "Legal", department="Legal")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="Internal position", internal_only=True)
        db.commit()
        comments = db.query(models.Comment).filter(
            models.Comment.contract_id == workspace["contract"].id
        ).all()
        assert comment_service.visible_to(comments, audience="some-new-portal") == []

    def test_assert_external_safe_raises_on_a_leak(self, db, workspace):
        legal = _user(db, workspace, "Legal", department="Legal")
        c = comment_service.create(db, contract=workspace["contract"], author=legal,
                                   body="Internal", internal_only=True)
        db.commit()
        with pytest.raises(RuntimeError, match="internal-only"):
            comment_service.assert_external_safe([c])

    def test_assert_external_safe_passes_clean_payloads(self, db, workspace):
        c = comment_service.create(db, contract=workspace["contract"], author=workspace["owner"],
                                   body="Shareable", internal_only=False)
        db.commit()
        comment_service.assert_external_safe([c])   # must not raise

    def test_consolidated_view_for_an_external_audience_drops_internal(self, db, workspace):
        legal = _user(db, workspace, "Legal", department="Legal")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="Internal only", internal_only=True)
        db.commit()
        external = comment_service.consolidated_review(db, workspace["contract"],
                                                       audience="counterparty")
        assert external["total"] == 0
        assert external["internal_only_count"] == 0

    def test_internal_mention_is_flagged_so_it_cannot_leak_via_the_feed(self, db, workspace):
        """The mentions feed is a second read path; it must carry the same flag."""
        legal = _user(db, workspace, "Legal Reviewer", department="Legal")
        finance = _user(db, workspace, "Finance Reviewer", department="Finance")
        comment_service.create(
            db, contract=workspace["contract"], author=legal,
            body=f"@{finance.name} hold the pricing position", internal_only=True,
        )
        db.commit()
        mention = db.query(models.Mention).filter(
            models.Mention.mentioned_user_id == finance.id
        ).one()
        assert mention.internal_only is True


# ---------------------------------------------------------------------------- consolidated


class TestConsolidatedReview:
    def test_comments_are_grouped_by_reviewing_function(self, db, workspace):
        """The question actually being asked is "what does Legal say, what does Finance say" —
        not "what happened in chronological order"."""
        legal = _user(db, workspace, "Legal", department="Legal")
        finance = _user(db, workspace, "Finance", department="Finance")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="Indemnity too broad", internal_only=True)
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="Propose capping at 12 months fees", kind="amendment")
        comment_service.create(db, contract=workspace["contract"], author=finance,
                               body="Pricing acceptable")
        db.commit()

        view = comment_service.consolidated_review(db, workspace["contract"])
        departments = {g["department"] for g in view["groups"]}
        assert departments == {"Legal", "Finance"}
        legal_group = next(g for g in view["groups"] if g["department"] == "Legal")
        assert len(legal_group["comments"]) == 2
        assert legal_group["amendments"] == 1
        assert view["amendments"] == 1
        assert view["internal_only_count"] == 1

    def test_author_department_is_used_when_none_is_given(self, db, workspace):
        legal = _user(db, workspace, "Legal", department="Legal")
        comment_service.create(db, contract=workspace["contract"], author=legal, body="Note")
        db.commit()
        view = comment_service.consolidated_review(db, workspace["contract"])
        assert view["groups"][0]["department"] == "Legal"

    def test_unassigned_department_is_grouped_not_dropped(self, db, workspace):
        nobody = _user(db, workspace, "No Department")
        comment_service.create(db, contract=workspace["contract"], author=nobody, body="Note")
        db.commit()
        view = comment_service.consolidated_review(db, workspace["contract"])
        assert view["groups"][0]["department"] == "Unassigned"


# ---------------------------------------------------------------------------- mentions


class TestMentions:
    def test_mention_by_full_name_notifies(self, db, workspace):
        legal = _user(db, workspace, "Legal", department="Legal")
        finance = _user(db, workspace, "Ayesha Khan", department="Finance")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="@Ayesha Khan can you confirm the pricing?")
        db.commit()

        mentions = comment_service.mentions_for_user(db, workspace["tenant"].id, finance.id)
        assert len(mentions) == 1
        assert mentions[0].mentioned_by == legal.id
        assert db.query(models.Notification).filter(
            models.Notification.user_id == finance.id,
            models.Notification.type == "contract.mentioned",
        ).count() == 1

    def test_mention_by_email_local_part(self, db, workspace):
        target = models.User(
            tenant_id=workspace["tenant"].id, email="ayesha.khan@example.com", name="A K",
            password_hash=security.hash_password("Str0ng!Passw0rd1"), role="approver",
        )
        db.add(target)
        db.commit()
        found = comment_service.extract_mentions(db, workspace["tenant"].id,
                                                 "ping @ayesha.khan please")
        assert [u.id for u in found] == [target.id]

    def test_self_mention_does_not_notify(self, db, workspace):
        legal = _user(db, workspace, "Legal Reviewer", department="Legal")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body=f"@{legal.name} note to self")
        db.commit()
        assert comment_service.mentions_for_user(db, workspace["tenant"].id, legal.id) == []

    def test_unresolvable_mention_is_ignored(self, db, workspace):
        """Inventing a recipient is worse than dropping the mention."""
        found = comment_service.extract_mentions(db, workspace["tenant"].id,
                                                 "@nobody-by-that-name look at this")
        assert found == []

    def test_email_address_in_a_comment_is_not_a_mention(self, db, workspace):
        """A conservative pattern: `write to me@example.com` must not mention anyone."""
        _user(db, workspace, "Example")
        found = comment_service.extract_mentions(db, workspace["tenant"].id,
                                                 "write to someone@example.com about it")
        assert found == []

    def test_unread_count_and_mark_read(self, db, workspace):
        legal = _user(db, workspace, "Legal", department="Legal")
        finance = _user(db, workspace, "Ayesha Khan", department="Finance")
        comment_service.create(db, contract=workspace["contract"], author=legal,
                               body="@Ayesha Khan please review")
        db.commit()
        assert comment_service.unread_mention_count(db, workspace["tenant"].id, finance.id) == 1
        assert comment_service.mark_mentions_read(db, workspace["tenant"].id, finance.id) == 1
        db.commit()
        assert comment_service.unread_mention_count(db, workspace["tenant"].id, finance.id) == 0


# ---------------------------------------------------------------------------- §3.5


class TestClientFacingCapability:
    def test_only_client_facing_users_may_transmit_externally(self, db, workspace):
        """RFI §3.5 — DFS/BBCORP remain the sole client-facing coordinators. A Legal reviewer
        is senior but deliberately NOT client-facing, so this cannot be a role check."""
        legal = _user(db, workspace, "Legal", department="Legal", role="manager")
        coordinator = _user(db, workspace, "DFS", department="DFS", role="author",
                            client_facing=True)

        assert not comment_service.can_share_externally(legal)
        assert comment_service.can_share_externally(coordinator)
        with pytest.raises(PermissionError, match="client-facing coordinators"):
            comment_service.assert_can_share(legal)
        comment_service.assert_can_share(coordinator)   # must not raise

    def test_admins_retain_the_capability(self, db, workspace):
        """So a workspace cannot lock itself out of talking to its own counterparties."""
        admin = _user(db, workspace, "Admin", role="admin")
        assert comment_service.can_share_externally(admin)
