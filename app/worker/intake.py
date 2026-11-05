"""Read a batch locally, then group it. No model is called, and OCR text is never saved or logged."""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import PipelineError
from ..db import audit
from ..db.models import Document, IntakeItem, ProcessingJob, Shipment
from ..db.session import new_session
from ..db.tenancy import set_scope
from ..domains.meridian import grouping
from ..ingestion import upload
from ..ingestion.storage import store
from ..pipeline import ocr, pii

log = logging.getLogger("meridian")


def read_document(data: bytes) -> grouping.Read:
    stored = upload.store(data)
    try:
        result = ocr.run_ocr(ocr.load_pages(stored.path, stored.kind))
    finally:
        stored.delete()
    read = grouping.read_text(result.text, poor_scan=result.needs_fallback())
    if read.reference and pii.residual_types(read.reference):
        return grouping.Read(read.document_type, None, "no_reference")  # personal data never becomes a reference
    return read


def known_shipments(session: Session, organization_id: uuid.UUID) -> dict[str, tuple[Shipment, bool]]:
    checked = set(session.scalars(select(ProcessingJob.shipment_id).where(ProcessingJob.organization_id == organization_id)))
    rows = session.scalars(select(Shipment).where(Shipment.organization_id == organization_id))
    return {grouping.normalize(row.reference): (row, row.id in checked) for row in rows}


def attach(session: Session, item: IntakeItem, shipment: Shipment) -> None:
    """Move the file into the shipment. The check still has to be started, so nothing completes on its own."""
    session.add(Document(organization_id=item.organization_id, shipment_id=shipment.id, storage_key=item.storage_key))
    item.storage_key = None
    item.shipment_id = shipment.id


def process_batch(organization_id: str, batch_id: str) -> None:
    organization, batch = uuid.UUID(organization_id), uuid.UUID(batch_id)
    with new_session() as session:
        set_scope(session, None, organization)
        items = list(session.scalars(select(IntakeItem).where(
            IntakeItem.organization_id == organization, IntakeItem.batch_id == batch, IntakeItem.status == "queued")
            .order_by(IntakeItem.created_at, IntakeItem.id)))
        if not items:
            return  # already done: the queue can deliver a batch twice
        reads: list[grouping.Read] = []
        for item in items:
            try:
                reads.append(read_document(store().get(item.storage_key)))
            except (OSError, PipelineError):
                reads.append(grouping.Read("unknown", None, "unreadable"))

        known = known_shipments(session, organization)
        decisions = grouping.decide(reads, {key: checked for key, (_, checked) in known.items()})
        for item, read, decision in zip(items, reads, decisions):
            item.document_type, item.reference, item.status, item.reason = read.document_type, read.reference, decision.status, decision.reason
            if decision.status != grouping.AUTO:
                continue
            key = grouping.normalize(read.reference)
            if key not in known:
                shipment = Shipment(id=uuid.uuid4(), organization_id=organization, reference=read.reference)
                session.add(shipment)
                session.flush()
                known[key] = (shipment, False)
            attach(session, item, known[key][0])
            audit.record(session, organization, None, audit.INTAKE_GROUPED, f"shipment:{known[key][0].id}", None)
        session.commit()
        log.info(json.dumps({"level": "info", "stage": "intake", "file_count": len(items),
                             "grouped": sum(d.status == grouping.AUTO for d in decisions)}))
