"""Payload formats for outgoing deliveries.

- `event`: says a job finished, with IDs, statuses and the code-written reason. Sent for every finished job.
- `wms_receipt`: a verified goods receipt for a warehouse system, with the extracted fields. Sent once per job,
  only when the result is verified: a Match from the rules, or an exception a person resolved.

Adding a target: write a function that takes a `Delivered` and returns a dict, and register it below with whether it
needs a verified result. Fields hold only what the website already shows; names the masking replaced stay as
placeholders, and documents themselves are never sent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Document, ExtractionResult, ProcessingJob, ReviewAction, Shipment, VerificationResult


@dataclass(frozen=True)
class Delivered:
    delivery_id: uuid.UUID
    job: ProcessingJob
    shipment: Shipment
    check: VerificationResult | None
    session: Session


@dataclass(frozen=True)
class Format:
    build: Callable[[Delivered], dict]
    verified_only: bool


def _event(d: Delivered) -> dict:
    return {
        "event": "job.finished", "delivery_id": str(d.delivery_id), "job_id": str(d.job.id), "shipment_id": str(d.shipment.id),
        "reference": d.shipment.reference, "job_status": d.job.job_status, "check_status": d.check.status if d.check else None,
        "reason": d.check.reason if d.check else None,
    }


def _wms_receipt(d: Delivered) -> dict:
    documents = d.session.execute(
        select(Document.document_type, ExtractionResult.fields, ExtractionResult.quantity_unit)
        .join(ExtractionResult, ExtractionResult.document_id == Document.id)
        .where(Document.shipment_id == d.shipment.id).order_by(Document.created_at, Document.id)).all()
    reviews = list(d.session.scalars(select(ReviewAction).where(ReviewAction.job_id == d.job.id)
                                     .order_by(ReviewAction.created_at, ReviewAction.id)))
    corrections = [r.correction for r in reviews if r.correction]
    return {
        "event": "goods_receipt.verified", "delivery_id": str(d.delivery_id), "job_id": str(d.job.id),
        "shipment_id": str(d.shipment.id), "reference": d.shipment.reference,
        "verification": {
            "status": d.check.status if d.check else None, "reason": d.check.reason if d.check else None,
            "decided_by": "review" if any(r.action == "resolve" for r in reviews) else "rules",
            "config_version": d.check.config_version if d.check else None,
            "corrected_quantity": corrections[-1].get("total_quantity") if corrections else None,
        },
        "documents": [{"document_type": kind, "fields": fields, "quantity_unit": unit} for kind, fields, unit in documents],
    }


FORMATS: dict[str, Format] = {
    "event": Format(_event, verified_only=False),
    "wms_receipt": Format(_wms_receipt, verified_only=True),
}


def is_verified(session: Session, job: ProcessingJob) -> bool:
    """A Match from the rules, or any exception a person has resolved."""
    check = session.scalar(select(VerificationResult.status).where(VerificationResult.job_id == job.id))
    resolved = session.scalar(select(ReviewAction.id).where(ReviewAction.job_id == job.id, ReviewAction.action == "resolve").limit(1))
    return resolved is not None or (job.job_status == "succeeded" and check == "Match")


def build(session: Session, delivery_id: uuid.UUID, job_id: uuid.UUID, format_name: str) -> dict:
    job = session.get(ProcessingJob, job_id)
    shipment = session.get(Shipment, job.shipment_id)
    check = session.scalar(select(VerificationResult).where(VerificationResult.job_id == job.id))
    return FORMATS.get(format_name, FORMATS["event"]).build(Delivered(delivery_id, job, shipment, check, session))
