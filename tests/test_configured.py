"""Workflows run from configuration, stay deterministic, and old versions stay explainable."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains import registry
from app.domains.configured import Workflow, WorkflowConfig
from app.domains.meridian.domain import DOMAIN
from app.pipeline import runner
from test_auth import client, clerk_settings  # noqa: F401  (shared fixtures)
from test_jobs import ALICE, api, fake_response, start_org  # noqa: F401
from test_reviews import run_job

CONFIG = Path("app/domains/meridian/config/meridian-1.json")
RELEASED = {"meridian-1": "978cb07fa63e9b7c4bbea8def64592f7c4f9c2636a966d7a980b5d2fb23783b8"}

ORDERS = {
    "version": "orders-1", "domain": "orders", "prompt_version": "orders-v1",
    "system_prompt": "Fill the JSON.", "image_instruction": "Read this.",
    "document_types": {"purchase_order": ["purchase order"], "goods_receipt": ["goods receipt", "grn"], "unknown": []},
    "fields": {"po_number": "text", "vendor": "text", "ordered_on": "date", "units": "count"},
    "privacy": {"reference_fields": ["po_number"], "party_fields": ["vendor"], "signed_document": "signed", "unsigned_title": "purchase order"},
    "units": {"crate": ["crate", "crates"]}, "primary_units": ["crate"],
    "check": {
        "type": "compare_totals", "field": "units", "left": "purchase_order", "right": "goods_receipt", "not_applicable_alone": "unknown",
        "reasons": {
            "not_applicable": "Nothing to compare.", "none_recognized": "Nothing recognized.", "missing_left": "No order.",
            "missing_right": "No receipt.", "too_many": "One pair only.", "unreadable": "Unreadable.",
            "unit_clash": "{left_unit} against {right_unit}.", "match": "Both say {left_value}{unit}.",
            "differ": "{left_value} ordered, {right_value} received{unit}.",
        },
    },
}


def parsed(workflow, kind, units):
    model = workflow.extraction_model
    return workflow.post_process(model(document_type=kind, fields=workflow.fields_model(units=units),
                                       quantity_totals=[{"value": units, "unit": "crates"}]))


def test_a_new_workflow_needs_only_configuration():
    workflow = Workflow(WorkflowConfig.model_validate(ORDERS))
    domain = workflow.domain()
    assert domain.reference_fields == ("po_number",) and domain.config_version == "orders-1"
    same = workflow.check([parsed(workflow, "purchase_order", 10), parsed(workflow, "goods_receipt", 10)])
    assert same.status == "Match" and same.reason == "Both say 10 crates."
    other = workflow.check([parsed(workflow, "purchase_order", 10), parsed(workflow, "goods_receipt", 9)])
    assert other.status == "Mismatch" and other.reason == "10 ordered, 9 received crates."
    assert workflow.check([parsed(workflow, "purchase_order", 10)]).status == "Incomplete"
    assert set(workflow.fields_model().model_dump()) == set(ORDERS["fields"])


def test_field_types_normalize_values():
    workflow = Workflow(WorkflowConfig.model_validate(ORDERS))
    fields = workflow.fields_model(po_number="  A   1 ", ordered_on="02/01/2026", units="1,200")
    assert fields.po_number == "A 1" and fields.ordered_on == "2026-01-02" and fields.units == 1200
    assert workflow.extraction_model(document_type="GRN", fields=fields).document_type == "goods_receipt"
    assert workflow.extraction_model(document_type="other", fields=fields).document_type == "unknown"


def changed(path, value):
    config = copy.deepcopy(ORDERS)
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return config


@pytest.mark.parametrize("config", [
    changed(["check", "left"], "invoice"),
    changed(["check", "right"], "purchase_order"),
    changed(["check", "field"], "vendor"),
    changed(["privacy", "party_fields"], ["units"]),
    changed(["primary_units"], ["pallet"]),
    changed(["check", "reasons", "match"], "{left_value.__class__}"),
    changed(["check", "reasons", "match"], "{secret}"),
    changed(["check", "type"], "ask_the_model"),
    changed(["privacy", "signed_document"], "("),
    changed(["fields", "units"], "money"),
    changed(["version"], "../outside"),
    {**ORDERS, "surprise": True},
    {key: value for key, value in ORDERS.items() if key != "check"},
])
def test_broken_configuration_is_refused(config):
    with pytest.raises((ValidationError, ValueError)):
        WorkflowConfig.model_validate(config)


def test_every_reason_must_exist():
    config = copy.deepcopy(ORDERS)
    del config["check"]["reasons"]["unreadable"]
    with pytest.raises(ValidationError):
        WorkflowConfig.model_validate(config)


def test_released_versions_are_never_edited():
    for version, digest in RELEASED.items():
        data = CONFIG.with_name(f"{version}.json").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, f"Add a new version instead of editing {version}"


def test_meridian_keeps_its_contract():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert list(config["fields"]) == ["invoice_number", "shipper_name", "receiver_name", "shipment_date", "total_quantity", "total_weight_kg"]
    assert DOMAIN.prompt_version == "meridian-v2" and DOMAIN.config_version == "meridian-1"


def test_a_saved_result_names_its_configuration(api, monkeypatch):  # noqa: F811
    http, _, _, delivered = api
    start_org(http)

    def versioned(files):
        response = fake_response(files=files)
        response.pipeline.config_version = "meridian-1"
        return response
    monkeypatch.setattr(runner, "run", versioned)
    job_id = run_job(http, delivered)
    version = http.get(f"/v1/jobs/{job_id}", headers=ALICE).json()["config_version"]
    assert version == "meridian-1"
    assert http.get(f"/v1/configurations/{version}", headers=ALICE).json()["check"]["left"] == "commercial_invoice"


def test_old_configuration_can_be_read_but_unknown_cannot(api):  # noqa: F811
    http, _, _, _ = api
    start_org(http)
    assert http.get("/v1/configurations/meridian-1", headers=ALICE).json()["version"] == "meridian-1"
    assert http.get("/v1/configurations/nothing", headers=ALICE).status_code == 404
    assert http.get("/v1/configurations/meridian-1").status_code == 401


def test_registry_ignores_path_tricks():
    assert registry.configuration("../../secrets") is None
