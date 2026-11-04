"""Shipments, their documents, and background jobs. Every route is limited to the caller's organization."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import config
from ..core.errors import CLIENT_MESSAGE
from ..db import audit
from ..db.models import Document, ExtractionResult, ProcessingJob, Shipment, VerificationResult
from ..db.session import get_db
from ..ingestion.storage import new_key, store
from ..ingestion.upload import sniff_kind
from ..worker import queue
from .deps import Member, NotFound, current_member, request_id_for

router = APIRouter(prefix="/v1")


class NewShipment(BaseModel):
    reference: str = Field(min_length=1, max_length=100)


def _shipment(session: Session, member: Member, shipment_id: uuid.UUID) -> Shipment:
    shipment = session.scalar(select(Shipment).where(
        Shipment.id == shipment_id, Shipment.organization_id == member.organization_id))
    if shipment is None:
        raise NotFound
    return shipment


def _shipment_json(shipment: Shipment) -> dict:
    return {"id": str(shipment.id), "reference": shipment.reference, "status": shipment.status,
            "created_at": shipment.created_at.isoformat() if shipment.created_at else None}


@router.post("/shipments", status_code=201)
def create_shipment(body: NewShipment, member: Member = Depends(current_member), session: Session = Depends(get_db)):
    shipment = Shipment(organization_id=member.organization_id, reference=body.reference.strip())
    session.add(shipment)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return JSONResponse(status_code=409, content={"error": "A shipment with this reference already exists."})
    return _shipment_json(shipment)


@router.get("/shipments")
def list_shipments(limit: int = Query(50, ge=1, le=200), member: Member = Depends(current_member),
                   session: Session = Depends(get_db)):
    rows = session.scalars(select(Shipment).where(Shipment.organization_id == member.organization_id)
                           .order_by(Shipment.created_at.desc(), Shipment.id).limit(limit))
    return [_shipment_json(s) for s in rows]


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: uuid.UUID, member: Member = Depends(current_member), session: Session = Depends(get_db)):
    shipment = _shipment(session, member, shipment_id)
    documents = session.scalars(select(Document).where(Document.shipment_id == shipment.id)
                                .order_by(Document.created_at, Document.id))
    jobs = session.scalars(select(ProcessingJob).where(ProcessingJob.shipment_id == shipment.id)
                           .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id))
    return {**_shipment_json(shipment),
            "documents": [{"id": str(d.id), "document_type": d.document_type, "processing_status": d.processing_status,
                           "page_count": d.page_count} for d in documents],
            "jobs": [{"id": str(j.id), "status": j.job_status} for j in jobs]}


@router.post("/shipments/{shipment_id}/documents", status_code=201)
async def add_document(request: Request, shipment_id: uuid.UUID, file: UploadFile = File(...),
                       member: Member = Depends(current_member), session: Session = Depends(get_db)):
    shipment = _shipment(session, member, shipment_id)
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": CLIENT_MESSAGE})
    kind = sniff_kind(data)
    if kind is None:
        return JSONResponse(status_code=415, content={"error": CLIENT_MESSAGE})
    key = new_key(member.organization_id, kind)  # the uploaded filename is never read or stored
    store().put(key, data)
    document = Document(organization_id=member.organization_id, shipment_id=shipment.id, storage_key=key)
    session.add(document)
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.DOCUMENT_UPLOADED,
                 f"document:{document.id}", request_id_for(request))
    try:
        session.commit()
    except Exception:
        store().delete(key)
        raise
    return {"id": str(document.id), "processing_status": document.processing_status}


def _accepted(job: ProcessingJob) -> JSONResponse:
    return JSONResponse(status_code=202, content={"id": str(job.id), "status": job.job_status})


@router.post("/shipments/{shipment_id}/jobs", status_code=202)
def start_job(shipment_id: uuid.UUID, idempotency_key: str | None = Header(default=None, max_length=100),
              member: Member = Depends(current_member), session: Session = Depends(get_db)):
    shipment = _shipment(session, member, shipment_id)
    if idempotency_key:
        existing = session.scalar(select(ProcessingJob).where(
            ProcessingJob.organization_id == member.organization_id, ProcessingJob.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.shipment_id != shipment.id:
                return JSONResponse(status_code=409, content={"error": "This key was used for another shipment."})
            return _accepted(existing)
    waiting = session.scalar(select(Document.id).where(
        Document.shipment_id == shipment.id, Document.storage_key.is_not(None)).limit(1))
    if waiting is None:
        return JSONResponse(status_code=409, content={"error": "Upload a document first."})
    job = ProcessingJob(organization_id=member.organization_id, shipment_id=shipment.id,
                        idempotency_key=idempotency_key, job_status="queued", attempts=0)
    session.add(job)
    shipment.status = "processing"
    session.commit()
    try:
        queue.enqueue(member.organization_id, job.id)
    except Exception:  # the broker is down. Saying so beats a job that waits forever.
        job.job_status = "failed"
        job.error_class = "queue_unavailable"
        session.commit()
        return JSONResponse(status_code=503, content={"error": "We can't start this check right now. Try again soon."})
    return _accepted(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, member: Member = Depends(current_member), session: Session = Depends(get_db)):
    job = session.scalar(select(ProcessingJob).where(
        ProcessingJob.id == job_id, ProcessingJob.organization_id == member.organization_id))
    if job is None:
        raise NotFound
    check = session.scalar(select(VerificationResult).where(VerificationResult.job_id == job.id))
    documents = []
    if check is not None:
        rows = session.execute(
            select(Document, ExtractionResult).join(ExtractionResult, ExtractionResult.document_id == Document.id)
            .where(Document.shipment_id == job.shipment_id, ExtractionResult.created_at <= check.created_at)
            .order_by(ExtractionResult.created_at.desc(), Document.created_at, Document.id)
        ).all()
        seen: set[uuid.UUID] = set()
        for document, extraction in rows:  # newest result per document, at the time of this job
            if document.id not in seen:
                seen.add(document.id)
                documents.append({"id": str(document.id), "document_type": document.document_type,
                                  "fields": extraction.fields, "quantity_unit": extraction.quantity_unit})
    return {
        "id": str(job.id), "shipment_id": str(job.shipment_id), "status": job.job_status,
        "attempts": job.attempts, "error_class": job.error_class,
        "timings_ms": job.timings_ms, "entity_counts": job.entity_counts,
        "check": {"status": check.status, "reason": check.reason} if check else None,
        "documents": documents,
    }
