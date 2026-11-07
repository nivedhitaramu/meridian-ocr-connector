"""Run a shipment's job and save its safe results. PostgreSQL holds the truth; the queue only delivers IDs.

A job can be delivered more than once, for example after a worker dies. A finished job is left alone,
an unfinished one starts again from its stored files, and results land in one transaction.
"""
from __future__ import annotations

import logging
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import config
from ..core.errors import PipelineError
from ..db.models import Document, ExtractionResult, ProcessingJob, Shipment, UsageRecord, VerificationResult
from ..db.session import new_session
from ..db.tenancy import set_scope
from ..ingestion.storage import store
from ..pipeline import runner
from . import queue, webhooks

log = logging.getLogger("meridian")

FINISHED = {"succeeded", "failed", "manual_review"}
# Worth another try: the provider was busy or unreachable, and the files are still here.
TEMPORARY = {"llm_http_error", "llm_rate_limited", "llm_unreachable"}


class TryAgain(Exception):
    """A temporary failure. The job stays open, and Celery delivers it again later."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pending_documents(session: Session, job: ProcessingJob) -> list[Document]:
    return list(session.scalars(
        select(Document).where(Document.shipment_id == job.shipment_id, Document.storage_key.is_not(None))
        .order_by(Document.created_at, Document.id)
    ))


def _delete_files(documents: list[Document]) -> None:
    for document in documents:
        store().delete(document.storage_key)
        document.storage_key = None
        document.deleted_at = _now()


def _finish(session: Session, job: ProcessingJob, documents: list[Document], status: str, error_class: str | None,
            pipeline=None) -> None:
    """Every finished job that read documents is metered, whatever its outcome, because the work was done."""
    if documents:
        session.add(UsageRecord(organization_id=job.organization_id, job_id=job.id, documents=len(documents),
                                model_calls=getattr(pipeline, "model_calls", 0), input_tokens=getattr(pipeline, "prompt_tokens", 0),
                                output_tokens=getattr(pipeline, "completion_tokens", 0)))
    job.job_status = status
    job.error_class = error_class
    job.finished_at = _now()
    for document in documents:
        document.processing_status = status
    _delete_files(documents)
    deliveries = webhooks.create_deliveries(session, job)
    organization_id = job.organization_id
    session.commit()
    log.info(json.dumps({"level": "info", "stage": "job.end", "outcome": status, "error_class": error_class}))
    for delivery_id in deliveries:
        try:
            queue.enqueue_webhook(organization_id, delivery_id)
        except Exception:  # the job's result is safe; a broker outage must not fail it
            log.warning(json.dumps({"level": "warning", "stage": "webhook", "error_class": "queue_unavailable"}))


def _save_results(session: Session, job: ProcessingJob, documents: list[Document], response) -> None:
    data = response.model_dump()
    for document, result in zip(documents, data["documents"]):
        document.document_type = result["document_type"]
        document.page_count = result.get("page_count")
        session.add(ExtractionResult(
            organization_id=job.organization_id, document_id=document.id, fields=result["fields"],
            quantity_unit=result.get("quantity_unit"), prompt_version=data["pipeline"].get("prompt_version"),
        ))
    session.add(VerificationResult(organization_id=job.organization_id, job_id=job.id,
                                   status=data["check"]["status"], reason=data["check"]["reason"],
                                   config_version=data["pipeline"].get("config_version")))
    job.timings_ms = data["pipeline"].get("timings_ms")
    job.entity_counts = data["pii"].get("entity_counts")
    job.used_vision_fallback = bool(data["pipeline"].get("used_vision_fallback"))
    shipment = session.get(Shipment, job.shipment_id)
    shipment.status = "checked"


def process(organization_id: str, job_id: str) -> None:
    organization, job_key = uuid.UUID(organization_id), uuid.UUID(job_id)
    with new_session() as session:
        set_scope(session, None, organization)
        job = session.get(ProcessingJob, job_key)
        if job is None or job.job_status in FINISHED:
            return
        job.job_status = "running"
        job.attempts += 1
        attempts = job.attempts
        session.commit()

        set_scope(session, None, organization)
        job = session.get(ProcessingJob, job_key)
        documents = _pending_documents(session, job)
        if not documents:
            _finish(session, job, documents, "failed", "no_documents")
            return

        try:
            response = runner.run([store().get(d.storage_key) for d in documents])
        except PipelineError as err:
            if err.error_class in TEMPORARY and attempts < config.JOB_MAX_ATTEMPTS:
                job.job_status = "queued"
                job.error_class = err.error_class
                session.commit()
                raise TryAgain(err.error_class) from err
            status = "manual_review" if err.error_class.startswith("manual_review") else "failed"
            _finish(session, job, documents, status, err.error_class)
            return
        except OSError:  # a stored file is missing or unreadable
            _finish(session, job, documents, "failed", "file_unavailable")
            return

        _save_results(session, job, documents, response)
        _finish(session, job, documents, "succeeded", None, response.pipeline)


def sweep_abandoned() -> int:
    """Remove files left behind by a crash. A storage key names its organization."""
    removed = 0
    for key in store().older_than(config.STORAGE_MAX_AGE_SECONDS):
        store().delete(key)
        removed += 1
        organization = key.split("/", 1)[0]
        try:
            organization_id = uuid.UUID(organization)
        except ValueError:
            continue
        with new_session() as session:
            set_scope(session, None, organization_id)
            document = session.scalar(select(Document).where(Document.storage_key == key))
            if document is not None:
                document.storage_key = None
                document.deleted_at = _now()
                session.commit()
    return removed
