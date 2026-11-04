"""What the pipeline needs from a document workflow. A new workflow fills in one Domain and registers it."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern
from typing import Any

from pydantic import BaseModel, Field


class PIIInfo(BaseModel):
    masked_before_llm: bool = False
    entity_counts: dict[str, int] = Field(default_factory=dict)
    placeholder_count: int = 0


class PipelineInfo(BaseModel):
    ocr_engine: str = "tesseract"
    used_vision_fallback: bool = False
    model: str | None = None
    prompt_version: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class Domain:
    name: str
    prompt_version: str
    system_prompt: str
    image_instruction: str
    extraction_model: type[BaseModel]  # must have `document_type` and `fields`
    response_model: type[BaseModel]    # must have `documents`, `check.status` and `pii`
    mock_extract: Callable[[str], Any]  # offline stand-in used when LLM_PROVIDER=mock

    # Personal data checks on what the model returned.
    reference_fields: tuple[str, ...]  # checked for ID-like values only
    party_fields: tuple[str, ...]      # organization names, also checked for people

    # Which documents carry a signature band, for redaction.
    signed_document: Pattern[str]      # anywhere in the text
    unsigned_title: Pattern[str]       # in the first page's title area

    # The business decision. The pipeline never looks inside these.
    post_process: Callable[[Any], Any]
    check: Callable[[list[Any]], Any]
    build_document: Callable[..., Any]
    build_response: Callable[..., Any]
