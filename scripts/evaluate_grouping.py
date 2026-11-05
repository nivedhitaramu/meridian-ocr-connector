"""Grouping accuracy on a labelled set. Local OCR only: no model is called and nothing leaves this machine.

    python scripts/evaluate_grouping.py
"""
from __future__ import annotations

import csv
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domains.meridian import grouping  # noqa: E402
from app.worker.intake import read_document  # noqa: E402

SHEETS = ((Path("samples/test_sheet.csv"), Path("samples")),
          (Path("samples/holdout/holdout_sheet.csv"), Path("samples/holdout")))


def labelled() -> list[tuple[str, str, str, grouping.Read]]:
    rows = []
    for sheet, folder in SHEETS:
        with sheet.open(encoding="utf-8") as file:
            for row in csv.DictReader(file):
                read = read_document((folder / row["file"]).read_bytes())
                rows.append((row["file"], row["invoice_number"], row["expected_document_type"], read))
    return rows


def score(title: str, rows: list[tuple[str, str, str, grouping.Read]]) -> tuple[int, int]:
    decisions = grouping.decide([row[3] for row in rows], {})
    grouped = wrong = 0
    reasons: dict[str, int] = {}
    for (name, truth, _, read), decision in zip(rows, decisions):
        if decision.status == grouping.AUTO:
            grouped += 1
            if grouping.normalize(read.reference) != grouping.normalize(truth or ""):
                wrong += 1
                print(f"  WRONG {name}")
        else:
            reasons[decision.reason] = reasons.get(decision.reason, 0) + 1
    print(f"{title}: {len(rows)} documents, {grouped} auto-grouped, {wrong} wrong, {len(rows) - grouped} sent to review {reasons}")
    return grouped, wrong


def main() -> None:
    rows = labelled()
    with_truth = [row for row in rows if row[1]]
    read_right = sum(grouping.normalize(r[3].reference or "") == grouping.normalize(r[1]) for r in with_truth)
    types_right = sum(r[3].document_type == r[2] for r in rows)
    print(f"Reference read: {read_right}/{len(with_truth)}. Document type read: {types_right}/{len(rows)}.")

    wrong_total = score("Clean batch", rows)[1]

    # Damage the same documents in the ways real paperwork goes wrong. None of these may auto-group wrongly.
    damaged = []
    for index, (name, truth, kind, read) in enumerate(rows):
        if read.reference and index % 3 == 0:  # a misread character, while its partner stays clean
            read = replace(read, reference=read.reference[:-1] + ("O" if read.reference[-1] == "0" else "0"))
        elif index % 3 == 1:
            read = replace(read, reference=None, problem="no_reference")
        damaged.append((name, truth, kind, read))
    wrong_total += score("Damaged batch", damaged)[1]

    # Two invoices claiming one reference must both wait for a person.
    twin = next(row for row in rows if row[3].reference and row[2] == "commercial_invoice")
    decisions = grouping.decide([twin[3], twin[3]], {})
    print(f"Duplicate invoices: {[d.reason for d in decisions]}")
    assert all(d.status == grouping.REVIEW for d in decisions)

    print(f"Wrong automatic matches: {wrong_total}")
    sys.exit(1 if wrong_total else 0)


if __name__ == "__main__":
    main()
