"""Usage metering and plan limits (#44)."""
import uuid
from datetime import datetime, timezone

import pytest

from app.api import usage as usage_api
from app.core import plans
from app.db import models
from app.domains.base import PipelineInfo
from app.pipeline import runner
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, api, fake_response, new_shipment, start_org, upload  # noqa: F401
from test_reviews import BOB, add_member, run_job


def with_tokens(monkeypatch, calls=2, prompt=300, completion=40):
    def run(files):
        response = fake_response(files=files)
        response.pipeline = PipelineInfo(prompt_version="v-test", model_calls=calls, prompt_tokens=prompt,
                                         completion_tokens=completion)
        return response
    monkeypatch.setattr(runner, "run", run)


def test_a_finished_job_is_metered(api, monkeypatch):  # noqa: F811
    http, _, _, delivered = api
    start_org(http)
    with_tokens(monkeypatch)
    run_job(http, delivered)
    body = http.get("/v1/usage", headers=ALICE).json()
    assert body["documents"] == 1 and body["model_calls"] == 2
    assert body["input_tokens"] == 300 and body["output_tokens"] == 40
    assert body["plan"] == "trial" and body["limit"] == plans.PLANS["trial"]
    assert body["remaining"] == plans.PLANS["trial"] - 1


def test_failed_and_manual_review_jobs_are_metered_too(api, monkeypatch):  # noqa: F811
    from test_reviews import blocked
    http, _, _, delivered = api
    start_org(http)
    blocked(monkeypatch)
    run_job(http, delivered)
    assert http.get("/v1/usage", headers=ALICE).json()["documents"] == 1


def test_the_queue_delivering_twice_meters_once(api, monkeypatch):  # noqa: F811
    from app.worker import jobs
    http, _, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    jobs.process(*delivered[-1])
    assert http.get("/v1/usage", headers=ALICE).json()["documents"] == 1


def test_limit_stops_a_new_check_with_402(api, monkeypatch):  # noqa: F811
    http, _, _, delivered = api
    start_org(http)
    monkeypatch.setitem(plans.PLANS, "trial", 1)
    run_job(http, delivered)
    shipment = new_shipment(http, reference="MF-2")
    upload(http, shipment)
    refused = http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE)
    assert refused.status_code == 402 and "limit" in refused.json()["error"]


def test_a_job_that_would_pass_the_limit_is_refused(api, monkeypatch):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    monkeypatch.setitem(plans.PLANS, "trial", 1)
    shipment = new_shipment(http)
    upload(http, shipment)
    upload(http, shipment)
    assert http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).status_code == 402


def test_no_limit_plan_never_refuses(api, monkeypatch):  # noqa: F811
    http, make_session, _, delivered = api
    org = start_org(http)
    with make_session() as session:
        session.get(models.Organization, uuid.UUID(org)).plan = "enterprise"
        session.commit()
    monkeypatch.setitem(plans.PLANS, "trial", 0)
    run_job(http, delivered)
    body = http.get("/v1/usage", headers=ALICE).json()
    assert body["limit"] is None and body["remaining"] is None and body["documents"] == 1


def test_unknown_plan_gets_the_trial_limit():
    assert plans.monthly_limit("typo") == plans.PLANS["trial"]
    assert plans.monthly_limit(None) == plans.PLANS["trial"]


def test_last_months_use_does_not_count(api, monkeypatch):  # noqa: F811
    http, make_session, _, delivered = api
    org = start_org(http)
    run_job(http, delivered)
    with make_session() as session:
        for record in session.query(models.UsageRecord).all():
            record.created_at = datetime(2020, 1, 15, tzinfo=timezone.utc)
        session.commit()
    assert http.get("/v1/usage", headers=ALICE).json()["documents"] == 0
    assert usage_api.month_start(datetime(2026, 11, 7, 15, tzinfo=timezone.utc)) == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert org


def test_counts_survive_when_retention_deletes_the_job(api, monkeypatch):  # noqa: F811
    http, make_session, _, delivered = api
    start_org(http)
    job_id = run_job(http, delivered)
    with make_session() as session:
        session.delete(session.get(models.ProcessingJob, uuid.UUID(job_id)))
        session.commit()
    assert http.get("/v1/usage", headers=ALICE).json()["documents"] == 1


@pytest.mark.parametrize("role,expected", [("clerk", 403), ("supervisor", 200)])
def test_supervisors_and_admins_see_usage(api, role, expected):  # noqa: F811
    http, make_session, _, _ = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, role)
    assert http.get("/v1/usage", headers=BOB).status_code == expected


def test_another_organizations_use_is_not_counted(api, monkeypatch):  # noqa: F811
    http, make_session, _, delivered = api
    start_org(http)
    run_job(http, delivered)
    other = {"Authorization": f"Bearer {token(sub='user_cara', email='cara@example.com', exp=4_000_000_000)}"}
    http.post("/v1/organizations", json={"name": "Other"}, headers=other)
    assert http.get("/v1/usage", headers=other).json()["documents"] == 0
