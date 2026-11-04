"""The upload, 202, poll and result flow, with storage and job handling. Uses a fake pipeline unless noted."""
import shutil
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import config
from app.core.errors import PipelineError
from app.db import models
from app.domains.base import PIIInfo, PipelineInfo
from app.domains.meridian.domain import build_response
from app.domains.meridian.schemas import Check, DocumentResult, MeridianFields
from app.ingestion import storage
from app.pipeline import runner
from app.worker import jobs, queue
from test_auth import client, clerk_settings, token  # noqa: F401  (shared fixtures)

EXP = int(time.time()) + 3600
ALICE = {"Authorization": f"Bearer {token(sub='user_alice', email='alice@example.com', exp=EXP)}"}
BOB = {"Authorization": f"Bearer {token(sub='user_bob', email='bob@example.com', exp=EXP)}"}
PDF = b"%PDF-1.4 fictional"


def fake_response(status="Match", files=None):
    documents = [DocumentResult(slot=i + 1, document_type="commercial_invoice", quantity_unit="carton",
                                fields=MeridianFields(invoice_number="MF-1", shipper_name="Kestrel Exports", total_quantity=120))
                 for i in range(len(files or [1]))]
    return build_response("request-id", documents, Check(status=status, reason="Fixed reason."),
                          PIIInfo(masked_before_llm=True, entity_counts={"PERSON": 2}),
                          PipelineInfo(prompt_version="v-test", timings_ms={"ocr": 1}))


@pytest.fixture
def api(client, tmp_path, monkeypatch):  # noqa: F811
    http, make_session = client
    store = storage.LocalStore(tmp_path / "files")
    delivered = []
    monkeypatch.setattr(storage, "store", lambda: store)
    monkeypatch.setattr("app.api.shipments.store", lambda: store)
    monkeypatch.setattr(jobs, "store", lambda: store)
    monkeypatch.setattr(jobs, "new_session", make_session)
    monkeypatch.setattr(queue, "enqueue", lambda org, job: delivered.append((str(org), str(job))))
    monkeypatch.setattr(runner, "run", lambda files: fake_response(files=files))
    return http, make_session, store, delivered


def start_org(http, headers=ALICE):
    return http.post("/v1/organizations", json={"name": "Fictional Org"}, headers=headers).json()["id"]


def new_shipment(http, headers=ALICE, reference="MF-1"):
    return http.post("/v1/shipments", json={"reference": reference}, headers=headers).json()["id"]


def upload(http, shipment, data=PDF, headers=ALICE, filename="priya-raman-passport.pdf"):
    return http.post(f"/v1/shipments/{shipment}/documents", files={"file": (filename, data)}, headers=headers)


def ready_job(http, delivered, headers=ALICE):
    start_org(http)
    shipment = new_shipment(http)
    upload(http, shipment)
    upload(http, shipment)
    response = http.post(f"/v1/shipments/{shipment}/jobs", headers=headers)
    assert response.status_code == 202
    return shipment, response.json()["id"]


def stored_files(store):
    return [p for p in store.root.rglob("*") if p.is_file()] if store.root.exists() else []


def test_celery_task_retries_a_temporary_failure(monkeypatch):
    from app.pipeline import pii
    from app.worker.celery_app import process_job

    monkeypatch.setattr(pii, "warm_up", lambda: None)
    calls = []

    def flaky(organization_id, job_id):
        calls.append(job_id)
        if len(calls) == 1:
            raise jobs.TryAgain("llm_http_error")

    monkeypatch.setattr(jobs, "process", flaky)
    result = process_job.apply(args=["org", "job"], retries=0, throw=False)
    assert len(calls) == 2 and result.successful()


def test_celery_settings_survive_a_dying_worker():
    from app.worker.celery_app import app as celery_app

    assert celery_app.conf.task_acks_late and celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.accept_content == ["json"]


def test_full_flow_upload_accept_process_poll(api):
    http, _, store, delivered = api
    shipment, job_id = ready_job(http, delivered)
    assert http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["status"] == "queued"
    assert len(delivered) == 1 and delivered[0][1] == job_id  # only IDs go through the queue
    assert len(stored_files(store)) == 2

    jobs.process(*delivered[0])

    body = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()
    assert body["status"] == "succeeded"
    assert body["check"] == {"status": "Match", "reason": "Fixed reason."}
    assert len(body["documents"]) == 2 and body["documents"][0]["fields"]["total_quantity"] == 120
    assert body["entity_counts"] == {"PERSON": 2}
    assert stored_files(store) == []
    detail = http.get(f"/v1/shipments/{shipment}", headers=ALICE).json()
    assert detail["status"] == "checked"
    assert {d["processing_status"] for d in detail["documents"]} == {"succeeded"}


def test_filename_is_never_stored(api):
    http, make_session, store, _ = api
    start_org(http)
    shipment = new_shipment(http)
    assert upload(http, shipment).status_code == 201
    assert "priya" not in str(stored_files(store)).lower()
    with make_session() as session:
        key = session.scalars(select(models.Document.storage_key)).one()
        assert "priya" not in key.lower()


def test_upload_checks_bytes_and_size(api, monkeypatch):
    http, _, store, _ = api
    start_org(http)
    shipment = new_shipment(http)
    assert upload(http, shipment, b"MZ renamed.pdf").status_code == 415
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 5)
    assert upload(http, shipment).status_code == 413
    assert stored_files(store) == []


def test_upload_is_audited_without_values(api):
    http, _, _, _ = api
    start_org(http)
    upload(http, new_shipment(http))
    events = http.get("/v1/audit-events", headers=ALICE).json()
    assert "document.uploaded" in [e["action"] for e in events]
    assert "priya" not in str(events).lower()


def test_duplicate_reference_is_a_409(api):
    http, _, _, _ = api
    start_org(http)
    new_shipment(http)
    assert http.post("/v1/shipments", json={"reference": "MF-1"}, headers=ALICE).status_code == 409


def test_job_needs_a_document(api):
    http, _, _, delivered = api
    start_org(http)
    assert http.post(f"/v1/shipments/{new_shipment(http)}/jobs", headers=ALICE).status_code == 409
    assert delivered == []


def test_idempotency_key_returns_the_same_job(api):
    http, _, _, delivered = api
    key = {"Idempotency-Key": "abc"}
    shipment, first = ready_job(http, delivered, headers={**ALICE, **key})
    again = http.post(f"/v1/shipments/{shipment}/jobs", headers={**ALICE, **key})
    assert again.status_code == 202 and again.json()["id"] == first
    assert len(delivered) == 1


def test_delivered_twice_runs_once(api, monkeypatch):
    http, _, _, delivered = api
    _, job_id = ready_job(http, delivered)
    jobs.process(*delivered[0])
    monkeypatch.setattr(runner, "run", lambda files: pytest.fail("a finished job must not run again"))
    jobs.process(*delivered[0])
    assert http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["attempts"] == 1


def test_worker_dying_midway_can_be_retried_without_duplicates(api, monkeypatch):
    http, make_session, store, delivered = api
    _, job_id = ready_job(http, delivered)

    def dies(files):
        raise KeyboardInterrupt  # a process dying, not a handled error

    monkeypatch.setattr(runner, "run", dies)
    with pytest.raises(KeyboardInterrupt):
        jobs.process(*delivered[0])
    assert http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["status"] == "running"
    assert len(stored_files(store)) == 2  # still there for the retry

    monkeypatch.setattr(runner, "run", lambda files: fake_response(files=files))
    jobs.process(*delivered[0])
    body = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()
    assert body["status"] == "succeeded" and body["attempts"] == 2
    with make_session() as session:
        assert len(session.scalars(select(models.VerificationResult)).all()) == 1
        assert len(session.scalars(select(models.ExtractionResult)).all()) == 2


def test_temporary_error_keeps_files_and_tries_again(api, monkeypatch):
    http, _, store, delivered = api
    _, job_id = ready_job(http, delivered)

    def busy(files):
        raise PipelineError("llm_http_error")

    monkeypatch.setattr(runner, "run", busy)
    with pytest.raises(jobs.TryAgain):
        jobs.process(*delivered[0])
    assert http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["status"] == "queued"
    assert len(stored_files(store)) == 2


def test_gives_up_after_the_last_attempt(api, monkeypatch):
    http, _, store, delivered = api
    _, job_id = ready_job(http, delivered)
    monkeypatch.setattr(config, "JOB_MAX_ATTEMPTS", 1)

    def busy(files):
        raise PipelineError("llm_rate_limited")

    monkeypatch.setattr(runner, "run", busy)
    jobs.process(*delivered[0])
    body = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()
    assert body["status"] == "failed" and body["error_class"] == "llm_rate_limited"
    assert stored_files(store) == []


def test_manual_review_saves_a_safe_record_and_deletes_files(api, monkeypatch):
    http, make_session, store, delivered = api
    _, job_id = ready_job(http, delivered)

    def blocked(files):
        raise PipelineError("manual_review_residual_pii")

    monkeypatch.setattr(runner, "run", blocked)
    jobs.process(*delivered[0])
    body = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()
    assert body["status"] == "manual_review" and body["error_class"] == "manual_review_residual_pii"
    assert body["check"] is None and body["documents"] == []
    assert stored_files(store) == []


def test_re_run_keeps_earlier_results(api):
    http, make_session, _, delivered = api
    shipment, first = ready_job(http, delivered)
    jobs.process(*delivered[0])
    upload(http, shipment)
    second = http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).json()["id"]
    jobs.process(*delivered[1])
    assert http.get(f"/v1/jobs/{first}", headers=ALICE).json()["status"] == "succeeded"
    assert http.get(f"/v1/jobs/{second}", headers=ALICE).json()["status"] == "succeeded"
    with make_session() as session:
        assert len(session.scalars(select(models.VerificationResult)).all()) == 2


def test_queue_down_fails_the_job_clearly(api, monkeypatch):
    http, _, _, _ = api
    start_org(http)
    shipment = new_shipment(http)
    upload(http, shipment)

    def down(org, job):
        raise ConnectionError("broker down")

    monkeypatch.setattr(queue, "enqueue", down)
    response = http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE)
    assert response.status_code == 503
    assert http.get(f"/v1/shipments/{shipment}", headers=ALICE).json()["jobs"][0]["status"] == "failed"


def test_another_tenant_gets_404s(api):
    http, _, _, delivered = api
    shipment, job_id = ready_job(http, delivered)
    start_org(http, BOB)
    assert http.get(f"/v1/shipments/{shipment}", headers=BOB).status_code == 404
    assert http.get(f"/v1/jobs/{job_id}", headers=BOB).status_code == 404
    assert upload(http, shipment, headers=BOB).status_code == 404
    assert http.post(f"/v1/shipments/{shipment}/jobs", headers=BOB).status_code == 404
    assert http.get("/v1/shipments", headers=BOB).json() == []


def test_sweep_removes_abandoned_files_and_clears_the_key(api, monkeypatch):
    http, make_session, store, _ = api
    start_org(http)
    upload(http, new_shipment(http))
    monkeypatch.setattr(config, "STORAGE_MAX_AGE_SECONDS", -1)
    assert jobs.sweep_abandoned() == 1
    assert stored_files(store) == []
    with make_session() as session:
        document = session.scalars(select(models.Document)).one()
        assert document.storage_key is None and document.deleted_at is not None


def test_sweep_leaves_recent_files(api):
    http, _, store, _ = api
    start_org(http)
    upload(http, new_shipment(http))
    assert jobs.sweep_abandoned() == 0
    assert len(stored_files(store)) == 1


def test_s3_store_round_trip(monkeypatch):
    moto = pytest.importorskip("moto")
    import boto3

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fictional")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fictional")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with moto.mock_aws():
        boto3.client("s3").create_bucket(Bucket="uploads")
        store = storage.S3Store("uploads")
        key = storage.new_key(uuid.uuid4(), "pdf")
        store.put(key, PDF)
        assert store.get(key) == PDF
        assert store.older_than(3600) == []
        assert store.older_than(-1) == [key]
        store.delete(key)
        assert store.older_than(-1) == []


@pytest.mark.skipif(shutil.which("tesseract") is None or shutil.which("pdftoppm") is None, reason="needs OCR tools")
def test_same_status_as_the_extract_endpoint(client, tmp_path, monkeypatch):  # noqa: F811
    http, make_session = client
    monkeypatch.setattr(config, "LLM_PROVIDER", "mock")
    store = storage.LocalStore(tmp_path / "files")
    delivered = []
    monkeypatch.setattr("app.api.shipments.store", lambda: store)
    monkeypatch.setattr(jobs, "store", lambda: store)
    monkeypatch.setattr(jobs, "new_session", make_session)
    monkeypatch.setattr(queue, "enqueue", lambda org, job: delivered.append((str(org), str(job))))
    samples = Path("samples")
    invoice, packing = (samples / "S04_invoice.pdf").read_bytes(), (samples / "S04_packing.pdf").read_bytes()

    direct = http.post("/v1/extract", files={"file": ("a", invoice), "file2": ("b", packing)}).json()["check"]

    start_org(http)
    shipment = new_shipment(http)
    upload(http, shipment, invoice)
    upload(http, shipment, packing)
    job_id = http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).json()["id"]
    jobs.process(*delivered[0])
    assert http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["check"] == direct
    assert direct["status"] == "Mismatch"
