"""A contract's department name and its department record stay in step.

`Contract` carries both a free-text `department` and a `department_id`. The id is what the
analytics segmentation, the obligation filter, the guidance prefill and the per-department
contract count join on — and nothing wrote it, so all four read a column that was always NULL
and every department reported holding nothing.
"""

import uuid

import pytest

from app import models


@pytest.fixture()
def workspace(db, make_user):
    owner, tenant = make_user(email=f"dept-{uuid.uuid4().hex[:8]}@example.com", name="Owner")
    return {"tenant": tenant, "owner": owner}


def _department(db, ws, name: str) -> models.Department:
    d = models.Department(tenant_id=ws["tenant"].id, name=name)
    db.add(d)
    db.flush()
    return d


def _contract(db, ws, department: str) -> models.Contract:
    from app.routers.contracts import _link_department

    c = models.Contract(
        tenant_id=ws["tenant"].id, reference_no=f"CM-{uuid.uuid4().hex[:6]}",
        title="Vendor Services Agreement", type="vendor", status="draft",
        owner_id=ws["owner"].id, created_by=ws["owner"].id, department=department,
    )
    _link_department(db, c)
    db.add(c)
    db.flush()
    return c


def test_the_name_resolves_to_the_record(db, workspace):
    procurement = _department(db, workspace, "Procurement")

    c = _contract(db, workspace, "Procurement")

    assert c.department_id == procurement.id


def test_matching_ignores_case(db, workspace):
    """A department typed in a different case is the same department, not a new one."""
    procurement = _department(db, workspace, "Procurement")

    c = _contract(db, workspace, "  pROCUREMENT ")

    assert c.department_id == procurement.id


def test_a_department_with_no_record_leaves_the_link_unset(db, workspace):
    """A real state, not an error — the name is still stored and still reported on."""
    c = _contract(db, workspace, "Somewhere Unrecorded")

    assert c.department_id is None
    assert c.department == "Somewhere Unrecorded"


def test_clearing_the_department_clears_the_link(db, workspace):
    """Otherwise an agreement keeps counting towards a department it no longer belongs to."""
    from app.routers.contracts import _link_department

    _department(db, workspace, "Procurement")
    c = _contract(db, workspace, "Procurement")
    assert c.department_id is not None

    c.department = ""
    _link_department(db, c)

    assert c.department_id is None


def test_a_department_in_another_workspace_is_not_matched(db, make_user):
    """Name matching must not reach across the workspace boundary."""
    from app.routers.contracts import _link_department

    owner_a, tenant_a = make_user(email=f"a-{uuid.uuid4().hex[:8]}@example.com", name="A")
    owner_b, tenant_b = make_user(email=f"b-{uuid.uuid4().hex[:8]}@example.com", name="B")

    db.add(models.Department(tenant_id=tenant_b.id, name="Procurement"))
    db.flush()

    c = models.Contract(
        tenant_id=tenant_a.id, reference_no=f"CM-{uuid.uuid4().hex[:6]}", title="X",
        type="vendor", status="draft", owner_id=owner_a.id, created_by=owner_a.id,
        department="Procurement",
    )
    _link_department(db, c)

    assert c.department_id is None


def test_the_count_follows_the_link(db, workspace):
    """What the Departments screen actually shows."""
    procurement = _department(db, workspace, "Procurement")
    _department(db, workspace, "Legal")
    _contract(db, workspace, "Procurement")
    _contract(db, workspace, "Procurement")
    _contract(db, workspace, "Legal")

    held = db.query(models.Contract).filter_by(
        tenant_id=workspace["tenant"].id, department_id=procurement.id).count()

    assert held == 2
