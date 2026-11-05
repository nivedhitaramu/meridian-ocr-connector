"""Exceptions, human review and summaries."""
import time
import uuid

import pytest

from app.core.errors import PipelineError
from app.db import models
from app.pipeline import runner
from app.worker import jobs
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, BOB, api, fake_response, new_shipment, start_org, upload  # noqa: F401

EXP = int(time.time()) + 3600
CARA = {"Authorization": f"Bearer {token(sub='user_cara', email='cara@example.com', exp=EXP)}"}


def run_job(http, delivered, reference="MF-1"):
    shipment = new_shipment(http, reference=reference)
    upload(http, shipment)
    job_id = http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).json()["id"]
    jobs.process(*delivered[-1])
    return job_id


def mismatch(monkeypatch):
    monkeypatch.setattr(runner, "run", lambda files: fake_response(status="Mismatch", files=files))


def blocked(monkeypatch):
    def fail(files):
        raise PipelineError("manual_review_residual_pii")
    monkeypatch.setattr(runner, "run", fail)


def add_member(http, make_session, org, headers, role):
    user_id = uuid.UUID(http.get("/v1/me", headers=headers).json()["id"])
    with make_session() as session:
        session.add(models.OrganizationMember(organization_id=uuid.UUID(org), user_id=user_id, role=role))
        session.commit()


def review(http, job_id, headers=ALICE, **body):
    return http.post(f"/v1/jobs/{job_id}/reviews", headers=headers, json={"action": "resolve", "reason": "Recounted on the dock.", **body})


def test_matches_are_not_exceptions(api):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    assert http.get("/v1/exceptions", headers=ALICE).json() == []


def test_mismatch_and_manual_review_are_exceptions(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    first = run_job(http, delivered, "MF-1")
    blocked(monkeypatch)
    second = run_job(http, delivered, "MF-2")
    items = {item["job_id"]: item for item in http.get("/v1/exceptions", headers=ALICE).json()}
    assert items[first]["check_status"] == "Mismatch" and items[first]["reference"] == "MF-1"
    assert items[second]["job_status"] == "manual_review" and items[second]["error_class"] == "manual_review_residual_pii"


def test_resolving_clears_it_and_is_audited(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    job_id = run_job(http, delivered)
    assert review(http, job_id).status_code == 201
    assert http.get("/v1/exceptions", headers=ALICE).json() == []
    assert "review.recorded" in [e["action"] for e in http.get("/v1/audit-events", headers=ALICE).json()]


def test_follow_up_keeps_it_open(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    job_id = run_job(http, delivered)
    review(http, job_id, action="follow_up")
    assert len(http.get("/v1/exceptions", headers=ALICE).json()) == 1


def test_correction_sits_beside_the_original(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    job_id = run_job(http, delivered)
    review(http, job_id, corrected_quantity=118)
    saved = http.get(f"/v1/jobs/{job_id}/reviews", headers=ALICE).json()
    assert saved[0]["correction"] == {"total_quantity": 118} and saved[0]["reason"] == "Recounted on the dock."
    original = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()
    assert original["check"]["status"] == "Mismatch" and original["documents"][0]["fields"]["total_quantity"] == 120


def test_manual_review_case_can_be_reviewed(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    blocked(monkeypatch)
    assert review(http, run_job(http, delivered)).status_code == 201


def test_clerk_can_see_but_not_review(api, monkeypatch):
    http, make_session, _, delivered = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, "clerk")
    mismatch(monkeypatch)
    job_id = run_job(http, delivered)
    assert len(http.get("/v1/exceptions", headers=BOB).json()) == 1
    assert review(http, job_id, headers=BOB).status_code == 403


@pytest.mark.parametrize("body", [{"reason": ""}, {"action": "delete"}, {"corrected_quantity": -1}])
def test_bad_reviews_are_refused(api, monkeypatch, body):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    assert review(http, run_job(http, delivered), **body).status_code == 422


def test_another_tenant_sees_nothing(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    mismatch(monkeypatch)
    job_id = run_job(http, delivered)
    start_org(http, BOB)
    assert http.get("/v1/exceptions", headers=BOB).json() == []
    assert review(http, job_id, headers=BOB).status_code == 404
    assert http.get(f"/v1/jobs/{job_id}/reviews", headers=BOB).status_code == 404
    assert http.get("/v1/analytics/summary", headers=BOB).json()["shipments"] == 0
    assert http.get("/v1/observability/summary", headers=BOB).json()["latest"] is None


def test_summaries_come_from_saved_jobs(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered, "MF-1")
    mismatch(monkeypatch)
    run_job(http, delivered, "MF-2")
    summary = http.get("/v1/analytics/summary", headers=ALICE).json()
    assert summary["shipments"] == 2 and summary["open_exceptions"] == 1
    assert summary["checks_by_status"] == {"Match": 1, "Mismatch": 1}
    assert summary["jobs_by_status"] == {"succeeded": 2}
    traces = http.get("/v1/observability/summary", headers=ALICE).json()
    assert traces["jobs_measured"] == 2 and traces["average_stage_ms"] == {"ocr": 1}
    assert traces["entities_by_type"] == {"PERSON": 4}
    assert traces["latest"]["timings_ms"] == {"ocr": 1} and traces["latest"]["check_status"] in ("Match", "Mismatch")


def test_summary_reports_latency_and_fallback_rate(api):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    summary = http.get("/v1/observability/summary", headers=ALICE).json()
    assert summary["average_latency_ms"] == 1 and summary["vision_fallback_rate"] == 0


def test_processing_history_can_be_searched(api, monkeypatch):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered, "MF-100")
    mismatch(monkeypatch)
    run_job(http, delivered, "XY_200")
    everything = http.get("/v1/jobs", headers=ALICE).json()
    assert {row["reference"] for row in everything} == {"MF-100", "XY_200"}
    assert {row["check_status"] for row in everything} == {"Match", "Mismatch"}
    assert [r["reference"] for r in http.get("/v1/jobs", params={"q": "mf-1"}, headers=ALICE).json()] == ["MF-100"]
    assert http.get("/v1/jobs", params={"status": "failed"}, headers=ALICE).json() == []


def test_processing_history_stays_in_the_organization(api):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    http.post("/v1/organizations", headers=BOB, json={"name": "Other"})
    assert http.get("/v1/jobs", headers=BOB).json() == []


def test_shipments_can_be_searched_and_filtered(api):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered, "MF-100")
    new_shipment(http, reference="XY_200")
    found = http.get("/v1/shipments", params={"q": "y_2"}, headers=ALICE).json()
    assert [row["reference"] for row in found] == ["XY_200"]
    assert http.get("/v1/shipments", params={"q": "%"}, headers=ALICE).json() == []
    checked = http.get("/v1/shipments", params={"status": "checked"}, headers=ALICE).json()
    assert [row["reference"] for row in checked] == ["MF-100"]


def test_trace_summary_holds_no_document_values(api):
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    text = str(http.get("/v1/observability/summary", headers=ALICE).json())
    assert "Kestrel" not in text and "MF-1" not in text


def test_clerk_cannot_read_the_trace_summary(api):
    http, make_session, _, _ = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, "clerk")
    assert http.get("/v1/observability/summary", headers=BOB).status_code == 403
