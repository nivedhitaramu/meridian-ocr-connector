"""Connectors (#41): verified goods receipts reach a warehouse system, and only verified ones."""
import importlib.util
import json
import pathlib
import socket

import httpx
import pytest

from app.core import config
from app.worker import webhooks
from test_auth import client, clerk_settings  # noqa: F401  (shared fixtures)
from test_customer_api import PUBLIC, hooks, new_key, submit  # noqa: F401
from test_jobs import ALICE, BOB, api, start_org  # noqa: F401
from test_reviews import add_member, blocked, mismatch, review

spec = importlib.util.spec_from_file_location("sandbox_wms", pathlib.Path(__file__).parent.parent / "scripts/sandbox_wms.py")
sandbox_wms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox_wms)
WMS = "https://wms.example.com/receipts"


def add_endpoints(http):
    event = http.post("/v1/webhooks", headers=ALICE, json={"url": PUBLIC}).json()
    wms = http.post("/v1/webhooks", headers=ALICE, json={"url": WMS, "format": "wms_receipt"}).json()
    return event, wms


def sent_to(sent, url):
    return [json.loads(body) for target, body, _ in sent.requests if target == url]


def deliver_all(queued):
    for item in list(queued):
        webhooks.deliver(*item)
    queued.clear()


def test_a_match_sends_a_verified_receipt_with_fields(hooks):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    _, wms = add_endpoints(http)
    assert wms["format"] == "wms_receipt"
    key = new_key(http).json()["key"]
    job = submit(http, key, delivered)
    deliver_all(queued)
    [receipt] = sent_to(sent, WMS)
    assert receipt["event"] == "goods_receipt.verified" and receipt["job_id"] == job
    assert receipt["verification"]["status"] == "Match" and receipt["verification"]["decided_by"] == "rules"
    assert receipt["documents"][0]["fields"]["shipper_name"] == "Kestrel Exports"
    assert len(sent_to(sent, PUBLIC)) == 1  # the plain event goes out as before


def test_a_mismatch_waits_until_a_person_resolves_it(hooks, monkeypatch):
    http, make_session, delivered, sent, queued = hooks
    org = start_org(http)
    add_endpoints(http)
    add_member(http, make_session, org, BOB, "supervisor")
    mismatch(monkeypatch)
    job = submit(http, new_key(http).json()["key"], delivered)
    deliver_all(queued)
    assert sent_to(sent, WMS) == []  # not verified yet
    assert review(http, job, BOB, reason="Counted by hand.", corrected_quantity=118).status_code == 201
    deliver_all(queued)
    [receipt] = sent_to(sent, WMS)
    assert receipt["verification"]["status"] == "Mismatch" and receipt["verification"]["decided_by"] == "review"
    assert receipt["verification"]["corrected_quantity"] == 118


def test_a_follow_up_is_not_a_verification(hooks, monkeypatch):
    http, make_session, delivered, sent, queued = hooks
    org = start_org(http)
    add_endpoints(http)
    add_member(http, make_session, org, BOB, "supervisor")
    mismatch(monkeypatch)
    job = submit(http, new_key(http).json()["key"], delivered)
    review(http, job, BOB, action="follow_up", reason="Asked the supplier.")
    deliver_all(queued)
    assert sent_to(sent, WMS) == []


def test_manual_review_sends_nothing_to_the_wms(hooks, monkeypatch):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    add_endpoints(http)
    blocked(monkeypatch)
    submit(http, new_key(http).json()["key"], delivered)
    deliver_all(queued)
    assert sent_to(sent, WMS) == [] and len(sent_to(sent, PUBLIC)) == 1


def test_a_receipt_is_sent_once(hooks):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    add_endpoints(http)
    submit(http, new_key(http).json()["key"], delivered)
    from app.worker import jobs
    jobs.process(*delivered[-1])  # the queue delivers the job again
    deliver_all(queued)
    assert len(sent_to(sent, WMS)) == 1


def test_unknown_format_is_refused(hooks):
    http, _, _, _, _ = hooks
    start_org(http)
    assert http.post("/v1/webhooks", headers=ALICE, json={"url": WMS, "format": "erp_magic"}).status_code == 422


def test_existing_endpoints_keep_the_event_format(hooks):
    http, _, _, _, _ = hooks
    start_org(http)
    http.post("/v1/webhooks", headers=ALICE, json={"url": PUBLIC})
    assert http.get("/v1/webhooks", headers=ALICE).json()[0]["format"] == "event"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_receipt_reaches_the_sandbox_wms_over_http(api, monkeypatch):  # noqa: F811
    """End to end with a real HTTP server standing in for the warehouse system."""
    http, make_session, _, delivered = api
    queued = []
    monkeypatch.setattr(webhooks, "new_session", make_session)
    monkeypatch.setattr(config, "WEBHOOK_ALLOW_PRIVATE", True)
    from app.worker import queue
    monkeypatch.setattr(queue, "enqueue_webhook", lambda org, delivery: queued.append((str(org), str(delivery))))
    start_org(http)
    port = _free_port()
    secret = http.post("/v1/webhooks", headers=ALICE,
                       json={"url": f"http://127.0.0.1:{port}/receipts", "format": "wms_receipt"}).json()["secret"]
    received = []
    server = sandbox_wms.serve(secret, port, received)
    try:
        job = submit(http, new_key(http).json()["key"], delivered)
        deliver_all(queued)
    finally:
        server.shutdown()
    assert [r["job_id"] for r in received] == [job]
    assert http.get("/v1/webhooks/deliveries", headers=ALICE).json()[0]["status"] == "delivered"


def test_sandbox_refuses_a_bad_signature():
    port = _free_port()
    server = sandbox_wms.serve("right", port, [])
    try:
        body = b'{"event":"goods_receipt.verified"}'
        bad = httpx.post(f"http://127.0.0.1:{port}/receipts", content=body,
                         headers={"X-Meridian-Signature": webhooks.sign("wrong", int(__import__("time").time()), body)})
        assert bad.status_code == 401
    finally:
        server.shutdown()


@pytest.mark.parametrize("fmt", ["event", "wms_receipt"])
def test_payloads_never_hold_masked_names_or_files(hooks, fmt):
    http, _, delivered, sent, queued = hooks
    start_org(http)
    http.post("/v1/webhooks", headers=ALICE, json={"url": WMS, "format": fmt})
    submit(http, new_key(http).json()["key"], delivered)
    deliver_all(queued)
    body = json.dumps(sent_to(sent, WMS))
    assert "storage_key" not in body and "%PDF" not in body
