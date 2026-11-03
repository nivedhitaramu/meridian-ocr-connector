"""Organization settings: renaming, adding and removing members, and what each records."""
import time
import uuid

import pytest

from app.db import models
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)

EXP = int(time.time()) + 3600


def bearer(name):
    return {"Authorization": f"Bearer {token(sub=f'user_{name}', email=f'{name}@example.com', exp=EXP)}"}


ALICE, BOB, CARA = bearer("alice"), bearer("bob"), bearer("cara")


def start_org(http, headers=ALICE, name="Fictional Org"):
    return http.post("/v1/organizations", json={"name": name}, headers=headers).json()["id"]


def sign_in(http, headers):
    return http.get("/v1/me", headers=headers).json()["id"]


def add(http, email, role="clerk", headers=ALICE):
    return http.post("/v1/organization/members", json={"email": email, "role": role}, headers=headers)


def actions(http):
    return [e["action"] for e in http.get("/v1/audit-events", headers=ALICE).json()]


def test_admin_can_rename_and_it_is_recorded(client):  # noqa: F811
    http, _ = client
    start_org(http)
    assert http.patch("/v1/organization", json={"name": "  New Name "}, headers=ALICE).json()["name"] == "New Name"
    assert http.get("/v1/organization", headers=ALICE).json()["name"] == "New Name"
    assert "organization.renamed" in actions(http)


def test_same_name_records_nothing(client):  # noqa: F811
    http, _ = client
    start_org(http)
    http.patch("/v1/organization", json={"name": "Fictional Org"}, headers=ALICE)
    assert actions(http) == ["organization.created"]


def test_blank_name_is_refused(client):  # noqa: F811
    http, _ = client
    start_org(http)
    assert http.patch("/v1/organization", json={"name": ""}, headers=ALICE).status_code == 422


def test_add_member_by_email_any_case(client):  # noqa: F811
    http, _ = client
    start_org(http)
    bob_id = sign_in(http, BOB)
    response = add(http, " BOB@Example.com ", "supervisor")
    assert response.status_code == 201 and response.json() == {"user_id": bob_id, "role": "supervisor"}
    assert http.get("/v1/organization", headers=BOB).json()["role"] == "supervisor"
    assert "member.added" in actions(http)


def test_adding_someone_who_never_signed_in_is_a_404(client):  # noqa: F811
    http, _ = client
    start_org(http)
    assert add(http, "stranger@example.com").status_code == 404
    assert actions(http) == ["organization.created"]


def test_adding_an_existing_member_is_a_409(client):  # noqa: F811
    http, _ = client
    start_org(http)
    sign_in(http, BOB)
    add(http, "bob@example.com")
    assert add(http, "bob@example.com").status_code == 409


@pytest.mark.parametrize("role", ["clerk", "supervisor"])
def test_only_admins_can_change_the_organization(client, role):  # noqa: F811
    http, _ = client
    start_org(http)
    bob_id, _ = sign_in(http, BOB), sign_in(http, CARA)
    add(http, "bob@example.com", role)
    assert http.patch("/v1/organization", json={"name": "Taken"}, headers=BOB).status_code == 403
    assert add(http, "cara@example.com", headers=BOB).status_code == 403
    assert http.delete(f"/v1/organization/members/{bob_id}", headers=BOB).status_code == 403


def test_remove_member_ends_their_access(client):  # noqa: F811
    http, _ = client
    start_org(http)
    bob_id = sign_in(http, BOB)
    add(http, "bob@example.com")
    assert http.delete(f"/v1/organization/members/{bob_id}", headers=ALICE).status_code == 204
    assert http.get("/v1/organization", headers=BOB).status_code == 404
    assert "member.removed" in actions(http)


def test_last_admin_cannot_be_removed(client):  # noqa: F811
    http, _ = client
    start_org(http)
    alice_id = sign_in(http, ALICE)
    assert http.delete(f"/v1/organization/members/{alice_id}", headers=ALICE).status_code == 409
    assert http.get("/v1/organization", headers=ALICE).status_code == 200


def test_cannot_remove_a_member_of_another_organization(client):  # noqa: F811
    http, _ = client
    start_org(http)
    start_org(http, BOB, "Bob Org")
    bob_id = sign_in(http, BOB)
    assert http.delete(f"/v1/organization/members/{bob_id}", headers=ALICE).status_code == 404
    assert http.get("/v1/organization", headers=BOB).status_code == 200


def test_settings_events_hold_no_emails(client):  # noqa: F811
    http, _ = client
    start_org(http)
    sign_in(http, BOB)
    add(http, "bob@example.com")
    assert "example.com" not in str(http.get("/v1/audit-events", headers=ALICE).json())


def test_member_with_reviews_cannot_be_removed(client):  # noqa: F811
    http, make_session = client
    org = uuid.UUID(start_org(http))
    bob_id = uuid.UUID(sign_in(http, BOB))
    add(http, "bob@example.com")
    with make_session() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("SQLite doesn't enforce foreign keys here")
        shipment = models.Shipment(organization_id=org, reference="MF-1")
        session.add(shipment)
        session.flush()
        job = models.ProcessingJob(organization_id=org, shipment_id=shipment.id)
        session.add(job)
        session.flush()
        result = models.VerificationResult(organization_id=org, job_id=job.id, status="Match", reason="Equal.")
        session.add(result)
        session.flush()
        session.add(models.ReviewAction(organization_id=org, verification_result_id=result.id, reviewer_id=bob_id, action="approve"))
        session.commit()
    assert http.delete(f"/v1/organization/members/{bob_id}", headers=ALICE).status_code == 409
    assert http.get("/v1/organization", headers=BOB).status_code == 200
