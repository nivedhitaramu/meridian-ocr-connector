"""Database schema, as designed in docs/ARCHITECTURE.md.

Two rules keep this schema safe:
- Every tenant table has organization_id, and foreign keys between tenant tables include it,
  so a row can never point at another organization's data.
- No column may hold an original filename, OCR text, a prompt, a completion or the placeholder map.
  tests/test_db.py enforces this.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, MetaData, String,
    UniqueConstraint, Uuid, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonValue = JSON().with_variant(JSONB(), "postgresql")

MEMBER_ROLES = ("admin", "supervisor", "clerk")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "manual_review")
CHECK_STATUSES = ("Match", "Mismatch", "Incomplete", "Not applicable")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(50), default="trial")
    approval_steps: Mapped[list | None] = mapped_column(JsonValue)  # empty means one supervisor approval
    retention_days: Mapped[int | None] = mapped_column(Integer)  # empty means records are kept
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _id()
    external_id: Mapped[str] = mapped_column(String(100), unique=True)  # the Clerk user ID
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = _created_at()


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (CheckConstraint(_one_of("role", MEMBER_ROLES), name="role_allowed"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="clerk")


class OrganizationInvitation(Base):
    """Gives no access until the person with this email accepts. Deleted once answered."""
    __tablename__ = "organization_invitations"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_organization_invitations_tenant_email"),
        CheckConstraint(_one_of("role", MEMBER_ROLES), name="role_allowed"),
        Index("ix_organization_invitations_email", "email"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    email: Mapped[str] = mapped_column(String(320))  # always lower case
    role: Mapped[str] = mapped_column(String(20))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_shipments_tenant_id"),
        UniqueConstraint("organization_id", "reference", name="uq_shipments_tenant_reference"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    reference: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "shipment_id"], ["shipments.organization_id", "shipments.id"],
                             name="fk_documents_tenant_shipment", ondelete="CASCADE"),
        UniqueConstraint("organization_id", "id", name="uq_documents_tenant_id"),
        Index("ix_documents_shipment", "shipment_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    document_type: Mapped[str | None] = mapped_column(String(50))
    storage_key: Mapped[str | None] = mapped_column(String(200))  # random name; cleared once the file is deleted
    processing_status: Mapped[str] = mapped_column(String(30), default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "shipment_id"], ["shipments.organization_id", "shipments.id"],
                             name="fk_processing_jobs_tenant_shipment", ondelete="CASCADE"),
        UniqueConstraint("organization_id", "id", name="uq_processing_jobs_tenant_id"),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_processing_jobs_tenant_idempotency_key"),
        CheckConstraint(_one_of("job_status", JOB_STATUSES), name="job_status_allowed"),
        Index("ix_processing_jobs_shipment", "shipment_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    shipment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    job_status: Mapped[str] = mapped_column(String(20), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str | None] = mapped_column(String(50))
    timings_ms: Mapped[dict | None] = mapped_column(JsonValue)
    used_vision_fallback: Mapped[bool | None]
    entity_counts: Mapped[dict | None] = mapped_column(JsonValue)
    created_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "document_id"], ["documents.organization_id", "documents.id"],
                             name="fk_extraction_results_tenant_document", ondelete="CASCADE"),
        Index("ix_extraction_results_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    fields: Mapped[dict] = mapped_column(JsonValue)
    quantity_unit: Mapped[str | None] = mapped_column(String(30))
    ocr_mean_confidence: Mapped[float | None]
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = _created_at()


class VerificationResult(Base):
    __tablename__ = "verification_results"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "job_id"], ["processing_jobs.organization_id", "processing_jobs.id"],
                             name="fk_verification_results_tenant_job", ondelete="CASCADE"),
        UniqueConstraint("organization_id", "id", name="uq_verification_results_tenant_id"),
        UniqueConstraint("job_id", name="uq_verification_results_job"),
        CheckConstraint(_one_of("status", CHECK_STATUSES), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(300))  # the rule engine's template, never model text
    config_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created_at()


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "job_id"], ["processing_jobs.organization_id", "processing_jobs.id"],
                             name="fk_review_actions_tenant_job", ondelete="CASCADE"),
        ForeignKeyConstraint(["organization_id", "reviewer_id"],
                             ["organization_members.organization_id", "organization_members.user_id"],
                             name="fk_review_actions_tenant_reviewer"),
        Index("ix_review_actions_job", "job_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(String(300))
    correction: Mapped[dict | None] = mapped_column(JsonValue)  # saved beside the model's result, never over it
    created_at: Mapped[datetime] = _created_at()


class ApiKey(Base):
    """Only a hash is kept. The key itself is shown once, when it's created."""
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Mailbox(Base):
    """One inbound address per organization. The token is in the address, so it's stored as is."""
    __tablename__ = "mailboxes"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_mailboxes_organization_id"),
        UniqueConstraint("token", name="uq_mailboxes_token"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    token: Mapped[str] = mapped_column(String(24))
    allowed_senders: Mapped[list | None] = mapped_column(JsonValue)
    created_at: Mapped[datetime] = _created_at()
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageRecord(Base):
    """What one finished job used. Kept when retention deletes the job, so monthly counts stay right."""
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_usage_records_job_id"),
        Index("ix_usage_records_tenant_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    documents: Mapped[int] = mapped_column(Integer)
    model_calls: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(100))  # needed to sign each delivery, so it can't be a hash
    created_at: Mapped[datetime] = _created_at()
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    """One per endpoint and job, so a job delivered twice by the queue can't send two events."""
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("endpoint_id", "job_id", name="uq_webhook_delivery_once"),)

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntakeItem(Base):
    """One file from a batch. It holds a reference and a reason code, never document text or a filename."""
    __tablename__ = "intake_items"
    __table_args__ = (Index("ix_intake_items_batch", "batch_id"), Index("ix_intake_items_tenant_status", "organization_id", "status"))

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    storage_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    document_type: Mapped[str | None] = mapped_column(String(50))
    reference: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(String(40))
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shipments.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created_at()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = _id()
    organization_id: Mapped[uuid.UUID] = _tenant()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(50))
    target: Mapped[str | None] = mapped_column(String(100))  # a type and ID, never field values
    request_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = _created_at()
