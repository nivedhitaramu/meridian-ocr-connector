"""Step 4: one model call that classifies and extracts. Only masked text reaches it."""
from __future__ import annotations

import base64
import io
import json
import re
import time
from dataclasses import dataclass

import httpx
from PIL import Image
from pydantic import ValidationError

from ..core import config
from ..core.errors import PipelineError
from ..domains.meridian.prompt import SYSTEM_PROMPT
from ..domains.meridian.schemas import LLMExtraction


RETRY_WAITS_S = (2, 5, 12)  # temporary errors are common on busy hosted models
TEMPORARY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class LLMResult:
    extraction: LLMExtraction
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _post(base_url: str, api_key: str, payload: dict) -> dict:
    if not api_key and "localhost" not in base_url and "127.0.0.1" not in base_url:
        raise PipelineError("llm_not_configured")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for wait in (*RETRY_WAITS_S, None):
        try:
            resp = httpx.post(f"{base_url}/chat/completions", json=payload, headers=headers,
                              timeout=config.LLM_TIMEOUT_S)
        except httpx.HTTPError as exc:
            if wait is None:
                raise PipelineError("llm_unreachable") from exc
        else:
            if resp.status_code not in TEMPORARY_STATUS or wait is None:
                break
        time.sleep(wait)
    if resp.status_code == 429:
        raise PipelineError("llm_rate_limited")
    if resp.status_code >= 400:
        raise PipelineError("llm_http_error")
    return resp.json()


def _parse(body: dict, model: str) -> LLMResult:
    try:
        content = body["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        extraction = LLMExtraction.model_validate(json.loads(content))
    except (KeyError, IndexError, json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise PipelineError("schema_invalid") from exc
    usage = body.get("usage") or {}
    return LLMResult(extraction, model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def extract_from_text(masked_text: str) -> LLMResult:
    if config.LLM_PROVIDER == "mock":
        from .mock_llm import mock_extract
        return LLMResult(mock_extract(masked_text), "mock-regex")

    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Document text:\n{masked_text}"},
        ],
    }
    last_error: PipelineError | None = None
    for _ in range(2):  # one retry on a malformed answer
        try:
            return _parse(_post(config.LLM_BASE_URL, config.LLM_API_KEY, payload), config.LLM_MODEL)
        except PipelineError as err:
            if err.error_class != "schema_invalid":
                raise
            last_error = err
    raise last_error  # type: ignore[misc]


def extract_from_images(redacted_pages: list[Image.Image]) -> LLMResult:
    """Called only with pages already painted out by vision.redact_pages()."""
    if not config.VISION_MODEL:
        raise PipelineError("manual_review_required")
    content: list[dict] = [{"type": "text", "text": "Read this redacted shipping document."}]
    if len(redacted_pages) > config.VISION_MAX_PAGES:
        raise PipelineError("manual_review_too_many_pages")
    for page in redacted_pages:
        buf = io.BytesIO()
        page.convert("RGB").save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {
        "model": config.VISION_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
    }
    return _parse(_post(config.VISION_BASE_URL, config.VISION_API_KEY, payload), config.VISION_MODEL)
