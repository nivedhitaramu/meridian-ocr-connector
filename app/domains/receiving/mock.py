"""Offline stand-in for the model (LLM_PROVIDER=mock), tuned to samples/receiving. Never report its accuracy as the model's."""
from __future__ import annotations

import re

_UNITS = r"units?|pieces|pcs|crates?|bags?|cartons?|ctns?"
_NUM = r"\d[\d,]*"


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def mock_extract(workflow, text: str):
    head = text[:300].lower()
    if "goods received note" in head or "goods receipt" in head:
        kind = "goods_receipt"
    elif "purchase order" in head:
        kind = "purchase_order"
    else:
        kind = "unknown"
    totals = [{"value": value, "unit": unit} for value, unit in
              re.findall(rf"total\s+units?\s+(?:ordered|received)\s*[:\-]?\s*({_NUM})\s*({_UNITS})\b", text, re.IGNORECASE)]
    return workflow.extraction_model.model_validate({
        "document_type": kind,
        "fields": {
            "po_number": _find(r"\b(?:PO|purchase\s+order)\s*(?:no\.?|number|ref\.?)\s*[:#]?\s*([A-Z]{2,4}-\d{3,6})", text),
            "vendor_name": _find(r"^(?:vendor|supplier)\s*[:\-]\s*([^\n]+?)\s*$", text),
            "buyer_name": _find(r"^(?:buyer|bill\s+to|received\s+at)\s*[:\-]\s*([^\n]+?)\s*$", text),
            "document_date": _find(r"^date\s*[:\-]\s*([^\n]+?)\s*$", text),
            "total_units": totals[0]["value"] if totals else None,
        },
        "quantity_totals": totals,
        "weight_unit": None,
    })
