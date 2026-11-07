"""Build the synthetic test set for the receiving workflow: purchase orders and goods received notes.

    python scripts/make_receiving_samples.py

Writes samples/receiving/*.pdf, receiving_sheet.csv and receiving_cases.csv. Every name, company and number is made up.
"""
from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples" / "receiving"
W, H = A4
BUYER = "Northline Warehouse Pvt Ltd"
STAFF = ["Ravi Shankar", "Meena Iyer", "Arjun Pillai", "Kavya Nair", "Sanjay Rao"]

# id, PO number, vendor, date shown, date ISO, ordered (value, unit), received (value, unit), expected status
SETS = [
    ("R01", "PO-40011", "Coastal Agro Exports", "03 Mar 2026", "2026-03-03", (240, "crates"), (240, "crates"), "Match"),
    ("R02", "PO-40027", "Deccan Packaging Industries", "05 Mar 2026", "2026-03-05", (1200, "units"), (1200, "units"), "Match"),
    ("R03", "PO-40038", "Sunrise Textiles Ltd", "09 Mar 2026", "2026-03-09", (80, "cartons"), (76, "cartons"), "Mismatch"),
    ("R04", "PO-40042", "Malabar Spice Traders", "11 Mar 2026", "2026-03-11", (150, "bags"), (15, "crates"), "Mismatch"),
    ("R05", "PO-40055", "Konkan Hardware Enterprises", "14 Mar 2026", "2026-03-14", (64, "crates"), None, "Incomplete"),
]


def _page(path: Path, title: str, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Synthetic document")
    c.setAuthor("synthetic")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, H - 60, title)
    c.setFont("Helvetica", 11)
    y = H - 100
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
    c.showPage()
    c.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sheet, cases = [], []
    for index, (sid, po, vendor, shown, iso, ordered, received, status) in enumerate(SETS):
        staff = STAFF[index % len(STAFF)]
        o_total, ordered_unit = ordered
        _page(OUT / f"{sid}_po.pdf", "PURCHASE ORDER", [
            f"PO Number: {po}", f"Date: {shown}", f"Vendor: {vendor}", f"Buyer: {BUYER}",
            f"Approved by: {staff}", f"Phone: +91 98{index}00 1{index}234",
            "Item A", "Item B", f"Total Units Ordered: {o_total:,} {ordered_unit}",
        ])
        fields = {"po_number": po, "vendor_name": vendor, "buyer_name": BUYER, "document_date": iso}
        sheet.append({"file": f"{sid}_po.pdf", "expected_document_type": "purchase_order", **fields, "total_units": o_total})
        case = {"case": f"{sid}-pair", "file": f"{sid}_po.pdf", "file2": "", "expected_status": status}
        if received:
            r_total, received_unit = received
            _page(OUT / f"{sid}_grn.pdf", "GOODS RECEIVED NOTE", [
                f"PO Number: {po}", f"Date: {shown}", f"Vendor: {vendor}", f"Received at: {BUYER}",
                f"Received by: {STAFF[(index + 2) % len(STAFF)]}", "Condition: sealed",
                f"Total Units Received: {r_total:,} {received_unit}",
            ])
            sheet.append({"file": f"{sid}_grn.pdf", "expected_document_type": "goods_receipt", **fields, "total_units": r_total})
            case["file2"] = f"{sid}_grn.pdf"
        cases.append(case)
    with open(OUT / "receiving_sheet.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sheet[0]))
        writer.writeheader()
        writer.writerows(sheet)
    with open(OUT / "receiving_cases.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    print(f"wrote {len(sheet)} documents and {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
