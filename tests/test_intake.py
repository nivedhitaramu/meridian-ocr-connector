"""Grouping uploaded documents: confident matches join, and uncertain ones wait for a person."""
import shutil
import uuid
from pathlib import Path

import pytest

from app.db import models
from app.domains.meridian import grouping
from app.domains.meridian.grouping import Read
from app.worker import intake, queue, retention
from test_auth import client, clerk_settings  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, BOB, api, new_shipment, start_org, upload  # noqa: F401

PDF = b"%PDF-1.4 synthetic"
INVOICE = "commercial_invoice"
PACKING = "packing_list"


def reads(*pairs):
    return [Read(kind, reference, None if reference else "no_reference") for kind, reference in pairs]


@pytest.mark.parametrize("text,reference", [
    ("COMMERCIAL INVOICE\nInvoice No: MF-10040\n", "MF-10040"),
    ("Packing List\nAgainst Invoice: INV/2026/0417 Date: Mar 3, 2026\n", "INV/2026/0417"),
    ("DELIVERY RECEIPT\nShipment Ref: MF-10040\n", "MF-10040"),
    ("Proof of Delivery\nConsignment Ref: HB-2026-118\n", "HB-2026-118"),
    ("Commercial Invoice\nBill No: VGS/EXP/2291 Date: 07-Mar-2026\n", "VGS/EXP/2291"),
    ("Commercial Invoice\nInvoice No. MF-1\nShipment Ref: MF-1\n", "MF-1"),
    ("Commercial Invoice\nInvoice No: A1\n", None),
])
def test_references_are_read(text, reference):
    read = grouping.read_text(text)
    if reference:
        assert read.reference == reference and read.problem is None
    else:
        assert read.reference is None  # too short to trust


def test_two_different_references_on_a_page_are_not_guessed():
    read = grouping.read_text("Commercial Invoice\nInvoice No: MF-1001\nShipment Ref: MF-2002\n")
    assert read.reference is None and read.problem == "conflicting_references"


def test_a_label_with_no_digits_is_not_a_reference():
    assert grouping.read_text("Packing List\nAgainst Invoice: enclosed\n").problem == "no_reference"


def test_poor_scan_is_never_trusted():
    assert grouping.read_text("Invoice No: MF-1001", poor_scan=True).problem == "poor_scan"


@pytest.mark.parametrize("text,kind", [
    ("COMMERCIAL INVOICE\nx", INVOICE), ("Packing List\nAgainst Invoice: A1", PACKING),
    ("Proof of Delivery\nx", "delivery_receipt"), ("Statement\nInvoice No: A-1", "unknown"),
])
def test_document_type_comes_from_the_title(text, kind):
    assert grouping.document_type(text) == kind


def test_a_clean_pair_groups():
    decisions = grouping.decide(reads((INVOICE, "MF-1001"), (PACKING, "mf 1001")), {})
    assert [d.status for d in decisions] == [grouping.AUTO, grouping.AUTO]


@pytest.mark.parametrize("batch,known,reason", [
    ([(INVOICE, None)], {}, "no_reference"),
    ([("unknown", "MF-1001")], {}, "unknown_type"),
    ([(INVOICE, "MF-1001"), (INVOICE, "MF-1001")], {}, "duplicate_type"),
    ([(INVOICE, "MF-1O01"), (PACKING, "MF-1001")], {}, "similar_reference"),
    ([(INVOICE, "MF-10011")], {"MF1001": False}, "similar_reference"),
    ([(INVOICE, "MF-1001")], {"MF1001": True}, "shipment_already_checked"),
    ([(INVOICE, "MF-1001")], {}, "no_matching_document"),
    ([(INVOICE, "MF-1001"), (PACKING, "KX-7734")], {}, "no_matching_document"),
])
def test_uncertain_matches_go_to_review(batch, known, reason):
    decision = grouping.decide(reads(*batch), known)[0]
    assert decision.status == grouping.REVIEW and decision.reason == reason


def test_clearly_different_references_both_group():
    decisions = grouping.decide(reads((INVOICE, "MF-1001"), (PACKING, "MF-1001"), (INVOICE, "KX-7734"), (PACKING, "KX-7734")), {})
    assert all(d.status == grouping.AUTO for d in decisions)


def test_a_document_can_join_a_known_shipment_alone():
    assert grouping.decide(reads((PACKING, "MF-1001")), {"MF1001": False})[0].status == grouping.AUTO


@pytest.fixture
def batch(api, monkeypatch):  # noqa: F811
    http, make_session, store, delivered = api
    queued, results = [], []
    monkeypatch.setattr(intake, "new_session", make_session)
    monkeypatch.setattr(intake, "store", lambda: store)
    monkeypatch.setattr("app.api.intake.store", lambda: store)
    monkeypatch.setattr(queue, "enqueue_intake", lambda org, b: queued.append((str(org), str(b))))
    monkeypatch.setattr(intake, "read_document", lambda data: results.pop(0))
    return http, make_session, store, queued, results


def send(http, count=2, headers=ALICE):
    files = [("files", ("secret-customer-name.pdf", PDF, "application/pdf")) for _ in range(count)]
    return http.post("/v1/intake", headers=headers, files=files)


def test_a_clean_pair_becomes_one_shipment_without_completing(batch):
    http, make_session, _, queued, results = batch
    start_org(http)
    assert send(http).status_code == 202
    results.extend(reads((INVOICE, "MF-1001"), (PACKING, "MF-1001")))
    intake.process_batch(*queued[0])
    items = http.get("/v1/intake", headers=ALICE).json()
    assert {item["status"] for item in items} == {"grouped"}
    shipments = http.get("/v1/shipments", headers=ALICE).json()
    assert [row["reference"] for row in shipments] == ["MF-1001"]
    detail = http.get(f"/v1/shipments/{shipments[0]['id']}", headers=ALICE).json()
    assert len(detail["documents"]) == 2 and detail["jobs"] == []  # a person still starts the check
    assert "secret-customer-name" not in str(items)
    with make_session() as session:
        assert all(item.storage_key is None for item in session.query(models.IntakeItem))
        assert all(document.storage_key for document in session.query(models.Document))


def test_an_uncertain_document_creates_nothing_until_a_person_decides(batch):
    http, _, _, queued, results = batch
    start_org(http)
    send(http, 1)
    results.extend(reads((INVOICE, None)))
    intake.process_batch(*queued[0])
    assert http.get("/v1/shipments", headers=ALICE).json() == []
    item = http.get("/v1/intake", params={"status": "needs_review"}, headers=ALICE).json()[0]
    assert item["reason"] == "no_reference"
    assigned = http.post(f"/v1/intake/items/{item['id']}/assign", headers=ALICE, json={"reference": "MF-2002"})
    assert assigned.status_code == 200 and assigned.json()["status"] == "assigned"
    shipment = http.get("/v1/shipments", headers=ALICE).json()[0]
    assert shipment["reference"] == "MF-2002"
    assert len(http.get(f"/v1/shipments/{shipment['id']}", headers=ALICE).json()["documents"]) == 1
    assert http.post(f"/v1/intake/items/{item['id']}/assign", headers=ALICE, json={"reference": "MF-3"}).status_code == 409
    actions = [event["action"] for event in http.get("/v1/audit-events", headers=ALICE).json()]
    assert "intake.uploaded" in actions and "intake.assigned" in actions


def test_a_document_joins_an_existing_open_shipment(batch):
    http, _, _, queued, results = batch
    start_org(http)
    new_shipment(http, reference="MF-1001")
    send(http, 1)
    results.extend(reads((PACKING, "mf/1001")))
    intake.process_batch(*queued[0])
    rows = http.get("/v1/shipments", headers=ALICE).json()
    assert len(rows) == 1 and len(http.get(f"/v1/shipments/{rows[0]['id']}", headers=ALICE).json()["documents"]) == 1


def test_a_checked_shipment_is_not_changed_automatically(batch):
    http, _, _, queued, results = batch
    start_org(http)
    shipment = new_shipment(http, reference="MF-1001")
    upload(http, shipment)
    assert http.post(f"/v1/shipments/{shipment}/jobs", headers=ALICE).status_code == 202
    send(http, 1)
    results.extend(reads((PACKING, "MF-1001")))
    intake.process_batch(*queued[0])
    assert http.get("/v1/intake", headers=ALICE).json()[0]["reason"] == "shipment_already_checked"


def test_a_batch_delivered_twice_is_processed_once(batch):
    http, _, _, queued, results = batch
    start_org(http)
    send(http)
    results.extend(reads((INVOICE, "MF-1001"), (PACKING, "MF-1001")))
    intake.process_batch(*queued[0])
    intake.process_batch(*queued[0])
    assert len(http.get("/v1/shipments", headers=ALICE).json()) == 1


def test_a_removed_file_goes_to_expired_not_a_broken_document(batch):
    http, make_session, store, queued, results = batch
    start_org(http)
    send(http, 1)
    results.extend(reads((INVOICE, None)))
    intake.process_batch(*queued[0])
    item = http.get("/v1/intake", headers=ALICE).json()[0]
    with make_session() as session:
        store.delete(session.query(models.IntakeItem).one().storage_key)
    assert http.post(f"/v1/intake/items/{item['id']}/assign", headers=ALICE, json={"reference": "MF-1"}).status_code == 410
    assert http.get("/v1/shipments", headers=ALICE).json() == []


def test_discard_removes_the_file(batch):
    http, make_session, store, queued, results = batch
    start_org(http)
    send(http, 1)
    results.extend(reads((INVOICE, None)))
    intake.process_batch(*queued[0])
    item = http.get("/v1/intake", headers=ALICE).json()[0]
    with make_session() as session:
        key = session.query(models.IntakeItem).one().storage_key
    assert http.delete(f"/v1/intake/items/{item['id']}", headers=ALICE).status_code == 204
    with pytest.raises(OSError):
        store.get(key)


def test_intake_stays_in_its_organization(batch):
    http, _, _, queued, results = batch
    start_org(http)
    send(http, 1)
    results.extend(reads((INVOICE, None)))
    intake.process_batch(*queued[0])
    item = http.get("/v1/intake", headers=ALICE).json()[0]
    http.post("/v1/organizations", headers=BOB, json={"name": "Other"})
    assert http.get("/v1/intake", headers=BOB).json() == []
    assert http.post(f"/v1/intake/items/{item['id']}/assign", headers=BOB, json={"reference": "X-1"}).status_code == 404
    assert http.delete(f"/v1/intake/items/{item['id']}", headers=BOB).status_code == 404


def test_one_bad_file_stores_nothing_and_too_many_are_refused(batch):
    http, _, store, _, _ = batch
    start_org(http)
    files = [("files", ("a.pdf", PDF, "application/pdf")), ("files", ("b.txt", b"not a document", "text/plain"))]
    assert http.post("/v1/intake", headers=ALICE, files=files).status_code == 415
    assert http.get("/v1/intake", headers=ALICE).json() == []
    assert send(http, 21).status_code == 413


def test_queue_outage_is_reported_and_leaves_no_file(batch, monkeypatch):
    http, make_session, _, _, _ = batch
    start_org(http)

    def down(*_):
        raise ConnectionError
    monkeypatch.setattr(queue, "enqueue_intake", down)
    assert send(http, 1).status_code == 503
    with make_session() as session:
        item = session.query(models.IntakeItem).one()
        assert item.storage_key is None and item.status == "failed"


def test_personal_data_never_becomes_a_reference(monkeypatch):
    monkeypatch.setattr(intake.upload, "store", lambda data: type("S", (), {"path": "x", "kind": "pdf", "delete": lambda self: None})())
    monkeypatch.setattr(intake.ocr, "load_pages", lambda path, kind: [])
    result = type("R", (), {"text": "COMMERCIAL INVOICE\nInvoice No: ABCPE1234F\n", "needs_fallback": lambda self: False})()
    monkeypatch.setattr(intake.ocr, "run_ocr", lambda pages: result)
    assert intake.read_document(b"x").reference is None


def test_retention_keeps_working_with_intake_rows(batch, monkeypatch):
    from datetime import datetime, timedelta, timezone
    http, make_session, store, queued, results = batch
    monkeypatch.setattr(retention, "new_session", make_session)
    monkeypatch.setattr(retention, "store", lambda: store)
    org = start_org(http)
    send(http)
    results.extend(reads((INVOICE, "MF-1001"), (PACKING, "MF-1001")))
    intake.process_batch(*queued[0])
    with make_session() as session:
        session.query(models.Shipment).one().created_at = datetime.now(timezone.utc) - timedelta(days=40)
        for item in session.query(models.IntakeItem):
            item.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        session.commit()
    assert retention.apply(uuid.UUID(org), 30) == 1
    assert http.get("/v1/intake", headers=ALICE).json() == []


@pytest.mark.skipif(shutil.which("tesseract") is None or shutil.which("pdftoppm") is None, reason="needs OCR tools")
def test_real_samples_read_correctly():
    invoice = intake.read_document(Path("samples/S01_invoice.pdf").read_bytes())
    packing = intake.read_document(Path("samples/S01_packing.pdf").read_bytes())
    assert (invoice.document_type, invoice.reference) == (INVOICE, "MF-10040")
    assert (packing.document_type, packing.reference) == (PACKING, "MF-10040")
