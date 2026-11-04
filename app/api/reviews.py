"""Exceptions, human review, and summaries read from saved, safe job data."""
from __future__ import annotations

import uuid
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import audit
from ..db.models import ProcessingJob, ReviewAction, Shipment, VerificationResult
from ..db.session import get_db
from .deps import Member, NotFound, current_member, request_id_for, require_role

router = APIRouter(prefix="/v1")

RECENT_JOBS = 200


class NewReview(BaseModel):
    action: Literal["resolve", "follow_up"]
    reason: str = Field(min_length=1, max_length=300)
    corrected_quantity: int | None = Field(default=None, ge=0)


def _job(session: Session, member: Member, job_id: uuid.UUID) -> ProcessingJob:
    job = session.scalar(select(ProcessingJob).where(
        ProcessingJob.id == job_id, ProcessingJob.organization_id == member.organization_id))
    if job is None:
        raise NotFound
    return job


def _review_json(review: ReviewAction) -> dict:
    return {"id": str(review.id), "reviewer_id": str(review.reviewer_id), "action": review.action, "reason": review.reason,
            "correction": review.correction, "created_at": review.created_at.isoformat() if review.created_at else None}


def _open_exceptions(session: Session, member: Member, limit: int) -> list[tuple]:
    rows = session.execute(
        select(ProcessingJob, Shipment.reference, VerificationResult)
        .join(Shipment, Shipment.id == ProcessingJob.shipment_id)
        .outerjoin(VerificationResult, VerificationResult.job_id == ProcessingJob.id)
        .where(ProcessingJob.organization_id == member.organization_id)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id).limit(RECENT_JOBS)
    ).all()
    resolved = set(session.scalars(select(ReviewAction.job_id).where(
        ReviewAction.organization_id == member.organization_id, ReviewAction.action == "resolve")))
    exceptions = [row for row in rows if row[0].id not in resolved and (
        row[0].job_status in ("manual_review", "failed") or (row[2] is not None and row[2].status == "Mismatch"))]
    return exceptions[:limit]


@router.get("/exceptions")
def list_exceptions(limit: int = Query(50, ge=1, le=200), member: Member = Depends(current_member),
                    session: Session = Depends(get_db)):
    return [{"job_id": str(job.id), "shipment_id": str(job.shipment_id), "reference": reference,
             "job_status": job.job_status, "error_class": job.error_class,
             "check_status": check.status if check else None, "reason": check.reason if check else None,
             "created_at": job.created_at.isoformat() if job.created_at else None}
            for job, reference, check in _open_exceptions(session, member, limit)]


@router.get("/jobs/{job_id}/reviews")
def list_reviews(job_id: uuid.UUID, member: Member = Depends(current_member), session: Session = Depends(get_db)):
    job = _job(session, member, job_id)
    rows = session.scalars(select(ReviewAction).where(ReviewAction.job_id == job.id)
                           .order_by(ReviewAction.created_at, ReviewAction.id))
    return [_review_json(r) for r in rows]


@router.post("/jobs/{job_id}/reviews", status_code=201)
def add_review(request: Request, job_id: uuid.UUID, body: NewReview, member: Member = Depends(require_role("supervisor")),
               session: Session = Depends(get_db)):
    """The model's result stays as it was. A correction is saved beside it, with who made it and why."""
    job = _job(session, member, job_id)
    correction = {"total_quantity": body.corrected_quantity} if body.corrected_quantity is not None else None
    review = ReviewAction(organization_id=member.organization_id, job_id=job.id, reviewer_id=member.user_id,
                          action=body.action, reason=body.reason.strip(), correction=correction)
    session.add(review)
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.REVIEW_RECORDED, f"review:{review.id}",
                 request_id_for(request))
    session.commit()
    return _review_json(review)


@router.get("/analytics/summary")
def analytics_summary(member: Member = Depends(current_member), session: Session = Depends(get_db)):
    organization = member.organization_id
    jobs = session.execute(select(ProcessingJob.job_status, func.count()).where(
        ProcessingJob.organization_id == organization).group_by(ProcessingJob.job_status)).all()
    checks = session.execute(select(VerificationResult.status, func.count()).where(
        VerificationResult.organization_id == organization).group_by(VerificationResult.status)).all()
    return {
        "shipments": session.scalar(select(func.count()).select_from(Shipment).where(Shipment.organization_id == organization)),
        "jobs_by_status": {status: count for status, count in jobs},
        "checks_by_status": {status: count for status, count in checks},
        "open_exceptions": len(_open_exceptions(session, member, RECENT_JOBS)),
    }


@router.get("/observability/summary")
def observability_summary(member: Member = Depends(require_role("supervisor")), session: Session = Depends(get_db)):
    """Counts and timings only. These saved columns can't hold document text, so nothing here can leak it."""
    rows = session.execute(
        select(ProcessingJob, VerificationResult.status)
        .outerjoin(VerificationResult, VerificationResult.job_id == ProcessingJob.id)
        .where(ProcessingJob.organization_id == member.organization_id)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id).limit(RECENT_JOBS)
    ).all()
    finished = [row for row in rows if row[0].finished_at is not None]
    entities: Counter[str] = Counter()
    stages: dict[str, list[int]] = {}
    for job, _ in finished:
        entities.update(job.entity_counts or {})
        for stage, milliseconds in (job.timings_ms or {}).items():
            stages.setdefault(stage, []).append(milliseconds)
    latest = None
    if finished:
        job, status = finished[0]
        latest = {"job_id": str(job.id), "job_status": job.job_status, "check_status": status, "error_class": job.error_class,
                  "timings_ms": job.timings_ms or {}, "entity_counts": job.entity_counts or {}}
    return {
        "jobs_measured": len(finished),
        "latest": latest,
        "average_stage_ms": {stage: round(sum(values) / len(values)) for stage, values in stages.items()},
        "entities_by_type": dict(entities),
        "outcomes": dict(Counter(job.job_status for job, _ in finished)),
        "checks_by_status": dict(Counter(status for _, status in finished if status)),
    }
