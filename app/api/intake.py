"""Upload documents together and let confident matches group themselves. Everything else waits for a person."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import config
from ..core.errors import CLIENT_MESSAGE
from ..db import audit
from ..db.models import IntakeItem, Shipment
from ..db.session import get_db
from ..domains.meridian import grouping
from ..ingestion.storage import new_key, store
from ..ingestion.upload import sniff_kind
from ..worker import intake as intake_worker
from ..worker import queue
from .deps import Member, NotFound, current_member, request_id_for

router = APIRouter(prefix="/v1")
MAX_FILES = 20


class Assignment(BaseModel):
    reference: str = Field(min_length=1, max_length=100)


def _item_json(item: IntakeItem) -> dict:
    return {"id": str(item.id), "batch_id": str(item.batch_id), "status": item.status, "document_type": item.document_type,
            "reference": item.reference, "reason": item.reason, "shipment_id": str(item.shipment_id) if item.shipment_id else None,
            "created_at": item.created_at.isoformat() if item.created_at else None}


@router.post("/intake", status_code=202)
async def upload_batch(request: Request, files: list[UploadFile] = File(...), member: Member = Depends(current_member),
                       session: Session = Depends(get_db)):
    if len(files) > MAX_FILES:
        return JSONResponse(status_code=413, content={"error": f"Upload up to {MAX_FILES} files at a time."})
    batch = uuid.uuid4()
    contents = []
    for file in files:
        data = await file.read(config.MAX_UPLOAD_BYTES + 1)
        if len(data) > config.MAX_UPLOAD_BYTES:
            return JSONResponse(status_code=413, content={"error": CLIENT_MESSAGE})
        kind = sniff_kind(data)
        if kind is None:
            return JSONResponse(status_code=415, content={"error": CLIENT_MESSAGE})
        contents.append((data, kind))
    items = []
    for data, kind in contents:  # nothing is stored until every file has passed its check
        key = new_key(member.organization_id, kind)  # the uploaded filename is never read or stored
        store().put(key, data)
        items.append(IntakeItem(id=uuid.uuid4(), organization_id=member.organization_id, batch_id=batch, storage_key=key, status="queued"))
    session.add_all(items)
    audit.record(session, member.organization_id, member.user_id, audit.INTAKE_UPLOADED, f"batch:{batch}", request_id_for(request))
    session.commit()
    try:
        queue.enqueue_intake(member.organization_id, batch)
    except Exception:  # the broker is down. Saying so beats items that wait forever.
        for item in items:
            store().delete(item.storage_key)
            item.storage_key, item.status, item.reason = None, "failed", "queue_unavailable"
        session.commit()
        return JSONResponse(status_code=503, content={"error": "We can't read these documents right now. Try again soon."})
    return {"batch_id": str(batch), "files": len(items)}


@router.get("/intake")
def list_intake(status: str | None = Query(None, max_length=20), limit: int = Query(50, ge=1, le=200),
                member: Member = Depends(current_member), session: Session = Depends(get_db)):
    query = select(IntakeItem).where(IntakeItem.organization_id == member.organization_id)
    if status:
        query = query.where(IntakeItem.status == status)
    return [_item_json(item) for item in session.scalars(query.order_by(IntakeItem.created_at.desc(), IntakeItem.id).limit(limit))]


def _waiting_item(session: Session, member: Member, item_id: uuid.UUID) -> IntakeItem:
    item = session.scalar(select(IntakeItem).where(IntakeItem.id == item_id, IntakeItem.organization_id == member.organization_id))
    if item is None:
        raise NotFound
    return item


@router.post("/intake/items/{item_id}/assign")
def assign_item(request: Request, item_id: uuid.UUID, body: Assignment, member: Member = Depends(current_member),
                session: Session = Depends(get_db)):
    """A person's decision. It can create a shipment, or join one whose reference they typed exactly."""
    item = _waiting_item(session, member, item_id)
    if item.status != grouping.REVIEW:
        return JSONResponse(status_code=409, content={"error": "This document has already been handled."})
    try:
        store().get(item.storage_key)
    except (OSError, TypeError):
        item.storage_key, item.status, item.reason = None, "expired", "file_removed"
        session.commit()
        return JSONResponse(status_code=410, content={"error": "This file was removed after waiting too long. Upload it again."})
    reference = body.reference.strip()
    shipment = session.scalar(select(Shipment).where(Shipment.organization_id == member.organization_id, Shipment.reference == reference))
    if shipment is None:
        shipment = Shipment(id=uuid.uuid4(), organization_id=member.organization_id, reference=reference)
        session.add(shipment)
        session.flush()
    intake_worker.attach(session, item, shipment)
    item.status = "assigned"
    audit.record(session, member.organization_id, member.user_id, audit.INTAKE_ASSIGNED, f"shipment:{shipment.id}", request_id_for(request))
    session.commit()
    return _item_json(item)


@router.delete("/intake/items/{item_id}", status_code=204)
def discard_item(request: Request, item_id: uuid.UUID, member: Member = Depends(current_member), session: Session = Depends(get_db)):
    item = _waiting_item(session, member, item_id)
    if item.status != grouping.REVIEW:
        return JSONResponse(status_code=409, content={"error": "This document has already been handled."})
    key = item.storage_key
    item.storage_key, item.status = None, "discarded"
    audit.record(session, member.organization_id, member.user_id, audit.INTAKE_DISCARDED, f"intake:{item.id}", request_id_for(request))
    session.commit()
    if key:
        store().delete(key)
    return Response(status_code=204)
