"""Joining an organization: an admin invites an email, and only the person with that email can accept."""
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.db import models
from app.db.tenancy import set_invitee, set_scope
from app.worker import retention
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)
from test_tenancy import needs_postgres

EXP = int(time.time()) + 3600


def bearer(name, email=None):
    return {"Authorization": f"Bearer {token(sub=f'user_{name}', email=email or f'{name}@example.com', exp=EXP)}"}


ALICE, BOB, CARA = bearer("alice"), bearer("bob"), bearer("cara")


def start_org(http, headers=ALICE, name="Fictional Org"):
    return http.post("/v1/organizations", json={"name": name}, headers=headers).json()["id"]


def invite(http, email="bob@example.com", role="clerk", headers=ALICE):
    return http.post("/v1/organization/invitations", json={"email": email, "role": role}, headers=headers)


def mine(http, headers=BOB):
    return http.get("/v1/invitations", headers=headers).json()


def actions(http):
    return [e["action"] for e in http.get("/v1/audit-events", headers=ALICE).json()]


def expire(make_session, invitation_id):
    with make_session() as session:  # no scope, so this runs as the database owner, as test set-up
        session.get(models.OrganizationInvitation, uuid.UUID(invitation_id)).expires_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        session.commit()


def test_invited_person_joins_only_after_accepting(client):  # noqa: F811
    http, _ = client
    org = start_org(http)
    invitation = invite(http, " BOB@Example.com ", "supervisor").json()
    assert invitation["email"] == "bob@example.com" and invitation["expired"] is False

    assert http.get("/v1/me", headers=BOB).json()["memberships"] == []  # being invited gives no access
    assert http.get("/v1/organization", headers=BOB).status_code == 404

    [offer] = mine(http)
    assert offer["organization_name"] == "Fictional Org" and offer["invited_by"] == "alice@example.com"
    accepted = http.post(f"/v1/invitations/{offer['id']}/accept", headers=BOB)
    assert accepted.status_code == 200 and accepted.json() == {"organization_id": org, "role": "supervisor"}
    assert http.get("/v1/organization", headers=BOB).json()["role"] == "supervisor"
    assert mine(http) == []
    assert http.get("/v1/organization/invitations", headers=ALICE).json() == []
    assert "member.invited" in actions(http) and "member.added" in actions(http)


def test_answer_is_the_same_with_or_without_an_account(client):  # noqa: F811
    http, _ = client
    start_org(http)
    http.get("/v1/me", headers=BOB)  # Bob has an account, and the stranger doesn't
    known, unknown = invite(http, "bob@example.com"), invite(http, "stranger@example.com")
    assert known.status_code == unknown.status_code == 201
    assert set(known.json()) == set(unknown.json())


def test_invitation_works_for_someone_who_signs_up_later(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invite(http, "bob@example.com")
    assert len(mine(http)) == 1  # the first request here is also Bob's first sign-in


def test_someone_else_cannot_see_accept_or_decline_it(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    assert mine(http, CARA) == []
    assert http.post(f"/v1/invitations/{invitation['id']}/accept", headers=CARA).status_code == 404
    assert http.post(f"/v1/invitations/{invitation['id']}/decline", headers=CARA).status_code == 404
    assert http.get("/v1/organization", headers=CARA).status_code == 404
    assert len(mine(http)) == 1


def test_role_comes_from_the_invitation_not_the_request(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http, role="clerk").json()
    response = http.post(f"/v1/invitations/{invitation['id']}/accept", json={"role": "admin"}, headers=BOB)
    assert response.json()["role"] == "clerk"
    assert http.get("/v1/organization", headers=BOB).json()["role"] == "clerk"


def test_an_invitation_works_once(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    assert http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB).status_code == 200
    assert http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB).status_code == 404


def test_declining_gives_no_access_and_is_recorded(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    assert http.post(f"/v1/invitations/{invitation['id']}/decline", headers=BOB).status_code == 204
    assert http.get("/v1/organization", headers=BOB).status_code == 404
    assert mine(http) == []
    assert "invitation.declined" in actions(http)


def test_admin_can_cancel_and_then_it_cannot_be_accepted(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    assert http.delete(f"/v1/organization/invitations/{invitation['id']}", headers=ALICE).status_code == 204
    assert http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB).status_code == 404
    assert "invitation.cancelled" in actions(http)


def test_expired_invitation_cannot_be_seen_or_accepted(client):  # noqa: F811
    http, make_session = client
    start_org(http)
    invitation = invite(http).json()
    expire(make_session, invitation["id"])
    assert mine(http) == []
    assert http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB).status_code == 404
    assert http.post(f"/v1/invitations/{invitation['id']}/decline", headers=BOB).status_code == 404
    assert http.get("/v1/organization/invitations", headers=ALICE).json()[0]["expired"] is True


def test_inviting_again_replaces_the_role_and_restarts_the_time_limit(client):  # noqa: F811
    http, make_session = client
    start_org(http)
    first = invite(http, role="clerk").json()
    expire(make_session, first["id"])
    second = invite(http, role="supervisor").json()
    assert second["id"] == first["id"] and second["expired"] is False
    assert [o["role"] for o in mine(http)] == ["supervisor"]


@pytest.mark.parametrize("role,expected", [("clerk", 403), ("supervisor", 403)])
def test_only_admins_invite_or_see_invitations(client, role, expected):  # noqa: F811
    http, _ = client
    start_org(http)
    accepted = invite(http, "bob@example.com", role).json()
    http.post(f"/v1/invitations/{accepted['id']}/accept", headers=BOB)
    pending = invite(http, "cara@example.com").json()
    assert invite(http, "dan@example.com", "admin", BOB).status_code == expected
    assert http.get("/v1/organization/invitations", headers=BOB).status_code == expected
    assert http.delete(f"/v1/organization/invitations/{pending['id']}", headers=BOB).status_code == expected


def test_admin_cannot_cancel_another_organizations_invitation(client):  # noqa: F811
    http, _ = client
    start_org(http)
    start_org(http, CARA, "Cara Org")
    other = invite(http, "bob@example.com", headers=CARA).json()
    assert http.delete(f"/v1/organization/invitations/{other['id']}", headers=ALICE).status_code == 404
    assert len(mine(http)) == 1


def test_inviting_a_member_is_refused(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB)
    assert invite(http).status_code == 409


def test_bad_email_is_refused(client):  # noqa: F811
    http, _ = client
    start_org(http)
    assert invite(http, "not-an-email").status_code == 422


def test_events_hold_no_emails(client):  # noqa: F811
    http, _ = client
    start_org(http)
    invitation = invite(http).json()
    http.post(f"/v1/invitations/{invitation['id']}/accept", headers=BOB)
    assert "example.com" not in str(http.get("/v1/audit-events", headers=ALICE).json())


def test_nightly_task_removes_expired_invitations(client, monkeypatch):  # noqa: F811
    http, make_session = client
    monkeypatch.setattr(retention, "new_session", make_session)
    start_org(http)
    gone, kept = invite(http).json(), invite(http, "cara@example.com").json()
    expire(make_session, gone["id"])
    retention.apply_all()
    assert [i["id"] for i in http.get("/v1/organization/invitations", headers=ALICE).json()] == [kept["id"]]


@needs_postgres
def test_database_only_shows_an_invitee_their_own_invitations(client):  # noqa: F811
    http, make_session = client
    start_org(http)
    invite(http, "bob@example.com")
    invite(http, "cara@example.com")
    with make_session() as session:
        set_scope(session, None)
        emails = lambda: list(session.scalars(select(models.OrganizationInvitation.email)))  # noqa: E731
        assert emails() == []  # no organization and no email chosen
        set_invitee(session, "bob@example.com")
        assert emails() == ["bob@example.com"]  # a query with no filter still can't see Cara's


@needs_postgres
def test_invitee_scope_cannot_change_an_invitation(client):  # noqa: F811
    http, make_session = client
    start_org(http)
    invitation = invite(http).json()
    with make_session() as session:
        set_scope(session, None)
        set_invitee(session, "bob@example.com")
        changed = session.execute(update(models.OrganizationInvitation).where(
            models.OrganizationInvitation.id == uuid.UUID(invitation["id"])).values(role="admin"))
        assert changed.rowcount == 0  # an invitee can read it, but can't change it
        session.commit()
    assert mine(http)[0]["role"] == "clerk"
