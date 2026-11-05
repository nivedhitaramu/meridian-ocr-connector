"""Hand a job to the queue. Kept apart so the API needn't import the pipeline's heavy models to enqueue."""
from __future__ import annotations

import uuid


def enqueue(organization_id: uuid.UUID, job_id: uuid.UUID) -> None:
    from .celery_app import process_job

    process_job.delay(str(organization_id), str(job_id))


def enqueue_webhook(organization_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
    from .celery_app import deliver_webhook

    deliver_webhook.delay(str(organization_id), str(delivery_id))
