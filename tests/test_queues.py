"""Deliveries go to their own queue, so in AWS they run on a worker outside the model-only egress firewall."""
from app.worker import celery_app


def test_deliveries_have_their_own_queue():
    routes = celery_app.app.conf.task_routes
    assert routes["deliver_webhook"] == {"queue": "deliveries"}
    assert "process_job" not in routes and "process_intake" not in routes  # these stay on the default queue


def test_compose_worker_consumes_both_queues():
    from pathlib import Path
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"-Q", "celery,deliveries"' in compose
