"""Run the full API on this computer, with no Docker, PostgreSQL, Redis or Celery.

    python scripts/run_local.py

Uses SQLite in .local/ and runs background work (checks, intake, webhooks) in threads, so every website screen works.
Keys and Clerk settings still come from .env. For development and demos only: there's no row-level security on
SQLite, and work in progress is lost if the process stops. Use docker compose for the real stack.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
LOCAL.mkdir(exist_ok=True)
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# Set before the app reads its settings. Values already in the environment win.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(LOCAL / 'meridian.db').as_posix()}")
os.environ.setdefault("STORAGE_DIR", str(LOCAL / "files"))
os.environ.setdefault("OTEL_CONSOLE_EXPORT", "0")

subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pipeline import pii  # noqa: E402
from app.worker import intake, jobs, queue, webhooks  # noqa: E402


def _in_background(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _retrying(task, retry_error, attempts: int, wait: float):
    def run(*args):
        for _ in range(attempts):
            try:
                return task(*args)
            except retry_error:
                time.sleep(wait)
    return run


def _job(organization_id, job_id):
    pii.warm_up()
    _retrying(jobs.process, jobs.TryAgain, 3, 15)(str(organization_id), str(job_id))


queue.enqueue = lambda organization_id, job_id: _in_background(_job, organization_id, job_id)
queue.enqueue_intake = lambda organization_id, batch: _in_background(intake.process_batch, str(organization_id), str(batch))
queue.enqueue_webhook = lambda organization_id, delivery: _in_background(
    _retrying(webhooks.deliver, webhooks.TryAgain, 3, 30), str(organization_id), str(delivery))

if __name__ == "__main__":
    # HOST and PORT let a free host such as Render run this too (deploy/render/api.Dockerfile).
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    print(f"API on http://{host}:{port}, data in {LOCAL}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
