"""Meridian's models, built from its active configuration. Changes belong in a new file under `config/`."""
from __future__ import annotations

from pathlib import Path

from ..configured import Check, QuantityTotal, Workflow, normalize_date, parse_number

ACTIVE_CONFIG = "meridian-1"

workflow = Workflow.load(Path(__file__).parent / "config" / f"{ACTIVE_CONFIG}.json")

MeridianFields = workflow.fields_model
LLMExtraction = workflow.extraction_model
DocumentResult = workflow.document_model
ExtractResponse = workflow.response_model

__all__ = ["ACTIVE_CONFIG", "Check", "DocumentResult", "ExtractResponse", "LLMExtraction", "MeridianFields",
           "QuantityTotal", "normalize_date", "parse_number", "workflow"]
