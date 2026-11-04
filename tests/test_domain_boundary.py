"""The pipeline works through the Domain interface, so a second workflow needs no pipeline changes."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import BaseModel

from app.core import config
from app.domains import registry
from app.domains.base import Domain
from app.pipeline import ocr, pii, runner
from app.pipeline.ocr import OCRResult, Word


def test_pipeline_has_no_meridian_imports():
    for path in Path("app/pipeline").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "meridian" not in (node.module or ""), path.name
            if isinstance(node, ast.Import):
                assert not any("meridian" in alias.name for alias in node.names), path.name


def test_active_domain_comes_from_settings():
    assert registry.active().name == config.DOMAIN == "meridian"


def test_unknown_domain_is_refused():
    with pytest.raises(ValueError):
        registry.get("nothing-here")


class Fields(BaseModel):
    reference: str | None = None
    vendor: str | None = None


class Extraction(BaseModel):
    document_type: str
    fields: Fields


class Doc(BaseModel):
    slot: int
    document_type: str
    fields: Fields
    used_vision_fallback: bool


class Response(BaseModel):
    request_id: str
    documents: list[Doc]
    check: dict
    pii: dict
    pipeline: dict


@pytest.fixture
def other_domain(monkeypatch):
    domain = Domain(
        name="other",
        prompt_version="other-v1",
        system_prompt="Read this other document.",
        image_instruction="Read this.",
        extraction_model=Extraction,
        response_model=Response,
        mock_extract=lambda text: Extraction(document_type="claim", fields=Fields(reference="C-1", vendor="Acme Trading")),
        reference_fields=("reference",),
        party_fields=("vendor",),
        signed_document=re.compile(r"never matches"),
        unsigned_title=re.compile(r"claim", re.IGNORECASE),
        post_process=lambda extraction: extraction,
        check=lambda parsed: SimpleNamespace(status="Paid" if parsed else "Unpaid"),
        build_document=lambda slot, parsed, pages, fallback: Doc(
            slot=slot, document_type=parsed.document_type, fields=parsed.fields, used_vision_fallback=fallback),
        build_response=lambda request_id, documents, check, pii_info, pipeline: Response(
            request_id=request_id, documents=documents, check={"status": check.status},
            pii=pii_info.model_dump(), pipeline=pipeline.model_dump()),
    )
    registry.register(domain)
    monkeypatch.setattr(config, "DOMAIN", "other")
    monkeypatch.setattr(config, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(ocr, "load_pages", lambda path, kind: [Image.new("RGB", (100, 100), "white")])
    words = [Word(0, "claim", 1, 1, 9, 9, 95.0, 0, 5, (1, 1, 0))]
    monkeypatch.setattr(ocr, "run_ocr", lambda images: OCRResult("claim " * 12, words, images, 95.0))
    monkeypatch.setattr(pii, "detect", lambda text: [])
    return domain


def test_a_second_domain_runs_through_the_same_pipeline(other_domain, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    result = runner.run([b"%PDF-1.4 fake"])
    assert result.check == {"status": "Paid"}
    assert result.documents[0].fields.reference == "C-1"
    assert result.pipeline["prompt_version"] == "other-v1"
    assert result.pii["masked_before_llm"] is True
    assert list(tmp_path.iterdir()) == []
