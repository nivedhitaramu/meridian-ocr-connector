"""Tell a customer's endpoint that a job finished. Only IDs, statuses and code-written reasons are sent."""
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

from ..core import config, webhook_url
from ..db.models import ProcessingJob, Shipment, VerificationResult, WebhookDelivery, WebhookEndpoint
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
    """Add one row per active endpoint, in the job's own transaction, unless a redelivery already did."""
    endpoints = session.scalars(select(WebhookEndpoint).where(
        WebhookEndpoint.organization_id == job.organization_id, WebhookEndpoint.disabled_at.is_(None)))
    seen = set(session.scalars(select(WebhookDelivery.endpoint_id).where(WebhookDelivery.job_id == job.id)))
    rows = [WebhookDelivery(id=uuid.uuid4(), organization_id=job.organization_id, endpoint_id=endpoint.id, job_id=job.id,
                            status="pending", attempts=0) for endpoint in endpoints if endpoint.id not in seen]
    session.add_all(rows)
    return [row.id for row in rows]


def payload(session: Session, delivery: WebhookDelivery) -> bytes:
    job = session.get(ProcessingJob, delivery.job_id)
    shipment = session.get(Shipment, job.shipment_id)
    check = session.scalar(select(VerificationResult).where(VerificationResult.job_id == job.id))
    return json.dumps({
        "event": "job.finished", "delivery_id": str(delivery.id), "job_id": str(job.id), "shipment_id": str(shipment.id),
        "reference": shipment.reference, "job_status": job.job_status, "check_status": check.status if check else None,
        "reason": check.reason if check else None,
    }, sort_keys=True, separators=(",", ":")).encode()


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
            body = payload(session, delivery)
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
