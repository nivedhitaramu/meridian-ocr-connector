"""Mailbox intake (#37): an emailed packet from an allowed sender becomes a job, and nothing else gets in."""
import time
from email.message import EmailMessage
from pathlib import Path

import pytest

from app.api import mailbox as mailbox_api
from app.core import config, plans
from app.db import models
from app.ingestion import eml
from app.worker import jobs
from scripts.send_inbound_email import rewrite, sign
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, api, start_org  # noqa: F401
from test_reviews import BOB, add_member

SECRET, DOMAIN = "test-inbound-secret", "in.example.test"
PACKET = Path(__file__).resolve().parent.parent / "samples" / "packet_S02_match.eml"


@pytest.fixture
def inbound(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "INBOUND_EMAIL_SECRET", SECRET)
    monkeypatch.setattr(config, "INBOUND_EMAIL_DOMAIN", DOMAIN)
    store = api[2]
    monkeypatch.setattr(mailbox_api, "store", lambda: store)
    return api


def make_mailbox(http, senders=("orders@kestrel.example",), headers=ALICE):
    return http.put("/v1/mailbox", json={"allowed_senders": list(senders)}, headers=headers).json()


def post(http, body, signature=None):
    return http.post("/v1/inbound/email", content=body, headers={
        "Content-Type": "message/rfc822", "X-Meridian-Inbound-Signature": signature or sign(SECRET, body)})


def packet(to, sender="orders@kestrel.example"):
    return rewrite(PACKET.read_bytes(), to, sender)


def test_an_emailed_packet_is_checked_with_no_upload(inbound):
    http, make_session, _, delivered = inbound
    start_org(http)
    address = make_mailbox(http)["address"]
    assert address.startswith("inbox+") and address.endswith("@" + DOMAIN)
    accepted = post(http, packet(address))
    assert accepted.status_code == 202 and accepted.json()["accepted"] is True
    assert accepted.json()["reference"].startswith("EMAIL-")
    jobs.process(*delivered[-1])
    job = http.get(f"/v1/jobs/{accepted.json()['job_id']}", headers=ALICE).json()
    assert job["status"] == "succeeded" and len(job["documents"]) == len(eml.attachments(PACKET.read_bytes()))
    actions = [e["action"] for e in http.get("/v1/audit-events", headers=ALICE).json()]
    assert "mailbox.received" in actions


@pytest.mark.parametrize("sender,expected", [
    ("orders@kestrel.example", True), ("ORDERS@Kestrel.Example", True), ("someone@kestrel.example", False),
    ("orders@kestrel.example.evil", False), ("x@sub.trusted.example", True), ("x@trusted.example", True),
    ("x@nottrusted.example", False), ("x@trusted.example.evil", False),
])
def test_sender_rules(sender, expected):
    assert mailbox_api.sender_allowed(sender, ["orders@kestrel.example", "trusted.example"]) is expected


def test_unknown_sender_is_ignored_and_nothing_is_created(inbound):
    http, make_session, _, delivered = inbound
    start_org(http)
    address = make_mailbox(http)["address"]
    response = post(http, packet(address, sender="stranger@elsewhere.example"))
    assert response.json() == {"accepted": False, "reason": "unknown_sender"}
    assert delivered == []
    with make_session() as session:
        assert session.query(models.Shipment).count() == 0


@pytest.mark.parametrize("signature", ["", "t=1,v1=abc", f"t={int(time.time())},v1=" + "0" * 64])
def test_unsigned_or_badly_signed_mail_is_refused(inbound, signature):
    http, _, _, delivered = inbound
    start_org(http)
    response = post(http, packet(make_mailbox(http)["address"]), signature=signature or "missing")
    assert response.status_code == 401 and delivered == []


def test_an_old_signed_request_cant_be_replayed(inbound):
    http, _, _, _ = inbound
    start_org(http)
    body = packet(make_mailbox(http)["address"])
    assert post(http, body, signature=sign(SECRET, body, int(time.time()) - 3600)).status_code == 401


def test_route_is_off_without_a_secret(inbound, monkeypatch):
    http, _, _, _ = inbound
    monkeypatch.setattr(config, "INBOUND_EMAIL_SECRET", "")
    assert post(http, b"anything", signature="t=1,v1=x").status_code == 503


def test_unknown_address_is_ignored(inbound):
    http, _, _, delivered = inbound
    start_org(http)
    make_mailbox(http)
    response = post(http, packet(f"inbox+{'a' * 24}@{DOMAIN}"))
    assert response.json()["reason"] == "unknown_mailbox" and delivered == []


def test_address_at_another_domain_is_ignored(inbound):
    http, _, _, _ = inbound
    start_org(http)
    token_part = make_mailbox(http)["address"].split("@")[0]
    assert post(http, packet(f"{token_part}@evil.example")).json()["reason"] == "unknown_mailbox"


def test_replacing_the_address_stops_the_old_one(inbound):
    http, _, _, _ = inbound
    start_org(http)
    old = make_mailbox(http)["address"]
    new = http.post("/v1/mailbox/rotate", headers=ALICE).json()["address"]
    assert new != old
    assert post(http, packet(old)).json()["reason"] == "unknown_mailbox"
    assert post(http, packet(new)).json()["accepted"] is True


def test_mail_without_usable_attachments_is_ignored(inbound):
    http, _, _, delivered = inbound
    start_org(http)
    address = make_mailbox(http)["address"]
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "orders@kestrel.example", address, "Docs"
    message.set_content("See attached.")
    message.add_attachment(b"not a document", maintype="text", subtype="plain", filename="invoice.pdf")
    assert post(http, message.as_bytes()).json()["reason"] == "eml_no_attachments"
    assert delivered == []


def test_plan_limit_applies_to_email_too(inbound, monkeypatch):
    http, _, _, delivered = inbound
    start_org(http)
    monkeypatch.setitem(plans.PLANS, "trial", 1)
    assert post(http, packet(make_mailbox(http)["address"])).json()["reason"] == "plan_limit"
    assert delivered == []


def test_one_organizations_mail_lands_only_there(inbound):
    http, _, _, _ = inbound
    start_org(http)
    other = {"Authorization": f"Bearer {token(sub='user_cara', email='cara@example.com', exp=4_000_000_000)}"}
    http.post("/v1/organizations", json={"name": "Other"}, headers=other)
    theirs = make_mailbox(http, headers=other)["address"]
    make_mailbox(http)
    assert post(http, packet(theirs)).json()["accepted"] is True
    assert http.get("/v1/shipments", headers=ALICE).json() == []
    assert len(http.get("/v1/shipments", headers=other).json()) == 1


@pytest.mark.parametrize("senders", [["not an address"], ["@"], ["x@"], [""] * 0 + ["a" * 300 + ".com"]])
def test_bad_sender_entries_are_refused(inbound, senders):
    http, _, _, _ = inbound
    start_org(http)
    assert http.put("/v1/mailbox", json={"allowed_senders": senders}, headers=ALICE).status_code == 422


def test_entries_are_normalized():
    assert mailbox_api.Senders(allowed_senders=[" Orders@Kestrel.Example ", "@Trusted.Example", "trusted.example"]
                               ).allowed_senders == ["orders@kestrel.example", "trusted.example"]


@pytest.mark.parametrize("role", ["clerk", "supervisor"])
def test_only_admins_manage_the_mailbox(inbound, role):
    http, make_session, _, _ = inbound
    org = start_org(http)
    add_member(http, make_session, org, BOB, role)
    assert http.get("/v1/mailbox", headers=BOB).status_code == 403
    assert http.put("/v1/mailbox", json={"allowed_senders": ["a@b.example"]}, headers=BOB).status_code == 403
    assert http.post("/v1/mailbox/rotate", headers=BOB).status_code == 403


def test_logs_and_events_hold_no_addresses(inbound, caplog):
    http, _, _, _ = inbound
    start_org(http)
    address = make_mailbox(http)["address"]
    with caplog.at_level("INFO"):
        post(http, packet(address))
        post(http, packet(address, sender="stranger@elsewhere.example"))
    events = str(http.get("/v1/audit-events", headers=ALICE).json())
    for secret in ("kestrel.example", "elsewhere.example", address.split("@")[0]):
        assert secret not in caplog.text and secret not in events
