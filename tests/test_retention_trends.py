"""Retention settings, the deletion they cause, and trends from saved data."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models
from app.worker import retention
from test_auth import client, clerk_settings  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, BOB, api, new_shipment, start_org, upload  # noqa: F401
from test_reviews import add_member, mismatch, review, run_job


@pytest.fixture
def kept(api, monkeypatch):  # noqa: F811
    http, make_session, store, delivered = api
    monkeypatch.setattr(retention, "new_session", make_session)
    monkeypatch.setattr(retention, "store", lambda: store)
    return http, make_session, store, delivered


def age(make_session, reference, days):
    with make_session() as session:
        shipment = session.query(models.Shipment).filter_by(reference=reference).one()
        shipment.created_at = datetime.now(timezone.utc) - timedelta(days=days)
        session.commit()


def references(http):
    return {row["reference"] for row in http.get("/v1/shipments", headers=ALICE).json()}


def test_nothing_is_deleted_unless_an_admin_turns_it_on(kept):
    http, make_session, _, delivered = kept
    start_org(http)
    run_job(http, delivered, "MF-OLD")
    age(make_session, "MF-OLD", 4000)
    assert retention.apply_all() == 0
    assert references(http) == {"MF-OLD"}


def test_only_expired_records_are_deleted_and_the_audit_trail_stays(kept, monkeypatch):
    http, make_session, _, delivered = kept
    start_org(http)
    mismatch(monkeypatch)
    old_job = run_job(http, delivered, "MF-OLD")
    review(http, old_job)
    run_job(http, delivered, "MF-NEW")
    age(make_session, "MF-OLD", 40)
    assert http.patch("/v1/organization/retention", headers=ALICE, json={"days": 30}).status_code == 200
    assert http.get("/v1/organization", headers=ALICE).json()["retention_days"] == 30
    assert retention.apply_all() == 1
    assert references(http) == {"MF-NEW"}
    assert http.get(f"/v1/jobs/{old_job}", headers=ALICE).status_code == 404
    with make_session() as session:
        assert session.query(models.ReviewAction).count() == 0
        assert session.query(models.VerificationResult).count() == 1
        assert session.query(models.ExtractionResult).count() == 1
    actions = [event["action"] for event in http.get("/v1/audit-events", headers=ALICE).json()]
    assert "retention.changed" in actions and "retention.applied" in actions and "review.recorded" in actions


def test_a_shipment_with_a_running_job_is_kept(kept):
    http, make_session, _, _ = kept
    org = start_org(http)
    shipment = new_shipment(http, reference="MF-BUSY")
    upload(http, shipment)
    assert http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).status_code == 202
    age(make_session, "MF-BUSY", 40)
    assert retention.apply(uuid.UUID(org), 30) == 0
    assert references(http) == {"MF-BUSY"}


def test_waiting_uploads_are_deleted_with_their_shipment(kept):
    http, make_session, store, _ = kept
    org = start_org(http)
    shipment = new_shipment(http, reference="MF-WAIT")
    upload(http, shipment)
    with make_session() as session:
        key = session.query(models.Document).one().storage_key
    assert store.get(key)
    age(make_session, "MF-WAIT", 40)
    assert retention.apply(uuid.UUID(org), 30) == 1
    with pytest.raises(OSError):
        store.get(key)


def test_retention_stays_in_its_organization(kept):
    http, make_session, _, delivered = kept
    org = start_org(http)
    run_job(http, delivered, "MF-MINE")
    http.post("/v1/organizations", headers=BOB, json={"name": "Other"})
    http.post("/v1/shipments", headers=BOB, json={"reference": "MF-THEIRS"})
    age(make_session, "MF-MINE", 40)
    age(make_session, "MF-THEIRS", 40)
    assert retention.apply(uuid.UUID(org), 30) == 1
    assert [row["reference"] for row in http.get("/v1/shipments", headers=BOB).json()] == ["MF-THEIRS"]


@pytest.mark.parametrize("days", [0, 6, 4000, -1])
def test_unsafe_retention_is_refused(api, days):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    assert http.patch("/v1/organization/retention", headers=ALICE, json={"days": days}).status_code == 422


def test_only_admins_set_retention_and_it_can_be_turned_off(api):  # noqa: F811
    http, make_session, _, _ = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, "supervisor")
    assert http.patch("/v1/organization/retention", headers=BOB, json={"days": 30}).status_code == 403
    assert http.patch("/v1/organization/retention", headers=ALICE, json={"days": None}).status_code == 200


def test_trends_come_from_saved_data(api, monkeypatch):  # noqa: F811
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered, "MF-1")
    mismatch(monkeypatch)
    job = run_job(http, delivered, "MF-2")
    review(http, job, corrected_quantity=118)
    trends = http.get("/v1/analytics/trends", headers=ALICE).json()
    assert trends["daily"][0]["jobs"] == 2 and trends["daily"][0]["mismatches"] == 1
    assert trends["suppliers"] == [{"name": "Kestrel Exports", "shipments": 2, "mismatches": 1}]
    assert trends["checks"] == 2 and trends["corrected_checks"] == 1


def test_trends_never_name_a_masked_person_or_another_organization(api, monkeypatch):  # noqa: F811
    from test_jobs import fake_response
    from app.pipeline import runner
    http, _, _, delivered = api
    start_org(http)

    def person(files):
        response = fake_response(files=files)
        for document in response.documents:
            document.fields.shipper_name = "<PERSON_1>"
        return response
    monkeypatch.setattr(runner, "run", person)
    run_job(http, delivered)
    assert http.get("/v1/analytics/trends", headers=ALICE).json()["suppliers"] == []
    http.post("/v1/organizations", headers=BOB, json={"name": "Other"})
    other = http.get("/v1/analytics/trends", headers=BOB).json()
    assert other["daily"] == [] and other["checks"] == 0


def test_empty_trends_are_valid(api):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    assert http.get("/v1/analytics/trends", params={"days": 7}, headers=ALICE).json() == {
        "days": 7, "daily": [], "suppliers": [], "checks": 0, "corrected_checks": 0}
