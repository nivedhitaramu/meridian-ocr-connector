"""The second workflow (#43): warehouse receiving, built from configuration and the same pipeline."""
import csv
import hashlib
from pathlib import Path

import pytest

from app.core import config
from app.domains import registry
from app.pipeline import runner

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "receiving"
CONFIG = Path(__file__).resolve().parent.parent / "app" / "domains" / "receiving" / "config" / "receiving-1.json"
RELEASED = "6158cfe78f48d1250aa018552f7b78beda404760431de1acefa9fbdc97cc6346"


@pytest.fixture
def receiving(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOMAIN", "receiving")
    monkeypatch.setattr(config, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    return registry.active()


def test_released_version_is_never_edited():
    assert hashlib.sha256(CONFIG.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == RELEASED


def test_found_by_name_with_no_registry_entry():
    domain = registry.get("receiving")
    assert domain.config_version == "receiving-1" and domain.reference_fields == ("po_number",)
    assert registry.get("meridian").config_version.startswith("meridian-")


@pytest.mark.parametrize("name", ["nope", "../meridian", "meridian.domain", "", "configured"])
def test_unknown_or_unsafe_names_are_refused(name):
    with pytest.raises(ValueError):
        registry.get(name)


def test_configuration_lookup_finds_both_workflows():
    assert registry.configuration("receiving-1")["domain"] == "receiving"
    assert registry.configuration("meridian-1")["domain"] == "meridian"


@pytest.mark.parametrize("case", list(csv.DictReader(open(SAMPLES / "receiving_cases.csv"))), ids=lambda c: c["case"])
def test_every_case_gets_its_expected_status(receiving, case):
    files = [SAMPLES / case["file"]] + ([SAMPLES / case["file2"]] if case["file2"] else [])
    response = runner.run([path.read_bytes() for path in files])
    assert response.check.status == case["expected_status"]
    assert response.pipeline.config_version == "receiving-1"


def test_staff_names_are_masked_and_companies_kept(receiving):
    response = runner.run([(SAMPLES / "R01_po.pdf").read_bytes(), (SAMPLES / "R01_grn.pdf").read_bytes()])
    text = response.model_dump_json()
    for person in ("Ravi Shankar", "Arjun Pillai"):
        assert person not in text
    assert response.pii.masked_before_llm and response.pii.entity_counts
    assert response.documents[0].fields.vendor_name == "Coastal Agro Exports"
