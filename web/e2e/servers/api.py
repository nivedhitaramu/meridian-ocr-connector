"""The real API on a throwaway database with the mock model, for browser tests. Threads stand in for Celery."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())
Path(os.environ["E2E_WORK_DIR"]).mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pipeline import pii  # noqa: E402
from app.worker import intake, jobs, queue, webhooks  # noqa: E402

pii.warm_up()


def job(organization, job_id):
    for _ in range(3):
        try:
            return jobs.process(str(organization), str(job_id))
        except jobs.TryAgain:
            time.sleep(1)


def background(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


queue.enqueue = lambda organization, job_id: background(job, organization, job_id)
queue.enqueue_intake = lambda organization, batch: background(intake.process_batch, str(organization), str(batch))
queue.enqueue_webhook = lambda organization, delivery: background(webhooks.deliver, str(organization), str(delivery))
uvicorn.run(app, host="127.0.0.1", port=8199, log_level="warning")
