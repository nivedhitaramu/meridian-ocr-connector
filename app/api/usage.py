"""Usage metering: documents and model use per organization, and the plan's monthly limit."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.plans import monthly_limit
from ..db.models import Organization, UsageRecord
from ..db.session import get_db
from .deps import Member, require_role

router = APIRouter(prefix="/v1")


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_totals(session: Session, organization_id: uuid.UUID, now: datetime | None = None) -> dict[str, int]:
    row = session.execute(select(
        func.coalesce(func.sum(UsageRecord.documents), 0), func.coalesce(func.sum(UsageRecord.model_calls), 0),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0), func.coalesce(func.sum(UsageRecord.output_tokens), 0),
    ).where(UsageRecord.organization_id == organization_id, UsageRecord.created_at >= month_start(now))).one()
    return {"documents": int(row[0]), "model_calls": int(row[1]), "input_tokens": int(row[2]), "output_tokens": int(row[3])}


def over_limit(session: Session, organization_id: uuid.UUID, adding: int) -> bool:
    """True when this many more documents would pass the plan's monthly limit."""
    limit = monthly_limit(session.scalar(select(Organization.plan).where(Organization.id == organization_id)))
    return limit is not None and month_totals(session, organization_id)["documents"] + adding > limit


@router.get("/usage")
def usage(member: Member = Depends(require_role("supervisor")), session: Session = Depends(get_db)):
    """This calendar month (UTC). Counts survive retention, because they hold no document data."""
    plan = session.scalar(select(Organization.plan).where(Organization.id == member.organization_id))
    totals = month_totals(session, member.organization_id)
    limit = monthly_limit(plan)
    return {"plan": plan, "month": month_start().date().isoformat(), "limit": limit, **totals,
            "remaining": None if limit is None else max(limit - totals["documents"], 0)}
