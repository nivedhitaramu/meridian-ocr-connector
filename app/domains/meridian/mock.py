"""Offline stand-in for the model (LLM_PROVIDER=mock).

Regex rules tuned to the synthetic samples in this repo. Use it for unit tests and CI
when there is no API key. Do not report its accuracy as the model's accuracy.
"""
from __future__ import annotations

import re

from .schemas import LLMExtraction

_UNITS = r"cartons?|ctns?|pieces|pcs|pc|packages|pkgs?|pallets?|cases?|boxes|units"
_NUM = r"\d[\d,]*(?:\.\d+)?"


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def mock_extract(text: str) -> LLMExtraction:
    head = text[:300].lower()
    if "packing list" in head:
        doc_type = "packing_list"
    elif "delivery receipt" in head or "proof of delivery" in head:
        doc_type = "delivery_receipt"
    elif "invoice" in head:
        doc_type = "commercial_invoice"
    else:
        doc_type = "unknown"

    totals = []
    # "Total Quantity: 120 CTNS" / "Total Received: 1,200 PCS"
    for value, unit in re.findall(rf"total\s+(?:quantity|qty|received)\s*[:\-]?\s*({_NUM})\s*({_UNITS})\b",
                                  text, re.IGNORECASE):
        totals.append({"value": value, "unit": unit})
    # "Total Cartons: 50" / "Total Pieces: 1,200"
    for unit, value in re.findall(rf"total\s+({_UNITS})\s*[:\-]?\s*({_NUM})", text, re.IGNORECASE):
        totals.append({"value": value, "unit": unit})

    weight = re.search(rf"(?:gross|total)\s+weight\s*[:\-]?\s*({_NUM})\s*(kgs?|lbs?)\b", text, re.IGNORECASE)

    return LLMExtraction.model_validate({
        "document_type": doc_type,
        "fields": {
            "invoice_number": _find(r"(?:invoice\s*(?:no\.?|number|ref\.?)|shipment\s+ref\.?)\s*[:#]?\s*([A-Z]{2,4}-\d{3,6})", text),
            "shipper_name": _find(r"^shipper\s*[:\-]\s*([^\n]+?)\s*$", text),
            "receiver_name": _find(r"^(?:consignee|receiver)\s*[:\-]\s*([^\n]+?)\s*$", text),
            "shipment_date": _find(r"^(?:shipment\s+date|invoice\s+date|delivery\s+date|date)\s*[:\-]\s*([^\n]+?)\s*$", text),
            "total_quantity": totals[0]["value"] if totals else None,
            "total_weight_kg": weight.group(1) if weight else None,
        },
        "quantity_totals": totals,
        "weight_unit": weight.group(2) if weight else None,
    })
