"""Meridian Freight: commercial invoice, packing list and delivery receipt, checked on total quantity."""
from __future__ import annotations

import re

from ..base import Domain, PIIInfo, PipelineInfo
from . import rules
from .mock import mock_extract
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT
from .schemas import Check, DocumentResult, ExtractResponse, LLMExtraction


def build_document(slot: int, parsed: rules.ParsedDoc, page_count: int, used_vision_fallback: bool) -> DocumentResult:
    return DocumentResult(
        slot=slot, document_type=parsed.document_type, fields=parsed.fields,
        quantity_unit=parsed.unit, quantity_totals=parsed.totals,
        page_count=page_count, used_vision_fallback=used_vision_fallback,
    )


def build_response(request_id: str, documents: list[DocumentResult], check: Check, pii: PIIInfo,
                   pipeline: PipelineInfo) -> ExtractResponse:
    return ExtractResponse(
        request_id=request_id,
        document_type=documents[0].document_type,
        fields=documents[0].fields,
        check=check,
        pii=pii,
        pipeline=pipeline,
        documents=documents,
    )


DOMAIN = Domain(
    name="meridian",
    prompt_version=PROMPT_VERSION,
    system_prompt=SYSTEM_PROMPT,
    image_instruction="Read this redacted shipping document.",
    extraction_model=LLMExtraction,
    response_model=ExtractResponse,
    mock_extract=mock_extract,
    reference_fields=("invoice_number",),
    party_fields=("shipper_name", "receiver_name"),
    signed_document=re.compile(r"delivery\s+receipt|proof\s+of\s+delivery|\bPOD\b|received\s+by|consignee\s+sign", re.IGNORECASE),
    unsigned_title=re.compile(r"commercial\s+invoice|packing\s+list", re.IGNORECASE),
    post_process=rules.post_process,
    check=rules.check,
    build_document=build_document,
    build_response=build_response,
)
