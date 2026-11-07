"""Deliver results to customers' endpoints. Each endpoint's format, in app/connectors, decides what is sent and when."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors import formats
from ..core import config, webhook_url
from ..db.models import ProcessingJob, WebhookDelivery, WebhookEndpoint
from ..db.session import new_session
from ..db.tenancy import set_scope

log = logging.getLogger("meridian")
TIMEOUT_SECONDS = 10


class TryAgain(Exception):
    """The endpoint didn't accept this delivery yet. The queue tries again later."""


def sign(secret: str, timestamp: int, body: bytes) -> str:
    message = str(timestamp).encode() + b"." + body
    return "t=" + str(timestamp) + ",v1=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def create_deliveries(session: Session, job: ProcessingJob) -> list[uuid.UUID]:
    """Add one row per active endpoint that wants this job now, in the caller's transaction, unless one exists.

    Called when a job finishes and again when a person resolves it, so a verified-only format is sent once,
    at whichever point the result became verified.
    """
    endpoints = session.scalars(select(WebhookEndpoint).where(
        WebhookEndpoint.organization_id == job.organization_id, WebhookEndpoint.disabled_at.is_(None)))
    seen = set(session.scalars(select(WebhookDelivery.endpoint_id).where(WebhookDelivery.job_id == job.id)))
    verified = None
    rows = []
    for endpoint in endpoints:
        if endpoint.id in seen:
            continue
        if formats.FORMATS.get(endpoint.format, formats.FORMATS["event"]).verified_only:
            verified = formats.is_verified(session, job) if verified is None else verified
            if not verified:
                continue
        rows.append(WebhookDelivery(id=uuid.uuid4(), organization_id=job.organization_id, endpoint_id=endpoint.id,
                                    job_id=job.id, status="pending", attempts=0))
    session.add_all(rows)
    return [row.id for row in rows]


def payload(session: Session, delivery: WebhookDelivery, format_name: str = "event") -> bytes:
    body = formats.build(session, delivery.id, delivery.job_id, format_name)
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _settle(delivery: WebhookDelivery, status: str) -> None:
    delivery.status = status
    delivery.finished_at = datetime.now(timezone.utc)


def deliver(organization_id: str, delivery_id: str) -> None:
    organization, key = uuid.UUID(organization_id), uuid.UUID(delivery_id)
    with new_session() as session:
        set_scope(session, None, organization)
        delivery = session.get(WebhookDelivery, key)
        if delivery is None or delivery.status != "pending":
            return
        endpoint = session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint.disabled_at is not None:
            _settle(delivery, "cancelled")
            session.commit()
            return
        delivery.attempts += 1
        accepted, code = False, None
        if webhook_url.acceptable(endpoint.url):
            body = payload(session, delivery, endpoint.format)
            headers = {"Content-Type": "application/json", "X-Meridian-Delivery": str(delivery.id),
                       "X-Meridian-Signature": sign(endpoint.secret, int(time.time()), body)}
            try:
                # Redirects stay off, so an accepted address can't send the request somewhere private.
                response = httpx.post(endpoint.url, content=body, headers=headers, timeout=TIMEOUT_SECONDS, follow_redirects=False)
                code = response.status_code
                accepted = response.is_success
            except httpx.HTTPError:
                pass
        delivery.response_code = code
        if accepted:
            _settle(delivery, "delivered")
            session.commit()
            return
        retry = delivery.attempts < config.WEBHOOK_MAX_ATTEMPTS
        if not retry:
            _settle(delivery, "failed")
        session.commit()
        log.info(json.dumps({"level": "info", "stage": "webhook", "outcome": "retry" if retry else "failed", "response_code": code}))
        if retry:
            raise TryAgain
