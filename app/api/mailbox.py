"""Mailbox intake (#37): an emailed packet becomes a checked shipment with no manual upload.

Each organization gets an address like inbox+<token>@<INBOUND_EMAIL_DOMAIN>. An email provider receives the mail
and posts the raw message to POST /v1/inbound/email, signed with INBOUND_EMAIL_SECRET. The sender must be on the
organization's allowed list, attachments are checked by their bytes like any upload, and each accepted email
starts one job. Without a secret and domain configured, the route refuses everything.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core import config
from ..core.errors import PipelineError
from ..db import audit
from ..db.models import Document, Mailbox, ProcessingJob, Shipment
from ..db.session import get_db
from ..db.tenancy import set_scope
from ..ingestion import eml
from ..ingestion.storage import new_key, store
from ..ingestion.upload import sniff_kind
from ..worker import queue
from .deps import Member, NotFound, request_id_for, require_role
from .usage import over_limit

router = APIRouter(prefix="/v1")
log = logging.getLogger("meridian")

MAX_MESSAGE_BYTES = 25 * 1024 * 1024
MAX_AGE_SECONDS = 300
_TOKEN = re.compile(r"^inbox\+([a-f0-9]{24})@", re.IGNORECASE)
_ENTRY = re.compile(r"^(?:[^@\s]+@)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$")


class Senders(BaseModel):
    allowed_senders: list[str] = Field(max_length=50)

    @field_validator("allowed_senders")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        """An entry is a full address, or a domain that covers its subdomains. Entries are kept in lower case."""
        cleaned = sorted({value.strip().lower().removeprefix("@") for value in values if value.strip()})
        for value in cleaned:
            if len(value) > 254 or not _ENTRY.match(value):
                raise ValueError("Each entry must be an email address or a domain such as example.com.")
        return cleaned


def _json(mailbox: Mailbox | None) -> dict:
    if mailbox is None or mailbox.disabled_at is not None:
        return {"address": None, "allowed_senders": [], "receiving": False}
    domain = config.INBOUND_EMAIL_DOMAIN
    return {"address": f"inbox+{mailbox.token}@{domain}" if domain else None,
            "allowed_senders": mailbox.allowed_senders or [],
            "receiving": bool(config.INBOUND_EMAIL_SECRET and domain)}


def _mailbox(session: Session, organization_id: uuid.UUID) -> Mailbox | None:
    return session.scalar(select(Mailbox).where(Mailbox.organization_id == organization_id))


@router.get("/mailbox")
def get_mailbox(member: Member = Depends(require_role("admin")), session: Session = Depends(get_db)):
    return _json(_mailbox(session, member.organization_id))


@router.put("/mailbox")
def set_mailbox(request: Request, body: Senders, member: Member = Depends(require_role("admin")),
                session: Session = Depends(get_db)):
    """Creates the address on first use. Only listed senders, or senders at a listed domain, are accepted."""
    mailbox = _mailbox(session, member.organization_id)
    if mailbox is None:
        mailbox = Mailbox(organization_id=member.organization_id, token=secrets.token_hex(12))
        session.add(mailbox)
    mailbox.allowed_senders, mailbox.disabled_at = body.allowed_senders, None
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.MAILBOX_CHANGED, f"mailbox:{mailbox.id}",
                 request_id_for(request))
    session.commit()
    return _json(mailbox)


@router.post("/mailbox/rotate")
def rotate_mailbox(request: Request, member: Member = Depends(require_role("admin")), session: Session = Depends(get_db)):
    """A new address. The old one stops working at once."""
    mailbox = _mailbox(session, member.organization_id)
    if mailbox is None:
        raise NotFound
    mailbox.token = secrets.token_hex(12)
    audit.record(session, member.organization_id, member.user_id, audit.MAILBOX_CHANGED, f"mailbox:{mailbox.id}",
                 request_id_for(request))
    session.commit()
    return _json(mailbox)


def signed(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    """The same scheme as our outgoing webhooks, so an old captured request can't be replayed."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((time.time() if now is None else now) - timestamp) > MAX_AGE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def sender_allowed(sender: str, allowed: list[str]) -> bool:
    sender = sender.lower()
    domain = sender.rsplit("@", 1)[-1]
    return "@" in sender and any(
        sender == entry or ("@" not in entry and (domain == entry or domain.endswith("." + entry))) for entry in allowed)


def _ignored(reason: str) -> JSONResponse:
    """Rejected mail gets a 200, so the provider doesn't keep retrying. Logs get the reason, never an address."""
    log.info(json.dumps({"level": "info", "stage": "mailbox", "outcome": "ignored", "error_class": reason}))
    return JSONResponse(status_code=200, content={"accepted": False, "reason": reason})


def _find_mailbox(session: Session, token: str) -> Mailbox | None:
    set_scope(session, None)
    if session.connection().dialect.name == "postgresql":
        session.execute(text("SELECT set_config('app.mailbox_token', :token, true)"), {"token": token})
    return session.scalar(select(Mailbox).where(Mailbox.token == token, Mailbox.disabled_at.is_(None)))


@router.post("/inbound/email", status_code=202)
async def inbound_email(request: Request, session: Session = Depends(get_db)):
    secret, domain = config.INBOUND_EMAIL_SECRET, config.INBOUND_EMAIL_DOMAIN.lower()
    if not secret or not domain:
        return JSONResponse(status_code=503, content={"error": "Mailbox intake isn't set up."})
    body = await request.body()
    if len(body) > MAX_MESSAGE_BYTES:
        return JSONResponse(status_code=413, content={"error": "Message too large."})
    if not signed(secret, request.headers.get("X-Meridian-Inbound-Signature", ""), body):
        return JSONResponse(status_code=401, content={"error": "Not authorized."})

    message = BytesParser(policy=policy.default).parsebytes(body)
    recipients = [address for _, address in getaddresses(
        [str(value) for header in ("Delivered-To", "To", "Cc") for value in message.get_all(header, [])])]
    tokens = {match.group(1).lower() for address in recipients
              if address.lower().endswith("@" + domain) and (match := _TOKEN.match(address))}
    if len(tokens) != 1:
        return _ignored("unknown_mailbox")
    mailbox = _find_mailbox(session, tokens.pop())
    if mailbox is None:
        return _ignored("unknown_mailbox")
    organization_id, allowed = mailbox.organization_id, list(mailbox.allowed_senders or [])
    senders = [address for _, address in getaddresses([str(value) for value in message.get_all("From", [])])]
    if len(senders) != 1 or not sender_allowed(senders[0], allowed):
        return _ignored("unknown_sender")
    try:
        files = eml.attachments(body)
    except PipelineError as err:
        return _ignored(err.error_class)
    files = [data for data in files if len(data) <= config.MAX_UPLOAD_BYTES]
    if not files:
        return _ignored("eml_no_attachments")

    set_scope(session, None, organization_id)
    if over_limit(session, organization_id, len(files)):
        return _ignored("plan_limit")
    reference = f"EMAIL-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"
    shipment = Shipment(id=uuid.uuid4(), organization_id=organization_id, reference=reference, status="processing")
    session.add(shipment)
    session.flush()
    for data in files:
        key = new_key(organization_id, sniff_kind(data))  # attachment names are never read or stored
        store().put(key, data)
        session.add(Document(organization_id=organization_id, shipment_id=shipment.id, storage_key=key))
    job = ProcessingJob(organization_id=organization_id, shipment_id=shipment.id, job_status="queued", attempts=0)
    session.add(job)
    session.flush()
    audit.record(session, organization_id, None, audit.MAILBOX_RECEIVED, f"job:{job.id}", request_id_for(request))
    session.commit()
    job_id, shipment_id = job.id, shipment.id
    try:
        queue.enqueue(organization_id, job_id)
    except Exception:
        job.job_status, job.error_class = "failed", "queue_unavailable"
        session.commit()
        return JSONResponse(status_code=503, content={"error": "Try again later."})  # the provider retries
    log.info(json.dumps({"level": "info", "stage": "mailbox", "outcome": "accepted", "file_count": len(files)}))
    return {"accepted": True, "job_id": str(job_id), "shipment_id": str(shipment_id), "reference": reference}
