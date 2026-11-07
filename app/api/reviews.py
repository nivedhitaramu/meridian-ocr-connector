"""Exceptions, human review, and summaries read from saved, safe job data."""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import audit
from ..db.models import Document, ExtractionResult, Organization, ProcessingJob, ReviewAction, Shipment, VerificationResult
from ..db.session import get_db
from ..domains import registry
from ..pipeline.pii import PLACEHOLDER_RE
from .deps import Forbidden, Member, NotFound, ROLE_RANKS, current_member, request_id_for, require_role
from .shipments import contains
from ..worker import queue, webhooks

router = APIRouter(prefix="/v1")

RECENT_JOBS = 200
TREND_JOBS = 5000
MINIMUM_RETENTION_DAYS = 7


class NewReview(BaseModel):
    action: Literal["resolve", "follow_up"]
    reason: str = Field(min_length=1, max_length=300)
    corrected_quantity: int | None = Field(default=None, ge=0)


def _now() -> datetime:
    """Approval state depends on review order, and the database default is only precise to the second on SQLite."""
    return datetime.now(timezone.utc)


class Retention(BaseModel):
    days: int | None = Field(ge=MINIMUM_RETENTION_DAYS, le=3650)


class Submission(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class ApprovalSteps(BaseModel):
    steps: list[Literal["supervisor", "admin"]] = Field(min_length=1, max_length=3)

    @field_validator("steps")
    @classmethod
    def seniority_only_rises(cls, steps: list[str]) -> list[str]:
        if any(ROLE_RANKS[a] > ROLE_RANKS[b] for a, b in zip(steps, steps[1:])):
            raise ValueError("steps must not go down in seniority")
        return steps


@dataclass
class Approval:
    """Where a case stands, worked out from its saved reviews so nothing can drift out of step."""
    steps: list[str]
    approvers: list[uuid.UUID] = field(default_factory=list)
    submitted: bool = False
    resolved: bool = False

    @property
    def next_role(self) -> str:
        return self.steps[min(len(self.approvers), len(self.steps) - 1)]

    @property
    def is_last_step(self) -> bool:
        return len(self.approvers) + 1 >= len(self.steps)

    def can_act(self, member: Member) -> bool:
        return (not self.resolved and ROLE_RANKS[member.role] >= ROLE_RANKS[self.next_role]
                and member.user_id not in self.approvers)


def _steps(session: Session, member: Member) -> list[str]:
    return session.get(Organization, member.organization_id).approval_steps or ["supervisor"]


def _approval(reviews: list[ReviewAction], steps: list[str]) -> Approval:
    state = Approval(steps=steps)
    for review in reviews:
        if review.action == "submit":
            state.submitted = True
        elif review.action == "approve":
            state.approvers.append(review.reviewer_id)
        elif review.action == "follow_up":  # back to the start: earlier approvals no longer stand
            state.approvers, state.submitted = [], False
        elif review.action == "resolve":
            state.resolved = True
    return state


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


def _reviews_by_job(session: Session, member: Member, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ReviewAction]]:
    grouped: dict[uuid.UUID, list[ReviewAction]] = {job_id: [] for job_id in job_ids}
    rows = session.scalars(select(ReviewAction).where(
        ReviewAction.organization_id == member.organization_id, ReviewAction.job_id.in_(job_ids))
        .order_by(ReviewAction.created_at, ReviewAction.id))
    for row in rows:
        grouped[row.job_id].append(row)
    return grouped


@router.get("/exceptions")
def list_exceptions(limit: int = Query(50, ge=1, le=200), member: Member = Depends(current_member),
                    session: Session = Depends(get_db)):
    rows = _open_exceptions(session, member, limit)
    steps = _steps(session, member)
    reviews = _reviews_by_job(session, member, [row[0].id for row in rows])
    items = []
    for job, reference, check in rows:
        state = _approval(reviews[job.id], steps)
        items.append({
            "job_id": str(job.id), "shipment_id": str(job.shipment_id), "reference": reference,
            "job_status": job.job_status, "error_class": job.error_class,
            "check_status": check.status if check else None, "reason": check.reason if check else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "approval": {"required": len(steps), "approved": len(state.approvers), "next_role": state.next_role,
                         "submitted": state.submitted, "can_act": state.can_act(member), "is_last_step": state.is_last_step},
            "history": [_review_json(review) for review in reviews[job.id]],
        })
    return items


@router.post("/jobs/{job_id}/submit", status_code=201)
def submit_for_approval(request: Request, job_id: uuid.UUID, body: Submission, member: Member = Depends(current_member),
                        session: Session = Depends(get_db)):
    """Any member can raise a case. This records who asked and why, and approves nothing."""
    job = _job(session, member, job_id)
    rows = list(session.scalars(select(ReviewAction).where(ReviewAction.job_id == job.id)
                                .order_by(ReviewAction.created_at, ReviewAction.id)))
    if _approval(rows, ["supervisor"]).resolved:
        return JSONResponse(status_code=409, content={"error": "This case is already resolved."})
    review = ReviewAction(organization_id=member.organization_id, job_id=job.id, reviewer_id=member.user_id,
                          action="submit", reason=body.reason.strip(), created_at=_now())
    session.add(review)
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.APPROVAL_SUBMITTED, f"review:{review.id}",
                 request_id_for(request))
    session.commit()
    return _review_json(review)


@router.patch("/organization/retention")
def set_retention(request: Request, body: Retention, member: Member = Depends(require_role("admin")),
                  session: Session = Depends(get_db)):
    """Empty keeps records. A number deletes older shipments and their results every night."""
    organization = session.get(Organization, member.organization_id)
    organization.retention_days = body.days
    audit.record(session, member.organization_id, member.user_id, audit.RETENTION_CHANGED,
                 f"organization:{organization.id}", request_id_for(request))
    session.commit()
    return {"retention_days": body.days}


@router.get("/analytics/trends")
def analytics_trends(days: int = Query(30, ge=1, le=90), member: Member = Depends(current_member),
                     session: Session = Depends(get_db)):
    """Every number comes from saved rows. Person-only parties are never named as suppliers."""
    organization = member.organization_id
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.execute(
        select(ProcessingJob, VerificationResult.status)
        .outerjoin(VerificationResult, VerificationResult.job_id == ProcessingJob.id)
        .where(ProcessingJob.organization_id == organization, ProcessingJob.created_at >= since)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id).limit(TREND_JOBS)
    ).all()

    daily: dict[str, Counter[str]] = {}
    for job, status in rows:
        day = daily.setdefault(job.created_at.date().isoformat(), Counter())
        day["jobs"] += 1
        day["mismatches"] += status == "Mismatch"
        day["manual_review"] += job.job_status == "manual_review"
        day["failed"] += job.job_status == "failed"

    party = registry.active().party_fields[0]
    mismatched = {job.shipment_id: status == "Mismatch" for job, status in reversed(rows) if status}
    suppliers: dict[str, Counter[str]] = {}
    extractions = session.execute(
        select(Document.shipment_id, ExtractionResult.fields)
        .join(ExtractionResult, ExtractionResult.document_id == Document.id)
        .where(Document.organization_id == organization, Document.shipment_id.in_(list(mismatched)))
    ).all() if mismatched else []
    for shipment_id, shipper in {(shipment_id, (fields or {}).get(party)) for shipment_id, fields in extractions}:
        if shipper and not PLACEHOLDER_RE.search(shipper):
            supplier = suppliers.setdefault(shipper, Counter())
            supplier["shipments"] += 1
            supplier["mismatches"] += mismatched[shipment_id]

    checked = [job.id for job, status in rows if status]
    corrected = set(session.scalars(select(ReviewAction.job_id).where(
        ReviewAction.organization_id == organization, ReviewAction.correction.is_not(None),
        ReviewAction.job_id.in_(checked)))) if checked else set()
    return {
        "days": days,
        "daily": [{"date": date, "jobs": c["jobs"], "mismatches": c["mismatches"], "manual_review": c["manual_review"], "failed": c["failed"]}
                  for date, c in sorted(daily.items(), reverse=True)],
        "suppliers": [{"name": name, "shipments": c["shipments"], "mismatches": c["mismatches"]}
                      for name, c in sorted(suppliers.items(), key=lambda item: (-item[1]["mismatches"], -item[1]["shipments"], item[0]))[:10]],
        "checks": len(checked),
        "corrected_checks": len(corrected),
    }


@router.patch("/organization/approval-steps")
def set_approval_steps(request: Request, body: ApprovalSteps, member: Member = Depends(require_role("admin")),
                       session: Session = Depends(get_db)):
    organization = session.get(Organization, member.organization_id)
    organization.approval_steps = body.steps
    audit.record(session, member.organization_id, member.user_id, audit.APPROVAL_STEPS_CHANGED,
                 f"organization:{organization.id}", request_id_for(request))
    session.commit()
    return {"approval_steps": body.steps}


@router.get("/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=200), q: str | None = Query(None, max_length=100),
              status: str | None = Query(None, max_length=20), member: Member = Depends(current_member),
              session: Session = Depends(get_db)):
    """Processing history, newest first. Every value comes from a saved row."""
    query = (select(ProcessingJob, Shipment.reference, VerificationResult.status)
             .join(Shipment, Shipment.id == ProcessingJob.shipment_id)
             .outerjoin(VerificationResult, VerificationResult.job_id == ProcessingJob.id)
             .where(ProcessingJob.organization_id == member.organization_id))
    if q and q.strip():
        query = query.where(Shipment.reference.ilike(contains(q), escape="\\"))
    if status:
        query = query.where(ProcessingJob.job_status == status)
    rows = session.execute(query.order_by(ProcessingJob.created_at.desc(), ProcessingJob.id).limit(limit)).all()
    return [{"id": str(job.id), "shipment_id": str(job.shipment_id), "reference": reference, "status": job.job_status,
             "check_status": check_status, "error_class": job.error_class, "attempts": job.attempts,
             "created_at": job.created_at.isoformat() if job.created_at else None,
             "finished_at": job.finished_at.isoformat() if job.finished_at else None}
            for job, reference, check_status in rows]


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
    rows = list(session.scalars(select(ReviewAction).where(ReviewAction.job_id == job.id)
                                .order_by(ReviewAction.created_at, ReviewAction.id)))
    state = _approval(rows, _steps(session, member))
    if state.resolved:
        return JSONResponse(status_code=409, content={"error": "This case is already resolved."})
    action = body.action
    if action == "resolve":
        if ROLE_RANKS[member.role] < ROLE_RANKS[state.next_role]:
            raise Forbidden
        if member.user_id in state.approvers:
            return JSONResponse(status_code=409, content={"error": "Someone else must approve this step."})
        action = "resolve" if state.is_last_step else "approve"
    correction = {"total_quantity": body.corrected_quantity} if body.corrected_quantity is not None else None
    review = ReviewAction(organization_id=member.organization_id, job_id=job.id, reviewer_id=member.user_id,
                          action=action, reason=body.reason.strip(), correction=correction, created_at=_now())
    session.add(review)
    session.flush()
    audit.record(session, member.organization_id, member.user_id, audit.REVIEW_RECORDED, f"review:{review.id}",
                 request_id_for(request))
    deliveries = webhooks.create_deliveries(session, job) if action == "resolve" else []  # now verified by a person
    session.commit()
    for delivery_id in deliveries:
        try:
            queue.enqueue_webhook(member.organization_id, delivery_id)
        except Exception:  # the review is saved; a broker outage must not undo it
            pass
    return _review_json(review)


@router.get("/analytics/summary")
def analytics_summary(member: Member = Depends(current_member), session: Session = Depends(get_db)):
    organization = member.organization_id
    jobs = session.execute(select(ProcessingJob.job_status, func.count()).where(
        ProcessingJob.organization_id == organization).group_by(ProcessingJob.job_status)).all()
    checks = session.execute(select(VerificationResult.status, func.count()).where(
        VerificationResult.organization_id == organization).group_by(VerificationResult.status)).all()
    open_rows = _open_exceptions(session, member, RECENT_JOBS)
    steps = _steps(session, member)
    reviews = _reviews_by_job(session, member, [row[0].id for row in open_rows])
    states = [_approval(rows, steps) for rows in reviews.values()]
    return {
        "shipments": session.scalar(select(func.count()).select_from(Shipment).where(Shipment.organization_id == organization)),
        "jobs_by_status": {status: count for status, count in jobs},
        "checks_by_status": {status: count for status, count in checks},
        "open_exceptions": len(open_rows),
        "waiting_for_you": sum(1 for state in states if state.can_act(member) and (state.submitted or state.approvers)),
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
    totals = [sum(job.timings_ms.values()) for job, _ in finished if job.timings_ms]
    read = [job for job, _ in finished if job.used_vision_fallback is not None]
    fallbacks = sum(1 for job in read if job.used_vision_fallback)
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
        "average_latency_ms": round(sum(totals) / len(totals)) if totals else 0,
        "vision_fallback_rate": round(fallbacks / len(read), 3) if read else 0,
        "latest": latest,
        "average_stage_ms": {stage: round(sum(values) / len(values)) for stage, values in stages.items()},
        "entities_by_type": dict(entities),
        "outcomes": dict(Counter(job.job_status for job, _ in finished)),
        "checks_by_status": dict(Counter(status for _, status in finished if status)),
    }
