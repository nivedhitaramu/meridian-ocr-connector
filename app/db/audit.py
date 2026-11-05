"""Audit events: who did what, to which record, in which request. Never field values or document content.

The caller commits, so an event and the change it describes land together.
"""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent

ORGANIZATION_CREATED = "organization.created"
ORGANIZATION_RENAMED = "organization.renamed"
MEMBER_ADDED = "member.added"
MEMBER_REMOVED = "member.removed"
MEMBER_ROLE_CHANGED = "member.role_changed"
SESSION_STARTED = "session.started"
DOCUMENT_UPLOADED = "document.uploaded"  # for #20
REVIEW_RECORDED = "review.recorded"  # for #27
API_KEY_CREATED = "api_key.created"
API_KEY_ROTATED = "api_key.rotated"
API_KEY_REVOKED = "api_key.revoked"
WEBHOOK_ADDED = "webhook.added"
WEBHOOK_REMOVED = "webhook.removed"
RETENTION_CHANGED = "retention.changed"
RETENTION_APPLIED = "retention.applied"
APPROVAL_SUBMITTED = "approval.submitted"
APPROVAL_STEPS_CHANGED = "approval.steps_changed"


def record(session: Session, organization_id: uuid.UUID, actor_id: uuid.UUID | None, action: str,
           target: str | None, request_id: str | None) -> None:
    session.add(AuditEvent(organization_id=organization_id, actor_id=actor_id, action=action,
                           target=target, request_id=request_id))


def record_session_once(session: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, clerk_session_id: str,
                        request_id: str | None) -> None:
    """The API never sees a sign-in, only tokens, so count each Clerk session's first use in an organization."""
    target = "session:" + hashlib.sha256(clerk_session_id.encode()).hexdigest()[:32]
    seen = session.scalar(select(AuditEvent.id).where(
        AuditEvent.organization_id == organization_id, AuditEvent.action == SESSION_STARTED,
        AuditEvent.target == target).limit(1))
    if seen is None:
        record(session, organization_id, actor_id, SESSION_STARTED, target, request_id)
        session.commit()


def recent(session: Session, organization_id: uuid.UUID, limit: int) -> list[AuditEvent]:
    return list(session.scalars(select(AuditEvent).where(AuditEvent.organization_id == organization_id)
                                .order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit)))
