"""Meridian's rule, which the engine in `domains/configured.py` runs from its configuration.

Documented choices (see README):
- total_quantity counts the unit printed next to the total. When a page prints two
  totals (e.g. cartons and pieces) the field holds the shipping-unit total (cartons /
  packages), because put-away is done by carton.
- The check compares like with like: if the other document's unit is among this
  document's printed totals, those two numbers are compared. No pack size is ever guessed.
- Weight never changes the status.
"""
from __future__ import annotations

from ..configured import ParsedDoc
from .schemas import workflow

check = workflow.check
normalize_unit = workflow.normalize_unit
post_process = workflow.post_process

__all__ = ["ParsedDoc", "check", "normalize_unit", "post_process"]
