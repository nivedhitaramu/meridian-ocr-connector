"""Warehouse receiving: a purchase order and a goods received note, checked on total units.

The second workflow, built from configuration alone. Select it with DOMAIN=receiving.
"""
from __future__ import annotations

from pathlib import Path

from ..configured import Workflow
from .mock import mock_extract

ACTIVE_CONFIG = "receiving-1"

workflow = Workflow.load(Path(__file__).parent / "config" / f"{ACTIVE_CONFIG}.json")
DOMAIN = workflow.domain(lambda text: mock_extract(workflow, text))
