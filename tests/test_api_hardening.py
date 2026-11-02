import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.core import config
from app.core.errors import PipelineError
from app.core.rate_limit import RateLimiter
from app.core.telemetry import LAST_TRACE
from app.pipeline import llm, ocr, runner


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "limiter", RateLimiter(100))
    return TestClient(main.app)  # no context manager, so spaCy isn't loaded at startup


def test_long_pdf_is_refused_not_cut_short(monkeypatch, tmp_path):
    import pdf2image

    monkeypatch.setattr(pdf2image, "pdfinfo_from_path", lambda path: {"Pages": 6})
    monkeypatch.setattr(pdf2image, "convert_from_path", lambda *a, **k: pytest.fail("should not render"))
    with pytest.raises(PipelineError) as e:
        ocr.load_pages(tmp_path / "long.pdf", "pdf")
    assert e.value.error_class == "too_many_pages"


def test_long_fallback_document_goes_to_manual_review(monkeypatch):
    monkeypatch.setattr(config, "VISION_MODEL", "vision-model")
    monkeypatch.setattr(llm, "_post", lambda *a: pytest.fail("should not call the model"))
    with pytest.raises(PipelineError) as e:
        llm.extract_from_images([Image.new("RGB", (10, 10))] * (config.VISION_MAX_PAGES + 1))
    assert e.value.error_class == "manual_review_too_many_pages"


def test_rejected_upload_gets_its_own_request_id(client):
    LAST_TRACE["request_id"] = "someone-elses-request"
    try:
        first = client.post("/v1/extract", files={"file": ("x", b"MZ not a pdf")})
        second = client.post("/v1/extract", files={"file": ("x", b"MZ not a pdf")})
    finally:
        LAST_TRACE.clear()
    assert first.status_code == 415
    assert first.json()["error"] == "Could not read this document."
    assert first.json()["request_id"] not in ("someone-elses-request", second.json()["request_id"])


def test_pipeline_error_reports_that_requests_id(client, monkeypatch):
    def fail(*args):
        raise PipelineError("ocr_empty")

    monkeypatch.setattr(runner, "_process_one", fail)
    response = client.post("/v1/extract", files={"file": ("x", b"%PDF-1.4")})
    assert response.status_code == 422
    assert response.json()["request_id"] == LAST_TRACE["request_id"]
    LAST_TRACE.clear()


@pytest.mark.parametrize("path", ["/v1/extract", "/v1/extract-eml"])
def test_burst_gets_a_429(client, monkeypatch, path):
    monkeypatch.setattr(main, "limiter", RateLimiter(2))
    codes = [client.post(path, files={"file": ("x", b"junk")}).status_code for _ in range(3)]
    assert codes[2] == 429 and 429 not in codes[:2]


def test_limit_resets_after_a_minute_and_is_per_client():
    now = [0.0]
    limiter = RateLimiter(1, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("b")
    assert not limiter.allow("a")
    now[0] = 61.0
    assert limiter.allow("a")


@pytest.mark.parametrize("path", ["/v1/trace/last", "/v1/metrics"])
def test_internal_endpoints_need_the_token_when_set(client, monkeypatch, path):
    assert client.get(path).status_code == 200  # open for local development
    monkeypatch.setattr(config, "INTERNAL_API_TOKEN", "secret-value")
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Internal-Token": "wrong"}).status_code == 401
    assert client.get(path, headers={"X-Internal-Token": "secret-value"}).status_code == 200
