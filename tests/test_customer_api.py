"""Customer API keys and signed webhooks."""
import importlib.util
import json
import pathlib
import uuid

import httpx
import pytest

from app.core import config, webhook_url
from app.db import models
from app.worker import jobs, queue, webhooks
from test_auth import client, clerk_settings  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, BOB, api, start_org  # noqa: F401
from test_reviews import add_member, mismatch  # noqa: F401

spec = importlib.util.spec_from_file_location("customer_example", pathlib.Path(__file__).parent.parent / "scripts/customer_example.py")
customer_example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(customer_example)

PDF = b"%PDF-1.4 synthetic"
PUBLIC = "https://hooks.example.com/meridian"


def new_key(http, headers=ALICE):
    return http.post("/v1/api-keys", headers=headers, json={"name": "Warehouse system"})


class Sent:
    def __init__(self, code=204):
        self.code, self.requests = code, []

    def __call__(self, url, content, headers, timeout, follow_redirects):
        assert follow_redirects is False
        self.requests.append((url, content, headers))
        return httpx.Response(self.code)


@pytest.fixture
def hooks(api, monkeypatch):  # noqa: F811
    http, make_session, store, delivered = api
    sent, queued = Sent(), []
    monkeypatch.setattr(webhooks, "new_session", make_session)
    monkeypatch.setattr(webhook_url, "acceptable", lambda url, resolve=True: True)
    monkeypatch.setattr(httpx, "post", sent)
    monkeypatch.setattr(queue, "enqueue_webhook", lambda org, delivery: queued.append((str(org), str(delivery))))
    return http, make_session, delivered, sent, queued


def submit(http, key, delivered):
    headers = {"X-API-Key": key}
    shipment = http.post("/v1/shipments", headers=headers, json={"reference": "MF-API"}).json()["id"]
    assert http.post(f"/v1/shipments/{shipment}/documents", headers=headers, files={"file": ("upload", PDF, "application/pdf")}).status_code == 201
    job = http.post(f"/v1/shipments/{shipment}/jobs", headers=headers).json()["id"]
    jobs.process(*delivered[-1])
    return job


def test_external_script_submits_and_receives_a_signed_result(hooks):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    key = new_key(http).json()["key"]
    secret = http.post("/v1/webhooks", headers=ALICE, json={"url": PUBLIC}).json()["secret"]
    job = submit(http, key, delivered)
    assert len(queued) == 1
    webhooks.deliver(*queued[0])
    url, body, headers = sent.requests[0]
    assert url == PUBLIC and customer_example.verify(secret, headers["X-Meridian-Signature"], body)
    assert not customer_example.verify("wrong-secret", headers["X-Meridian-Signature"], body)
    assert not customer_example.verify(secret, headers["X-Meridian-Signature"], body + b"x")
    event = json.loads(body)
    assert event["job_id"] == job and event["check_status"] == "Match" and event["reference"] == "MF-API"
    assert "Kestrel" not in body.decode()  # the event carries no extracted values
    assert http.get(f"/v1/jobs/{job}", headers={"X-API-Key": key}).json()["status"] == "succeeded"
    assert http.get("/v1/webhooks/deliveries", headers=ALICE).json()[0]["status"] == "delivered"


def test_old_signatures_are_refused(hooks):
    body = b"{}"
    header = webhooks.sign("s", 1000, body)
    assert customer_example.verify("s", header, body, now=1000)
    assert not customer_example.verify("s", header, body, now=1000 + 301)
    assert not customer_example.verify("s", "not-a-signature", body)


def test_failed_delivery_retries_then_stops_without_repeating_a_delivered_one(hooks, monkeypatch):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    key = new_key(http).json()["key"]
    http.post("/v1/webhooks", headers=ALICE, json={"url": PUBLIC})
    submit(http, key, delivered)
    sent.code = 500
    for _ in range(config.WEBHOOK_MAX_ATTEMPTS - 1):
        with pytest.raises(webhooks.TryAgain):
            webhooks.deliver(*queued[0])
    webhooks.deliver(*queued[0])
    row = http.get("/v1/webhooks/deliveries", headers=ALICE).json()[0]
    assert row["status"] == "failed" and row["attempts"] == config.WEBHOOK_MAX_ATTEMPTS and row["response_code"] == 500
    count = len(sent.requests)
    webhooks.deliver(*queued[0])
    assert len(sent.requests) == count


def test_a_job_delivered_twice_sends_one_event(hooks):
    http, _, delivered, _, queued = hooks
    start_org(http)
    key = new_key(http).json()["key"]
    http.post("/v1/webhooks", headers=ALICE, json={"url": PUBLIC})
    submit(http, key, delivered)
    jobs.process(*delivered[-1])
    assert len(queued) == 1


def test_only_a_hash_of_the_key_is_stored(api):  # noqa: F811
    http, make_session, _, _ = api
    start_org(http)
    created = new_key(http).json()
    with make_session() as session:
        row = session.get(models.ApiKey, uuid.UUID(created["id"]))
        assert created["key"] not in (row.key_hash, row.prefix) and created["key"].startswith(row.prefix)
    assert "key" not in http.get("/v1/api-keys", headers=ALICE).json()[0]


def test_rotation_and_revocation_stop_the_old_key(api):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    created = new_key(http).json()
    first = {"X-API-Key": created["key"]}
    assert http.get("/v1/shipments", headers=first).status_code == 200
    rotated = http.post(f"/v1/api-keys/{created['id']}/rotate", headers=ALICE).json()
    assert http.get("/v1/shipments", headers=first).status_code == 401
    second = {"X-API-Key": rotated["key"]}
    assert http.get("/v1/shipments", headers=second).status_code == 200
    assert http.delete(f"/v1/api-keys/{rotated['id']}", headers=ALICE).status_code == 204
    assert http.get("/v1/shipments", headers=second).status_code == 401


def test_a_key_only_acts_as_a_clerk_in_its_organization(api):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    headers = {"X-API-Key": new_key(http).json()["key"]}
    http.post("/v1/organizations", headers=BOB, json={"name": "Other"})
    other = http.post("/v1/shipments", headers=BOB, json={"reference": "SECRET"}).json()["id"]
    assert http.get(f"/v1/shipments/{other}", headers=headers).status_code == 404
    assert new_key(http, headers).status_code == 403
    assert http.get("/v1/audit-events", headers=headers).status_code == 403
    assert http.post("/v1/webhooks", headers=headers, json={"url": PUBLIC}).status_code == 403


def test_removing_a_member_stops_their_keys(api):  # noqa: F811
    http, make_session, _, _ = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, "admin")
    bob_id = http.get("/v1/me", headers=BOB).json()["id"]
    headers = {"X-API-Key": new_key(http, BOB).json()["key"]}
    assert http.get("/v1/shipments", headers=headers).status_code == 200
    assert http.delete(f"/v1/organization/members/{bob_id}", headers=ALICE).status_code == 204
    assert http.get("/v1/shipments", headers=headers).status_code == 401


def test_unknown_key_is_refused(api):  # noqa: F811
    http, _, _, _ = api
    assert http.get("/v1/shipments", headers={"X-API-Key": "mk_nope"}).status_code == 401


def test_key_rate_limit(api, monkeypatch):  # noqa: F811
    from app.api import deps
    from app.core.rate_limit import RateLimiter
    http, _, _, _ = api
    start_org(http)
    headers = {"X-API-Key": new_key(http).json()["key"]}
    monkeypatch.setattr(deps, "_key_limiter", RateLimiter(1))
    assert http.get("/v1/shipments", headers=headers).status_code == 200
    assert http.get("/v1/shipments", headers=headers).status_code == 429


@pytest.mark.parametrize("url", [
    "http://hooks.example.com/x", "https://localhost/x", "https://127.0.0.1/x", "https://169.254.169.254/latest/meta-data",
    "https://10.0.0.5/x", "https://[::1]/x", "https://[::ffff:127.0.0.1]/x", "https://user:pw@hooks.example.com/x", "ftp://hooks.example.com/x", "nonsense",
])
def test_unsafe_webhook_addresses_are_refused(api, url):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    assert http.post("/v1/webhooks", headers=ALICE, json={"url": url}).status_code == 422


def test_a_name_that_resolves_privately_is_refused_at_delivery(monkeypatch):
    monkeypatch.setattr(webhook_url.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    assert webhook_url.acceptable(PUBLIC, resolve=False)
    assert not webhook_url.acceptable(PUBLIC)


def test_only_admins_manage_keys_and_webhooks(api):  # noqa: F811
    http, make_session, _, _ = api
    org = start_org(http)
    add_member(http, make_session, org, BOB, "supervisor")
    assert new_key(http, BOB).status_code == 403
    assert http.get("/v1/webhooks", headers=BOB).status_code == 403


def test_key_actions_are_audited(api):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    created = new_key(http).json()
    http.delete(f"/v1/api-keys/{created['id']}", headers=ALICE)
    actions = [event["action"] for event in http.get("/v1/audit-events", headers=ALICE).json()]
    assert "api_key.created" in actions and "api_key.revoked" in actions
    assert created["key"] not in str(http.get("/v1/audit-events", headers=ALICE).json())
