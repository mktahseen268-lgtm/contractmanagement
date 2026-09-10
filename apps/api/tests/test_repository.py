"""Repository structure: parties, relationships, departments, folders, custom fields, search.

The load-bearing claim is **duplicate party detection**. A vendor master that lets "Acme
Trading (Pvt) Ltd" and "ACME TRADING PRIVATE LIMITED" both exist is worse than no vendor
master: it looks authoritative while answering "what is our exposure to Acme?" wrongly. So the
normalisation is tested against the spellings that actually occur, and onboarding is tested to
block rather than warn.

The other thing worth testing hard is the folder tree, because a materialised path makes a
cycle invisible after the fact — by the time anyone notices, the subtree is unreachable.

Requirements: SOW-24.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app import models, repository_service, search_service
from app.repository_service import RepositoryError


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"repo-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    return {"tenant": tenant, "owner": owner}


def _party(db, ws, name, registration="", **kwargs) -> models.Party:
    return repository_service.create_party(
        db, ws["tenant"].id,
        {"name": name, "registration_no": registration, **kwargs},
        actor=ws["owner"], override_reason=kwargs.pop("override_reason", ""),
    )


def _contract(db, ws, **kwargs) -> models.Contract:
    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title=kwargs.pop("title", "Vendor Services Agreement"),
        type=kwargs.pop("type", "vendor"), status=kwargs.pop("status", "draft"),
        owner_id=ws["owner"].id, created_by=ws["owner"].id,
        value=kwargs.pop("value", 100_000), currency=kwargs.pop("currency", "PKR"),
        **kwargs,
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------------------
# Party name normalisation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("Acme Trading (Pvt) Ltd", "ACME TRADING PRIVATE LIMITED"),
    ("Acme Trading Limited", "Acme Trading Ltd."),
    ("Globex L.L.C", "Globex LLC"),
    ("Northstar Industries, Inc.", "Northstar Industries Incorporated"),
    ("Initech FZE", "initech fze"),
    ("Stark Trading Co.", "Stark Trading Company"),
])
def test_the_same_company_spelled_differently_normalises_the_same(a, b):
    """These are the spellings that actually occur in vendor data."""
    assert repository_service.name_key(a) == repository_service.name_key(b)


@pytest.mark.parametrize("a,b", [
    ("Acme Trading", "Acme Logistics"),
    ("Northstar Industries", "Northstar Holdings"),
    ("Globex", "Initech"),
])
def test_different_companies_do_not_normalise_together(a, b):
    assert repository_service.name_key(a) != repository_service.name_key(b)


def test_normalisation_does_not_eat_a_name_that_is_only_a_suffix():
    """"Limited" as a whole name is odd but must not normalise to nothing — an empty key
    would match every other empty key."""
    assert repository_service.name_key("Limited") != ""


# ---------------------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------------------


def test_onboarding_blocks_on_a_near_identical_name(db, workspace):
    _party(db, workspace, "Acme Trading (Pvt) Ltd")
    with pytest.raises(RepositoryError, match="looks like an existing party"):
        _party(db, workspace, "ACME TRADING PRIVATE LIMITED")


def test_onboarding_blocks_on_a_matching_registration_number(db, workspace):
    """Different name, same registration — proof, not suspicion."""
    _party(db, workspace, "Acme Trading", registration="1234567-8")
    with pytest.raises(RepositoryError, match="looks like an existing party"):
        _party(db, workspace, "Completely Different Name", registration="1234567-8")


def test_the_two_signals_are_reported_separately(db, workspace):
    """An exact registration match is proof; a similar name is a suspicion. Conflating them
    either blocks on coincidence or lets a real duplicate through."""
    _party(db, workspace, "Acme Trading", registration="1234567-8")
    exact = repository_service.find_duplicates(db, workspace["tenant"].id, "Other",
                                               "1234567-8")
    likely = repository_service.find_duplicates(db, workspace["tenant"].id,
                                                "Acme Trading Ltd", "")
    assert exact[0]["certainty"] == "exact"
    assert likely[0]["certainty"] == "likely"


def test_an_override_with_a_reason_is_allowed_and_recorded(db, workspace):
    """"We knew and did it anyway" is a different fact from "nobody noticed"."""
    original = _party(db, workspace, "Acme Trading (Pvt) Ltd")
    duplicate = repository_service.create_party(
        db, workspace["tenant"].id, {"name": "Acme Trading Private Limited"},
        actor=workspace["owner"],
        override_reason="Separate legal entity in a different jurisdiction.",
    )
    assert duplicate.duplicate_override_of == original.id
    assert "Separate legal entity" in duplicate.duplicate_override_reason


def test_the_override_is_audited(db, workspace):
    _party(db, workspace, "Acme Trading")
    repository_service.create_party(
        db, workspace["tenant"].id, {"name": "Acme Trading Ltd"},
        actor=workspace["owner"], override_reason="Confirmed distinct.")
    db.flush()
    entries = db.query(models.AuditLog).filter_by(
        tenant_id=workspace["tenant"].id, action="party.created").all()
    assert any(e.meta.get("duplicate_override") for e in entries)


def test_an_unrelated_name_onboards_cleanly(db, workspace):
    _party(db, workspace, "Acme Trading")
    party = _party(db, workspace, "Globex Logistics")
    assert party.duplicate_override_of is None


def test_a_party_in_another_tenant_is_not_a_duplicate(db, make_user):
    """Duplicate detection is per workspace, like everything else."""
    owner_a, tenant_a = make_user(email=f"a-{uuid.uuid4().hex[:8]}@example.com", name="A")
    owner_b, tenant_b = make_user(email=f"b-{uuid.uuid4().hex[:8]}@example.com", name="B")
    repository_service.create_party(db, tenant_a.id, {"name": "Acme Trading"}, actor=owner_a)
    party = repository_service.create_party(db, tenant_b.id, {"name": "Acme Trading"},
                                            actor=owner_b)
    assert party.duplicate_override_of is None


def test_a_party_without_a_name_is_refused(db, workspace):
    with pytest.raises(RepositoryError, match="needs a name"):
        _party(db, workspace, "   ")


def test_an_unknown_entity_type_is_refused(db, workspace):
    with pytest.raises(RepositoryError, match="Unknown entity type"):
        _party(db, workspace, "Acme", entity_type="corporation-ish")


def test_linking_a_contract_keeps_the_free_text_field_in_step(db, workspace):
    """`party_id` is authoritative, but every existing report and PDF reads `counterparty`."""
    party = _party(db, workspace, "Acme Trading (Pvt) Ltd")
    contract = _contract(db, workspace)
    repository_service.link_contract_to_party(db, contract, party)
    assert contract.party_id == party.id
    assert contract.counterparty == "Acme Trading (Pvt) Ltd"


# ---------------------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------------------


def test_addenda_are_numbered_sequentially_per_parent(db, workspace):
    parent = _contract(db, workspace, title="Master Agreement")
    first = repository_service.relate(db, parent, _contract(db, workspace), "addendum_of",
                                      actor=workspace["owner"])
    second = repository_service.relate(db, parent, _contract(db, workspace), "addendum_of",
                                       actor=workspace["owner"])
    assert (first.sequence, second.sequence) == (1, 2)


def test_a_second_parent_starts_its_own_addendum_numbering(db, workspace):
    other = _contract(db, workspace, title="Another Master")
    repository_service.relate(db, _contract(db, workspace), _contract(db, workspace),
                              "addendum_of", actor=workspace["owner"])
    relation = repository_service.relate(db, other, _contract(db, workspace), "addendum_of",
                                         actor=workspace["owner"])
    assert relation.sequence == 1


def test_only_addenda_are_numbered(db, workspace):
    relation = repository_service.relate(db, _contract(db, workspace), _contract(db, workspace),
                                         "related_to", actor=workspace["owner"])
    assert relation.sequence == 0


def test_an_agreement_cannot_be_related_to_itself(db, workspace):
    contract = _contract(db, workspace)
    with pytest.raises(RepositoryError, match="cannot be related to itself"):
        repository_service.relate(db, contract, contract, "related_to",
                                  actor=workspace["owner"])


def test_an_unknown_relationship_kind_is_refused(db, workspace):
    with pytest.raises(RepositoryError, match="Unknown relationship"):
        repository_service.relate(db, _contract(db, workspace), _contract(db, workspace),
                                  "sort_of_about", actor=workspace["owner"])


def test_relating_twice_is_idempotent(db, workspace):
    parent, child = _contract(db, workspace), _contract(db, workspace)
    first = repository_service.relate(db, parent, child, "addendum_of",
                                      actor=workspace["owner"])
    again = repository_service.relate(db, parent, child, "addendum_of",
                                      actor=workspace["owner"])
    assert first.id == again.id, "a duplicate link would double-count in the history tree"


def test_an_addendum_inherits_its_parents_context(db, workspace):
    """Retyping the counterparty on every addendum is where they diverge."""
    party = _party(db, workspace, "Acme Trading")
    parent = _contract(db, workspace, governing_law="Pakistan", department="Procurement")
    repository_service.link_contract_to_party(db, parent, party)
    child = _contract(db, workspace, title="Addendum 1", type="", governing_law="")

    repository_service.inherit_from_parent(child, parent)

    assert child.party_id == party.id
    assert child.counterparty == "Acme Trading"
    assert child.governing_law == "Pakistan"
    assert child.department == "Procurement"


def test_inheriting_does_not_overwrite_what_is_already_set(db, workspace):
    parent = _contract(db, workspace, governing_law="Pakistan")
    child = _contract(db, workspace, governing_law="England & Wales")
    repository_service.inherit_from_parent(child, parent)
    assert child.governing_law == "England & Wales"


def test_the_history_tree_shows_both_directions(db, workspace):
    parent = _contract(db, workspace, title="Master Agreement")
    middle = _contract(db, workspace, title="Amendment 1")
    leaf = _contract(db, workspace, title="Addendum to the amendment")
    repository_service.relate(db, parent, middle, "amendment_of", actor=workspace["owner"])
    repository_service.relate(db, middle, leaf, "addendum_of", actor=workspace["owner"])

    history = repository_service.history(db, middle)
    assert [a["title"] for a in history["ancestors"]] == ["Master Agreement"]
    assert [d["title"] for d in history["descendants"]] == ["Addendum to the amendment"]
    assert history["descendants"][0]["label"] == "addendum no. 1"


# ---------------------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------------------


def test_folder_paths_are_materialised(db, workspace):
    legal = repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                             actor=workspace["owner"])
    vendors = repository_service.create_folder(db, workspace["tenant"].id, "Vendors",
                                               legal.id, actor=workspace["owner"])
    assert legal.path == "/Legal"
    assert vendors.path == "/Legal/Vendors"


def test_a_duplicate_path_is_refused(db, workspace):
    repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                     actor=workspace["owner"])
    with pytest.raises(RepositoryError, match="already exists"):
        repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                         actor=workspace["owner"])


def test_moving_a_folder_rewrites_the_whole_subtree(db, workspace):
    legal = repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                             actor=workspace["owner"])
    archive = repository_service.create_folder(db, workspace["tenant"].id, "Archive", None,
                                               actor=workspace["owner"])
    vendors = repository_service.create_folder(db, workspace["tenant"].id, "Vendors",
                                               legal.id, actor=workspace["owner"])
    y2026 = repository_service.create_folder(db, workspace["tenant"].id, "2026", vendors.id,
                                             actor=workspace["owner"])

    repository_service.move_folder(db, vendors, archive.id, actor=workspace["owner"])

    assert vendors.path == "/Archive/Vendors"
    assert y2026.path == "/Archive/Vendors/2026", "a stale descendant path orphans the subtree"


def test_a_folder_cannot_be_moved_inside_itself(db, workspace):
    """A materialised path makes the cycle invisible afterwards — by the time anyone
    notices, the subtree is unreachable."""
    legal = repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                             actor=workspace["owner"])
    vendors = repository_service.create_folder(db, workspace["tenant"].id, "Vendors",
                                               legal.id, actor=workspace["owner"])
    with pytest.raises(RepositoryError, match="inside itself"):
        repository_service.move_folder(db, legal, vendors.id, actor=workspace["owner"])


def test_a_folder_cannot_contain_itself(db, workspace):
    legal = repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                             actor=workspace["owner"])
    with pytest.raises(RepositoryError, match="cannot contain itself"):
        repository_service.move_folder(db, legal, legal.id, actor=workspace["owner"])


def test_a_slash_in_a_folder_name_cannot_forge_a_path(db, workspace):
    """Otherwise "Legal/Secret" would create a node the tree cannot represent."""
    folder = repository_service.create_folder(db, workspace["tenant"].id, "Legal/Secret",
                                              None, actor=workspace["owner"])
    assert folder.path == "/Legal-Secret"


def test_role_visibility_filters_the_tree(db, workspace):
    repository_service.create_folder(db, workspace["tenant"].id, "Open", None,
                                     actor=workspace["owner"])
    repository_service.create_folder(db, workspace["tenant"].id, "Board", None,
                                     actor=workspace["owner"], roles=["owner"])
    db.flush()

    visible_to_owner = {f.name for f in repository_service.visible_folders(
        db, workspace["tenant"].id, "owner")}
    visible_to_author = {f.name for f in repository_service.visible_folders(
        db, workspace["tenant"].id, "author")}

    assert "Board" in visible_to_owner
    assert "Board" not in visible_to_author
    assert "Open" in visible_to_author, "an empty role list means everyone"


# ---------------------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------------------


def _field(db, ws, key, ftype="text", contract_type="", **kwargs) -> models.CustomFieldDef:
    d = models.CustomFieldDef(
        tenant_id=ws["tenant"].id, key=key, label=key.replace("_", " ").title(),
        type=ftype, contract_type=contract_type, created_by=ws["owner"].id, **kwargs,
    )
    db.add(d)
    db.flush()
    return d


def test_house_wide_and_type_specific_fields_both_apply(db, workspace):
    _field(db, workspace, "cost_centre")
    _field(db, workspace, "sla_tier", contract_type="vendor")
    _field(db, workspace, "premises", contract_type="lease")

    keys = {d.key for d in repository_service.field_defs(db, workspace["tenant"].id, "vendor")}
    assert keys == {"cost_centre", "sla_tier"}


def test_custom_values_are_validated_against_their_type(db, workspace):
    _field(db, workspace, "sla_tier", "select", options=["Gold", "Silver"])
    contract = _contract(db, workspace)
    with pytest.raises(RepositoryError, match="not one of the permitted values"):
        repository_service.validate_custom_fields(db, contract, {"sla_tier": "Bronze"})


def test_custom_values_are_stored_json_safe(db, workspace):
    """The column is JSON, so a date object would fail on write rather than on read."""
    _field(db, workspace, "review_date", "date")
    contract = _contract(db, workspace)
    cleaned = repository_service.validate_custom_fields(
        db, contract, {"review_date": "2026-09-01"})
    assert cleaned["review_date"] == "2026-09-01"


def test_a_required_custom_field_is_enforced(db, workspace):
    _field(db, workspace, "cost_centre", required=True)
    contract = _contract(db, workspace)
    with pytest.raises(RepositoryError, match="required"):
        repository_service.validate_custom_fields(db, contract, {})


def test_describing_fields_carries_the_current_values(db, workspace):
    _field(db, workspace, "cost_centre")
    contract = _contract(db, workspace)
    contract.custom_fields = {"cost_centre": "CC-100"}
    described = repository_service.describe_custom_fields(db, contract)
    assert described[0]["key"] == "cost_centre"
    assert described[0]["value"] == "CC-100"


# ---------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------


def test_free_text_matches_the_body(db, workspace):
    _contract(db, workspace, title="Acquiring Agreement",
              body="The Merchant shall pay a discount rate of 1.75%.")
    _contract(db, workspace, title="Lease", body="The premises are at 12 Main Street.")
    result = search_service.search(db, workspace["tenant"].id, q="discount rate")
    assert result["total"] == 1
    assert result["items"][0]["title"] == "Acquiring Agreement"


def test_a_reference_number_is_searchable(db, workspace):
    contract = _contract(db, workspace)
    result = search_service.search(db, workspace["tenant"].id, q=contract.reference_no)
    assert result["total"] == 1


def test_filters_narrow_the_result(db, workspace):
    _contract(db, workspace, status="active", risk_level="high")
    _contract(db, workspace, status="draft", risk_level="high")
    result = search_service.search(db, workspace["tenant"].id,
                                   filters={"status": ["active"]})
    assert result["total"] == 1


def test_a_value_band_filters(db, workspace):
    _contract(db, workspace, value=50_000)
    _contract(db, workspace, value=5_000_000)
    result = search_service.search(db, workspace["tenant"].id,
                                   filters={"value_min": 1_000_000})
    assert result["total"] == 1


def test_a_date_range_filters(db, workspace):
    _contract(db, workspace, effective_date=dt.date(2026, 1, 1))
    _contract(db, workspace, effective_date=dt.date(2027, 1, 1))
    result = search_service.search(db, workspace["tenant"].id,
                                   filters={"effective_from": "2026-06-01"})
    assert result["total"] == 1


def test_a_folder_filter_includes_everything_beneath_it(db, workspace):
    """The tree is what a user thinks they are filtering by, not one node of it."""
    legal = repository_service.create_folder(db, workspace["tenant"].id, "Legal", None,
                                             actor=workspace["owner"])
    vendors = repository_service.create_folder(db, workspace["tenant"].id, "Vendors",
                                               legal.id, actor=workspace["owner"])
    _contract(db, workspace, folder_id=legal.id)
    _contract(db, workspace, folder_id=vendors.id)
    _contract(db, workspace)
    db.flush()

    result = search_service.search(db, workspace["tenant"].id,
                                   filters={"folder_path": "/Legal"})
    assert result["total"] == 2


def test_archived_agreements_are_excluded_by_default(db, workspace):
    _contract(db, workspace)
    _contract(db, workspace, archived_at=dt.datetime(2026, 1, 1))
    db.flush()
    assert search_service.search(db, workspace["tenant"].id)["total"] == 1
    assert search_service.search(db, workspace["tenant"].id,
                                 filters={"include_archived": True})["total"] == 2


def test_a_clause_filter_finds_agreements_composing_it(db, workspace):
    wanted = _contract(db, workspace)
    wanted.included_clauses = [{"clause_id": "x", "key": "limitation_of_liability",
                                "version_no": 1, "title": "Liability"}]
    _contract(db, workspace)
    db.flush()

    result = search_service.search(db, workspace["tenant"].id,
                                   filters={"clause_key": "limitation_of_liability"})
    assert result["total"] == 1
    assert result["items"][0]["id"] == wanted.id


def test_another_tenants_agreements_never_appear(db, workspace, make_user):
    other_owner, other_tenant = make_user(email=f"o-{uuid.uuid4().hex[:8]}@example.com",
                                          name="Other")
    db.add(models.Contract(
        tenant_id=other_tenant.id, reference_no="X-1", title="Secret agreement",
        type="vendor", status="draft", owner_id=other_owner.id, created_by=other_owner.id,
        body="discount rate", value=1, currency="PKR",
    ))
    db.flush()
    result = search_service.search(db, workspace["tenant"].id, q="discount rate")
    assert result["total"] == 0


def test_facets_count_the_whole_result_not_the_page(db, workspace):
    """A facet describing one page would be actively misleading."""
    for _ in range(5):
        _contract(db, workspace, status="active")
    for _ in range(3):
        _contract(db, workspace, status="draft")
    db.flush()

    result = search_service.search(db, workspace["tenant"].id, page_size=2)
    assert len(result["items"]) == 2
    assert result["facets"]["status"] == {"active": 5, "draft": 3}


def test_paging_walks_the_whole_set(db, workspace):
    for i in range(7):
        _contract(db, workspace, title=f"Agreement {i}")
    db.flush()
    seen = set()
    for page in (1, 2, 3):
        for item in search_service.search(db, workspace["tenant"].id, page=page,
                                          page_size=3)["items"]:
            seen.add(item["id"])
    assert len(seen) == 7


# --- snippets ----------------------------------------------------------------------------


def test_a_snippet_highlights_the_query_terms():
    body = "The Merchant shall pay a merchant discount rate of 1.75% of each transaction."
    assert "**discount**" in search_service.snippet(body, "discount")


def test_a_snippet_is_trimmed_around_the_hit():
    body = ("padding " * 60) + "the liability cap applies " + ("padding " * 60)
    result = search_service.snippet(body, "liability")
    assert "**liability**" in result
    assert result.startswith("…") and result.endswith("…")
    assert len(result) < len(body)


def test_a_snippet_falls_back_to_the_opening_when_nothing_matches():
    """A result with no snippet at all reads as a bug."""
    assert search_service.snippet("Some contract text here.", "zzz").startswith("Some contract")


def test_an_empty_body_produces_no_snippet():
    assert search_service.snippet("", "anything") == ""
