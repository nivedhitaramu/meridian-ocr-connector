"""Pydantic models: the field schema, the model's raw output, and the API response."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentType = Literal["commercial_invoice", "packing_list", "delivery_receipt", "unknown"]
CheckStatus = Literal["Match", "Mismatch", "Incomplete", "Not applicable"]

_DOC_TYPE_ALIASES = {
    "commercial invoice": "commercial_invoice",
    "commercial_invoice": "commercial_invoice",
    "invoice": "commercial_invoice",
    "packing list": "packing_list",
    "packing_list": "packing_list",
    "delivery receipt": "delivery_receipt",
    "delivery_receipt": "delivery_receipt",
    "proof of delivery": "delivery_receipt",
}

_DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d %b, %Y", "%Y/%m/%d",
)


def parse_number(value) -> float | None:
    """'1,200' -> 1200.0, '860.5 kg' -> 860.5, 120 -> 120.0. Thousands separators stripped."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def normalize_date(value) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split()).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text  # keep as printed when not parseable


class MeridianFields(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)  # validation errors must not echo values

    invoice_number: str | None = None
    shipper_name: str | None = None
    receiver_name: str | None = None
    shipment_date: str | None = None
    total_quantity: int | None = None
    total_weight_kg: float | None = None

    @field_validator("invoice_number", "shipper_name", "receiver_name", mode="before")
    @classmethod
    def _clean_str(cls, v):
        if v is None:
            return None
        v = " ".join(str(v).split())
        return v or None

    @field_validator("shipment_date", mode="before")
    @classmethod
    def _date(cls, v):
        return normalize_date(v)

    @field_validator("total_quantity", mode="before")
    @classmethod
    def _qty(cls, v):
        n = parse_number(v)
        if n is None:
            return None
        return int(n) if float(n).is_integer() else None  # 120.0 -> 120; 120.5 is not a count

    @field_validator("total_weight_kg", mode="before")
    @classmethod
    def _weight(cls, v):
        return parse_number(v)


class QuantityTotal(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    value: float
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _v(cls, v):
        n = parse_number(v)
        if n is None:
            raise ValueError("not a number")
        return n


class LLMExtraction(BaseModel):
    """What the model must return. Extra helper keys live outside `fields`."""
    model_config = ConfigDict(hide_input_in_errors=True)
    document_type: DocumentType
    fields: MeridianFields
    quantity_totals: list[QuantityTotal] = Field(default_factory=list)
    weight_unit: str | None = None

    @field_validator("document_type", mode="before")
    @classmethod
    def _doc_type(cls, v):
        key = " ".join(str(v or "").lower().replace("-", " ").split())
        return _DOC_TYPE_ALIASES.get(key, "unknown")


# ---------------------------------------------------------------- response
class Check(BaseModel):
    status: CheckStatus
    reason: str  # never contains names, IDs, phones, emails


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


class DocumentResult(BaseModel):
    slot: int
    document_type: DocumentType
    fields: MeridianFields
    quantity_unit: str | None = None
    quantity_totals: list[QuantityTotal] = Field(default_factory=list)
    page_count: int = 1
    used_vision_fallback: bool = False


class ExtractResponse(BaseModel):
    request_id: str
    document_type: DocumentType          # first document, matches the brief's contract
    fields: MeridianFields               # first document's fields
    check: Check
    pii: PIIInfo
    pipeline: PipelineInfo
    documents: list[DocumentResult]      # one entry per uploaded file / attachment
