"""Meridian Freight: commercial invoice, packing list and delivery receipt, checked on total quantity."""
from __future__ import annotations

from .mock import mock_extract
from .schemas import workflow

DOMAIN = workflow.domain(mock_extract)
build_response = workflow.build_response
build_document = workflow.build_document
