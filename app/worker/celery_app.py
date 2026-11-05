"""Celery wiring. Only IDs go through the queue, never text, filenames or field values.

Start a worker with: celery -A app.worker.celery_app worker --beat --loglevel=info
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from ..core import config
from ..pipeline import pii
from . import jobs, webhooks

app = Celery("meridian", broker=config.REDIS_URL)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,              # a job survives a worker dying partway through
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={"sweep-abandoned-uploads": {"task": "sweep_uploads", "schedule": crontab(minute=0)}},
)


@worker_process_init.connect
def _trace_tasks(**_) -> None:
    """Carry trace context across the queue. It records task names and IDs, and tasks only hold IDs."""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    CeleryInstrumentor().instrument()


@app.task(bind=True, name="process_job", max_retries=config.JOB_MAX_ATTEMPTS, default_retry_delay=30)
def process_job(self, organization_id: str, job_id: str) -> None:
    pii.warm_up()
    try:
        jobs.process(organization_id, job_id)
    except jobs.TryAgain as exc:
        raise self.retry(exc=exc)


@app.task(bind=True, name="deliver_webhook", max_retries=config.WEBHOOK_MAX_ATTEMPTS)
def deliver_webhook(self, organization_id: str, delivery_id: str) -> None:
    try:
        webhooks.deliver(organization_id, delivery_id)
    except webhooks.TryAgain as exc:
        raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)


@app.task(name="sweep_uploads")
def sweep_uploads() -> int:
    return jobs.sweep_abandoned()
