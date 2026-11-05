"""Delete shipment records older than an organization chose to keep. Off unless an admin turns it on.

Audit events stay, so the history of who did what outlives the records themselves.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..db import audit
from ..db.models import (Document, ExtractionResult, IntakeItem, Organization, ProcessingJob, ReviewAction, Shipment,
                         VerificationResult, WebhookDelivery)
from ..db.session import new_session
from ..db.tenancy import set_scope
from ..ingestion.storage import store

log = logging.getLogger("meridian")
ACTIVE = ("queued", "running")


def _delete_shipments(session: Session, organization_id: uuid.UUID, shipment_ids: list[uuid.UUID]) -> None:
    jobs = list(session.scalars(select(ProcessingJob.id).where(ProcessingJob.shipment_id.in_(shipment_ids))))
    documents = list(session.execute(select(Document.id, Document.storage_key).where(Document.shipment_id.in_(shipment_ids))))
    session.execute(delete(WebhookDelivery).where(WebhookDelivery.job_id.in_(jobs)))
    session.execute(delete(ReviewAction).where(ReviewAction.job_id.in_(jobs)))
    session.execute(delete(VerificationResult).where(VerificationResult.job_id.in_(jobs)))
    session.execute(delete(ExtractionResult).where(ExtractionResult.document_id.in_([row[0] for row in documents])))
    session.execute(delete(Document).where(Document.shipment_id.in_(shipment_ids)))
    session.execute(delete(ProcessingJob).where(ProcessingJob.shipment_id.in_(shipment_ids)))
    session.execute(update(IntakeItem).where(IntakeItem.shipment_id.in_(shipment_ids)).values(shipment_id=None))
    session.execute(delete(Shipment).where(Shipment.id.in_(shipment_ids)))
    audit.record(session, organization_id, None, audit.RETENTION_APPLIED, f"shipments:{len(shipment_ids)}", None)
    session.commit()
    for _, key in documents:  # after the commit, so a failed delete can't lose files for records that remain
        if key:
            store().delete(key)


def apply(organization_id: uuid.UUID, days: int, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    with new_session() as session:
        set_scope(session, None, organization_id)
        old = set(session.scalars(select(Shipment.id).where(
            Shipment.organization_id == organization_id, Shipment.created_at < cutoff)))
        busy = set(session.scalars(select(ProcessingJob.shipment_id).where(
            ProcessingJob.organization_id == organization_id, ProcessingJob.job_status.in_(ACTIVE))))
        expired = sorted(old - busy)
        if expired:
            _delete_shipments(session, organization_id, expired)
        # Items keep only a reference and a status, but they follow the same limit.
        session.execute(delete(IntakeItem).where(
            IntakeItem.organization_id == organization_id, IntakeItem.created_at < cutoff, IntakeItem.storage_key.is_(None)))
        session.commit()
    return len(expired)


def apply_all() -> int:
    with new_session() as session:
        set_scope(session, None)
        settings = session.execute(select(Organization.id, Organization.retention_days).where(
            Organization.retention_days.is_not(None))).all()
    removed = sum(apply(organization_id, days) for organization_id, days in settings)
    log.info(json.dumps({"level": "info", "stage": "retention", "organizations": len(settings), "shipments_removed": removed}))
    return removed
