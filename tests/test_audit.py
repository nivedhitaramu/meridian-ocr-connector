"""Audit events: what gets recorded, who can read it, and that it can't be changed."""
import os
import time
import uuid

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.db import models
from app.db.tenancy import set_scope
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)

is_postgres = (os.getenv("TEST_DATABASE_URL") or "").startswith("postgresql")
EXP = int(time.time()) + 3600


def bearer(sub, email, **claims):
    return {"Authorization": f"Bearer {token(sub=sub, email=email, exp=EXP, **claims)}"}


ALICE = bearer("user_alice", "alice@example.com")
BOB = bearer("user_bob", "bob@example.com")


def start_org(http, headers, name="Fictional Org"):
    response = http.post("/v1/organizations", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def events(http, headers, **params):
    response = http.get("/v1/audit-events", headers=headers, params=params)
    assert response.status_code == 200
    return response.json()


def add_member(http, make_session, organization_id, headers, role):
    user_id = uuid.UUID(http.get("/v1/me", headers=headers).json()["id"])
    with make_session() as session:
        session.add(models.OrganizationMember(organization_id=uuid.UUID(organization_id), user_id=user_id, role=role))
        session.commit()
    return str(user_id)


def test_creating_an_organization_is_recorded(client):  # noqa: F811
    http, _ = client
    org = start_org(http, ALICE)
    actor = http.get("/v1/me", headers=ALICE).json()["id"]
    [event] = events(http, ALICE)
    assert event["action"] == "organization.created"
    assert event["target"] == f"organization:{org}"
    assert event["actor_id"] == actor
    assert uuid.UUID(event["request_id"])


def test_role_change_is_recorded(client):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    bob_id = add_member(http, make_session, org, BOB, "clerk")
    assert http.patch(f"/v1/organization/members/{bob_id}", json={"role": "supervisor"}, headers=ALICE).status_code == 200
    newest = next(e for e in events(http, ALICE) if e["action"] != "organization.created")
    assert newest["action"] == "member.role_changed"
    assert newest["target"] == f"member:{bob_id}:supervisor"


def test_unchanged_role_records_nothing(client):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    bob_id = add_member(http, make_session, org, BOB, "clerk")
    http.patch(f"/v1/organization/members/{bob_id}", json={"role": "clerk"}, headers=ALICE)
    assert [e["action"] for e in events(http, ALICE)] == ["organization.created"]


def test_refused_change_records_nothing(client):  # noqa: F811
    http, _ = client
    start_org(http, ALICE)
    alice_id = http.get("/v1/me", headers=ALICE).json()["id"]
    assert http.patch(f"/v1/organization/members/{alice_id}", json={"role": "clerk"}, headers=ALICE).status_code == 409
    assert [e["action"] for e in events(http, ALICE)] == ["organization.created"]


def test_each_clerk_session_is_recorded_once(client):  # noqa: F811
    http, _ = client
    first = bearer("user_alice", "alice@example.com", sid="sess_one")
    second = bearer("user_alice", "alice@example.com", sid="sess_two")
    start_org(http, first)
    http.get("/v1/organization", headers=first)
    http.get("/v1/organization", headers=first)
    assert [e["action"] for e in events(http, first)].count("session.started") == 1
    http.get("/v1/organization", headers=second)
    assert [e["action"] for e in events(http, second)].count("session.started") == 2


def test_session_id_is_not_stored(client):  # noqa: F811
    http, _ = client
    headers = bearer("user_alice", "alice@example.com", sid="sess_secretvalue")
    start_org(http, headers)
    http.get("/v1/organization", headers=headers)
    assert "sess_secretvalue" not in str(events(http, headers))


def test_events_hold_no_names_or_emails(client):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE, "Very Specific Org Name")
    bob_id = add_member(http, make_session, org, BOB, "clerk")
    http.patch(f"/v1/organization/members/{bob_id}", json={"role": "supervisor"}, headers=ALICE)
    text = str(events(http, ALICE))
    assert "example.com" not in text and "Very Specific" not in text


def test_another_tenant_cannot_read_events(client):  # noqa: F811
    http, _ = client
    alice_org = start_org(http, ALICE)
    start_org(http, BOB)
    assert alice_org not in str(events(http, BOB))
    assert http.get("/v1/audit-events", headers={**BOB, "X-Organization-Id": alice_org}).status_code == 404


@pytest.mark.parametrize("role", ["clerk", "supervisor"])
def test_only_admins_can_read_events(client, role):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    add_member(http, make_session, org, BOB, role)
    assert http.get("/v1/audit-events", headers=BOB).status_code == 403


def test_not_signed_in_is_a_401(client):  # noqa: F811
    assert client[0].get("/v1/audit-events").status_code == 401


def test_limit_is_applied_and_bounded(client):  # noqa: F811
    http, make_session = client
    org = start_org(http, ALICE)
    bob_id = add_member(http, make_session, org, BOB, "clerk")
    http.patch(f"/v1/organization/members/{bob_id}", json={"role": "supervisor"}, headers=ALICE)
    assert len(events(http, ALICE, limit=1)) == 1
    assert http.get("/v1/audit-events", headers=ALICE, params={"limit": 0}).status_code == 422
    assert http.get("/v1/audit-events", headers=ALICE, params={"limit": 201}).status_code == 422


@pytest.mark.skipif(not is_postgres, reason="needs PostgreSQL")
def test_signed_in_requests_cannot_change_or_delete_events(client):  # noqa: F811
    http, make_session = client
    org = uuid.UUID(start_org(http, ALICE))
    alice_id = uuid.UUID(http.get("/v1/me", headers=ALICE).json()["id"])
    for statement in (update(models.AuditEvent).values(action="edited"), delete(models.AuditEvent)):
        with make_session() as session:
            set_scope(session, alice_id, org)
            with pytest.raises(DBAPIError):
                session.execute(statement)
    with make_session() as session:
        set_scope(session, alice_id, org)
        assert session.scalars(select(models.AuditEvent.action)).all() == ["organization.created"]
