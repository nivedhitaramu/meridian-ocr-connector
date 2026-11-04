"""Step 5: the business rule. Pure functions, no I/O, easy to unit test.

Documented choices (see README):
- total_quantity counts the unit printed next to the total. When a page prints two
  totals (e.g. cartons and pieces) the field holds the shipping-unit total (cartons /
  packages), because put-away is done by carton.
- The check compares like with like: if the other document's unit is among this
  document's printed totals, those two numbers are compared. No pack size is ever guessed.
- Weight never changes the status.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import Check, LLMExtraction, MeridianFields, QuantityTotal

LB_TO_KG = 0.45359237

_UNIT_GROUPS = {
    "carton": {"carton", "cartons", "ctn", "ctns", "ctn.", "ctns."},
    "piece": {"piece", "pieces", "pc", "pcs", "pcs.", "nos", "nos.", "no", "units", "unit", "ea", "each"},
    "package": {"package", "packages", "pkg", "pkgs", "pkg.", "pkgs.", "packs", "pack"},
    "pallet": {"pallet", "pallets", "plt", "plts"},
    "case": {"case", "cases", "cs"},
    "box": {"box", "boxes", "bx"},
    "bag": {"bag", "bags"},
    "roll": {"roll", "rolls"},
    "drum": {"drum", "drums"},
}
_SHIPPING_UNITS = ("carton", "package", "case", "box", "pallet", "bag", "drum", "roll")


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.strip().lower()
    for canonical, names in _UNIT_GROUPS.items():
        if u in names:
            return canonical
    return u.rstrip("s.") or None


@dataclass
class ParsedDoc:
    document_type: str
    fields: MeridianFields
    totals: list[QuantityTotal]  # units normalized

    @property
    def unit(self) -> str | None:
        """Unit of fields.total_quantity."""
        if self.fields.total_quantity is None:
            return None
        for t in self.totals:
            if t.value == self.fields.total_quantity:
                return t.unit
        return self.totals[0].unit if self.totals else None


def _totals_only(totals: list[QuantityTotal], stated: int | None) -> list[QuantityTotal]:
    """Models sometimes list item rows beside the total. A total is never smaller than its rows,
    so keep the largest value for each unit. Different units stay apart: no pack size is guessed."""
    largest: dict[str | None, QuantityTotal] = {}
    for total in totals:
        if total.unit not in largest or total.value > largest[total.unit].value:
            largest[total.unit] = total
    if stated is not None and len(largest) == 1:
        only = next(iter(largest.values()))
        if stated > only.value:  # the model's own total field saw a total its list missed
            largest[only.unit] = QuantityTotal(value=stated, unit=only.unit)
    return list(largest.values())


def post_process(ext: LLMExtraction) -> ParsedDoc:
    """Deterministic clean-up after the model: units, pounds -> kg, primary total."""
    fields = ext.fields.model_copy()
    totals = _totals_only([QuantityTotal(value=t.value, unit=normalize_unit(t.unit)) for t in ext.quantity_totals],
                          fields.total_quantity)

    if fields.total_weight_kg is not None and (ext.weight_unit or "").strip().lower() in {"lb", "lbs", "pound", "pounds"}:
        fields.total_weight_kg = round(fields.total_weight_kg * LB_TO_KG, 2)

    if totals:
        primary = next((t for t in totals if t.unit in _SHIPPING_UNITS), totals[0])
        if float(primary.value).is_integer():
            fields.total_quantity = int(primary.value)
    elif fields.total_quantity is not None:
        totals = [QuantityTotal(value=fields.total_quantity, unit=None)]
    return ParsedDoc(ext.document_type, fields, totals)


def _pick_comparable(inv: ParsedDoc, pl: ParsedDoc) -> tuple[QuantityTotal, QuantityTotal] | None:
    for a in inv.totals:
        for b in pl.totals:
            if a.unit and a.unit == b.unit:
                return a, b
    return None


def _plural(unit: str) -> str:
    return unit + ("es" if unit.endswith("x") else "s")


def _fmt(n: float) -> str:
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,}"


def check(docs: list[ParsedDoc]) -> Check:
    invoices = [d for d in docs if d.document_type == "commercial_invoice"]
    packing = [d for d in docs if d.document_type == "packing_list"]
    receipts = [d for d in docs if d.document_type == "delivery_receipt"]

    if not invoices and not packing:
        if receipts and len(receipts) == len(docs):
            return Check(status="Not applicable", reason="Only a delivery receipt was provided; there is no quantity to compare.")
        return Check(status="Incomplete", reason="No commercial invoice or packing list was recognized.")
    if not invoices:
        return Check(status="Incomplete", reason="Packing list provided without a commercial invoice.")
    if not packing:
        return Check(status="Incomplete", reason="Commercial invoice provided without a packing list.")
    if len(invoices) > 1 or len(packing) > 1:
        return Check(status="Incomplete", reason="More than one invoice or packing list; upload one pair at a time.")

    inv, pl = invoices[0], packing[0]
    if inv.fields.total_quantity is None or pl.fields.total_quantity is None:
        return Check(status="Mismatch", reason="A total quantity could not be read; check the documents by hand.")

    pair = _pick_comparable(inv, pl)
    if pair is None:
        iu, pu = inv.unit, pl.unit
        if iu and pu and iu != pu:
            return Check(status="Mismatch",
                         reason=f"Units differ: the invoice counts {_plural(iu)} and the packing list counts {_plural(pu)}.")
        pair = (QuantityTotal(value=inv.fields.total_quantity, unit=iu),
                QuantityTotal(value=pl.fields.total_quantity, unit=pu))

    a, b = pair
    unit = f" {_plural(a.unit)}" if a.unit else ""
    if a.value == b.value:
        return Check(status="Match", reason=f"Invoice quantity equals packing-list quantity ({_fmt(a.value)}{unit}).")
    return Check(status="Mismatch",
                 reason=f"Invoice quantity {_fmt(a.value)} differs from packing-list quantity {_fmt(b.value)}{unit}.")
