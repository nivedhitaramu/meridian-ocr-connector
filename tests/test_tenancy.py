"""Tenant isolation at API level on any database, and at database level on PostgreSQL (TEST_DATABASE_URL in CI)."""
import os
import time
import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import models
from app.db.models import Base
from app.db.tenancy import set_scope
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)

is_postgres = (os.getenv("TEST_DATABASE_URL") or "").startswith("postgresql")
needs_postgres = pytest.mark.skipif(not is_postgres, reason="row-level security needs PostgreSQL")
GLOBAL_TABLES = {"organizations", "users"}

ALICE = {"Authorization": f"Bearer {token(sub='user_alice', email='alice@example.com', exp=int(time.time()) + 3600)}"}
BOB = {"Authorization": f"Bearer {token(sub='user_bob', email='bob@example.com', exp=int(time.time()) + 3600)}"}


def start_org(http, headers, name="Fictional Org"):
    response = http.post("/v1/organizations", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def add_shipment(make_session, organization_id, reference="MF-1"):
    with make_session() as session:
        shipment = models.Shipment(organization_id=uuid.UUID(organization_id), reference=reference)
        session.add(shipment)
        session.commit()
        return str(shipment.id)


def add_member(http, make_session, organization_id, headers, role):
    user_id = uuid.UUID(http.get("/v1/me", headers=headers).json()["id"])
    with make_session() as session:
        session.add(models.OrganizationMember(organization_id=uuid.UUID(organization_id), user_id=user_id, role=role))
        session.commit()
    return str(user_id)


def test_creator_becomes_admin(client):  # noqa: F811
    http, _ = client
    start_org(http, ALICE, "Alice Org")
    body = http.get("/v1/organization", headers=ALICE).json()
    assert body["name"] == "Alice Org" and body["role"] == "admin"


def test_another_tenants_shipment_is_a_404(client):  # noqa: F811
    http, make_session = client
    alice_org, bob_org = start_org(http, ALICE), start_org(http, BOB)
    alice_shipment = add_shipment(make_session, alice_org)
    assert http.get(f"/v1/shipments/{alice_shipment}", headers=ALICE).status_code == 200
    response = http.get(f"/v1/shipments/{alice_shipment}", headers=BOB)
    assert response.status_code == 404 and response.json() == {"error": "Not found."}
    assert http.get(f"/v1/shipments/{uuid.uuid4()}", headers=BOB).status_code == 404
    assert bob_org != alice_org


def test_header_cannot_reach_an_organization_you_dont_belong_to(client):  # noqa: F811
    http, make_session = client
    alice_org = start_org(http, ALICE)
    start_org(http, BOB)
    shipment = add_shipment(make_session, alice_org)
    headers = {**BOB, "X-Organization-Id": alice_org}
    assert http.get("/v1/organization", headers=headers).status_code == 404
    assert http.get(f"/v1/shipments/{shipment}", headers=headers).status_code == 404


def test_several_organizations_need_a_choice(client):  # noqa: F811
    http, _ = client
    first, second = start_org(http, ALICE, "First"), start_org(http, ALICE, "Second")
    assert http.get("/v1/organization", headers=ALICE).status_code == 404
    assert http.get("/v1/organization", headers={**ALICE, "X-Organization-Id": second}).json()["name"] == "Second"
    assert http.get("/v1/organization", headers={**ALICE, "X-Organization-Id": first}).json()["name"] == "First"


def test_no_organization_yet_is_a_404(client):  # noqa: F811
    assert client[0].get("/v1/organization", headers=ALICE).status_code == 404


def test_not_signed_in_is_a_401(client):  # noqa: F811
    assert client[0].get("/v1/organization").status_code == 401


@pytest.mark.parametrize("role,members,change", [("clerk", 403, 403), ("supervisor", 200, 403), ("admin", 200, 200)])
def test_roles_limit_actions(client, role, members, change):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    add_member(http, make_session, org, BOB, role)
    assert http.get("/v1/organization/members", headers=BOB).status_code == members
    alice_id = http.get("/v1/me", headers=ALICE).json()["id"]
    response = http.patch(f"/v1/organization/members/{alice_id}", json={"role": "admin"}, headers=BOB)
    assert response.status_code == change


def test_last_admin_cannot_be_demoted(client):  # noqa: F811
    http, _ = client
    start_org(http, ALICE)
    alice_id = http.get("/v1/me", headers=ALICE).json()["id"]
    assert http.patch(f"/v1/organization/members/{alice_id}", json={"role": "clerk"}, headers=ALICE).status_code == 409


def test_role_must_be_a_known_one(client):  # noqa: F811
    http, _ = client
    start_org(http, ALICE)
    alice_id = http.get("/v1/me", headers=ALICE).json()["id"]
    assert http.patch(f"/v1/organization/members/{alice_id}", json={"role": "owner"}, headers=ALICE).status_code == 422


def test_member_list_shows_only_this_organization(client):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    start_org(http, BOB)
    emails = [m["email"] for m in http.get("/v1/organization/members", headers=ALICE).json()]
    assert emails == ["alice@example.com"]
    assert org


# ---------------------------------------------------------------- database level
@pytest.fixture
def two_tenants(client):  # noqa: F811
    _, make_session = client
    with make_session() as session:
        users = [models.User(external_id=f"user_{i}", email=f"{i}@example.com") for i in range(2)]
        orgs = [models.Organization(name=f"Org {i}") for i in range(2)]
        session.add_all(users + orgs)
        session.flush()
        for user, org in zip(users, orgs):
            session.add(models.OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
        shipments = [models.Shipment(organization_id=org.id, reference="MF-1") for org in orgs]
        session.add_all(shipments)
        session.commit()
        return make_session, [u.id for u in users], [o.id for o in orgs], [s.id for s in shipments]


@needs_postgres
def test_every_tenant_table_has_forced_row_level_security(client):  # noqa: F811
    _, make_session = client
    with make_session() as session:
        rows = session.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                                    "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace")).all()
    secured = {name for name, enabled, forced in rows if enabled and forced}
    assert set(Base.metadata.tables) - GLOBAL_TABLES <= secured


@needs_postgres
def test_query_without_a_filter_only_sees_the_current_tenant(two_tenants):
    make_session, users, orgs, shipments = two_tenants
    with make_session() as session:
        set_scope(session, users[0], orgs[0])
        assert session.execute(select(models.Shipment.id)).scalars().all() == [shipments[0]]
        assert session.get(models.Shipment, shipments[1]) is None


@needs_postgres
def test_cannot_write_into_or_change_another_tenant(two_tenants):
    make_session, users, orgs, shipments = two_tenants
    with make_session() as session:
        set_scope(session, users[0], orgs[0])
        changed = session.execute(update(models.Shipment).where(models.Shipment.id == shipments[1]).values(status="stolen"))
        assert changed.rowcount == 0
        session.rollback()
        set_scope(session, users[0], orgs[0])
        session.add(models.Shipment(organization_id=orgs[1], reference="MF-INJECTED"))
        with pytest.raises(DBAPIError):
            session.flush()


@needs_postgres
def test_no_organization_chosen_sees_no_tenant_rows(two_tenants):
    make_session, users, _, _ = two_tenants
    with make_session() as session:
        set_scope(session, users[0])
        assert session.execute(select(models.Shipment.id)).scalars().all() == []


@needs_postgres
def test_memberships_show_your_own_rows_only(two_tenants):
    make_session, users, orgs, _ = two_tenants
    with make_session() as session:
        set_scope(session, users[0])
        rows = session.execute(select(models.OrganizationMember.organization_id)).scalars().all()
        assert rows == [orgs[0]]


@needs_postgres
def test_scope_survives_a_commit(two_tenants):
    make_session, users, orgs, shipments = two_tenants
    with make_session() as session:
        set_scope(session, users[0], orgs[0])
        session.commit()
        assert session.execute(select(models.Shipment.id)).scalars().all() == [shipments[0]]


@needs_postgres
def test_restricted_role_is_not_a_superuser(client):  # noqa: F811
    _, make_session = client
    with Session(make_session.kw["bind"]) as session:
        row = session.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'meridian_app'")).one()
    assert row == (False, False)
