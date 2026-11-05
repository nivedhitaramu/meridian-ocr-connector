"""Generate the final scoring set: synthetic documents made after the prompt and filters were frozen.

Run once and score once. If a failure leads to a fix, these documents stop being unseen and a later score
on them must say so. Layouts, labels, companies and units differ from samples/ and samples/holdout/ on purpose.
All names, phones, emails and tax numbers are invented.

    python scripts/make_final_set.py
    python scripts/evaluate.py --sheet samples/final/final_sheet.csv --cases samples/final/final_cases.csv

Needs reportlab, and pdf2image with Poppler for the scanned document. Outputs to samples/final/.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from pdf2image import convert_from_path
from PIL import ImageFilter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples" / "final"
LB_TO_KG = 0.45359237
FIELDS = ["invoice_number", "shipper_name", "receiver_name", "shipment_date", "total_quantity", "total_weight_kg"]
random.seed(77)


@dataclass
class Shipment:
    sid: str
    reference: str
    shipper: str
    receiver: str
    printed_date: str
    iso_date: str
    invoice_total: str   # exactly as printed
    packing_total: str
    expected_quantity: tuple[int, int]  # the field on the invoice and on the packing list
    weight: float
    weight_unit: str
    labels: dict
    contact: tuple[str, str, str]
    expected: str
    extra_line: str = ""
    page: str = "portrait"
    font: str = "Helvetica"
    scanned: bool = False


BASE_LABELS = {"title_invoice": "COMMERCIAL INVOICE", "title_packing": "PACKING LIST", "ref": "Invoice #", "ref_packing": "Reference Invoice",
               "from": "Vendor", "to": "Deliver To", "date": "Dated", "total": "Grand Total", "weight": "Net Wt"}

SHIPMENTS = [
    Shipment("F01", "KP/24-25/0918", "Kaveri Polymers Pvt Ltd", "Meridian Freight Warehouse", "12 Apr 2026", "2026-04-12",
             "1,250 PCS", "1,250 PCS", (1250, 1250), 540.25, "KGS", BASE_LABELS,
             ("Ritu Malhotra", "+91 99021 44871", "ritu@kaveripoly.example"), "Match",
             extra_line="GSTIN: 29AAACK4821F1ZQ"),
    Shipment("F02", "NWC2026-77", "Northwind Cotton", "Meridian Freight Warehouse", "April 15, 2026", "2026-04-15",
             "84 CARTONS (2,016 PCS)", "84 CARTONS (2,016 PCS)", (84, 84), 1190.0, "KG",
             {**BASE_LABELS, "from": "Seller", "to": "Buyer", "total": "Total Shipped", "weight": "Gross Weight"},
             ("Farhan Siddiqui", "+91 90043 71265", "farhan@northwind.example"), "Match",
             extra_line="Proprietor GSTIN: 27ABCPE1234F1Z5", font="Times-Roman"),
    Shipment("F03", "SB-40117", "Sagar Bulk Traders", "Meridian Freight Warehouse", "18/04/2026", "2026-04-18",
             "300 BAGS", "301 BAGS", (300, 301), 15000.0, "KG",
             {**BASE_LABELS, "ref": "Seller's Ref No", "ref_packing": "Seller's Ref No", "total": "Bags Total"},
             ("Lakshmi Menon", "+91 97411 20938", "lakshmi@sagarbulk.example"), "Mismatch"),
    Shipment("F04", "ORB/EXP/5512", "Orbis Textiles", "Meridian Freight Warehouse", "21-04-2026", "2026-04-21",
             "72 ROLLS", "72 ROLLS", (72, 72), 3306.9, "LBS",
             {**BASE_LABELS, "from": "Consignor", "to": "Consignee", "ref": "Export Invoice No", "ref_packing": "Export Invoice No", "total": "Total Rolls"},
             ("Vikram Sethi", "+91 88260 51730", "vikram@orbis.example"), "Match", page="landscape"),
    Shipment("F05", "DLX-88203", "Delta Lane Exports", "Meridian Freight Warehouse", "Apr 24, 2026", "2026-04-24",
             "196 CTNS", "196 CTNS", (196, 196), 2204.5, "KG",
             {**BASE_LABELS, "from": "Shipped By", "to": "Shipped To", "weight": "Total Weight"},
             ("Meera Pillai", "+91 95355 18264", "meera@deltalane.example"), "Match", scanned=True),
    Shipment("F06", "HW-30094", "Hillwood Chemicals Ltd", "Meridian Freight Warehouse", "27 April 2026", "2026-04-27",
             "60 DRUMS", "60 PALLETS", (60, 60), 12000.0, "KG",
             {**BASE_LABELS, "ref": "Proforma Ref", "ref_packing": "Proforma Ref", "total": "Consignment Total"},
             ("Arjun Nair", "+91 98860 73149", "arjun@hillwood.example"), "Mismatch"),
    Shipment("F07", "ZN/2026/1044", "Zenith Forge", "Meridian Freight Warehouse", "2026/04/29", "2026-04-29",
             "48 CASES", "48 CASES", (48, 48), 760.5, "KG",
             {**BASE_LABELS, "from": "Supplier", "to": "Ship-To Party", "total": "No. of Cases"},
             ("Divya Rao", "+91 91080 26457", "divya@zenithforge.example"), "Match", font="Courier"),
]
RECEIPTS = {"F01": ("Harish Gowda", "9845001122", "Anita Desai"), "F05": ("Imran Khan", "8123409876", "Suresh Pawar")}
GOODS = ["Copper wire", "Printed labels", "Steel brackets", "Cotton yarn", "Ceramic tiles", "Rubber seals"]


def _page(path: Path, shipment: Shipment) -> tuple[canvas.Canvas, float, float]:
    size = landscape(A4) if shipment.page == "landscape" else A4
    c = canvas.Canvas(str(path), pagesize=size)
    c.setTitle("Synthetic final set document")
    return c, size[0], size[1]


def _rows(printed_total: str) -> list[tuple[str, str]]:
    number = int(printed_total.split()[0].replace(",", ""))
    unit = printed_total.split()[1]
    first = number // 3 + random.randint(1, 4)
    return [(random.choice(GOODS), f"{first:,} {unit}"), (random.choice(GOODS), f"{number - first:,} {unit}")]


def document(path: Path, s: Shipment, kind: str) -> None:
    invoice = kind == "invoice"
    labels = s.labels
    total = s.invoice_total if invoice else s.packing_total
    c, width, height = _page(path, s)
    bold = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[s.font]
    c.setFont(bold, 18)
    c.drawString(45, height - 55, labels["title_invoice"] if invoice else labels["title_packing"])
    c.setFont(s.font, 11)
    y = height - 85
    lines = [f"{labels['ref'] if invoice else labels['ref_packing']}: {s.reference}", f"{labels['date']}: {s.printed_date}",
             f"{labels['from']}: {s.shipper}", f"{labels['to']}: {s.receiver}"]
    if invoice:
        lines += [f"Contact: {s.contact[0]}", f"Phone: {s.contact[1]}", f"Email: {s.contact[2]}"]
    if s.extra_line:
        lines.append(s.extra_line)
    for line in lines:
        c.drawString(45, y, line)
        y -= 16
    y -= 12
    c.setFont(bold, 11)
    c.drawString(45, y, "Description")
    c.drawString(330, y, "Qty")
    c.line(45, y - 4, width - 45, y - 4)
    c.setFont(s.font, 11)
    for description, quantity in _rows(total):
        y -= 18
        c.drawString(45, y, description)
        c.drawString(330, y, quantity)
    y -= 30
    c.setFont(bold, 12)
    c.drawString(45, y, f"{labels['total']}: {total}")
    c.drawString(45, y - 20, f"{labels['weight']}: {s.weight:,.2f} {s.weight_unit}")
    c.setFont(s.font, 9)
    c.drawString(45, 40, "Synthetic test document.")
    c.save()


def receipt(path: Path, s: Shipment) -> None:
    driver, phone, clerk = RECEIPTS[s.sid]
    c, width, height = _page(path, s)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(45, height - 55, "DELIVERY RECEIPT")
    c.setFont("Helvetica", 11)
    y = height - 85
    for line in (f"Shipment Ref: {s.reference}", f"Delivered: {s.printed_date}", f"From: {s.shipper}", f"To: {s.receiver}",
                 f"Received Qty: {s.packing_total}", f"Driver: {driver}  Mobile: {phone}"):
        c.drawString(45, y, line)
        y -= 18
    c.drawString(45, 150, f"Received by: {clerk}")
    c.drawString(45, 125, "Signature:")
    path_line = c.beginPath()
    path_line.moveTo(110, 122)
    for k in range(7):
        path_line.curveTo(118 + k * 14, 138, 124 + k * 14, 108, 132 + k * 14, 124)
    c.drawPath(path_line)
    c.save()


def scan(pdf: Path) -> Path:
    """Turn a PDF into a slightly crooked, soft photo of a page."""
    image = convert_from_path(str(pdf), dpi=220)[0].convert("L")
    image = image.rotate(0.7, expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(0.5))
    png = pdf.with_suffix(".png")
    image.save(png)
    pdf.unlink()
    return png


def truth(s: Shipment, kind: str, index: int) -> list:
    weight = None
    if kind != "delivery_receipt":
        weight = round(s.weight * LB_TO_KG, 2) if s.weight_unit.startswith("LB") else s.weight
    return [kind, s.reference, s.shipper, s.receiver, s.iso_date, s.expected_quantity[index], weight]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        if old.is_file():
            old.unlink()
    sheet, cases = [], []
    for s in SHIPMENTS:
        names = []
        for short, kind, index in (("invoice", "commercial_invoice", 0), ("packing", "packing_list", 1)):
            path = OUT / f"{s.sid}_{short}.pdf"
            document(path, s, short)
            if s.scanned:
                path = scan(path)
            names.append(path.name)
            sheet.append([path.name, *truth(s, kind, index)])
        cases.append((f"{s.sid}-pair", names[0], names[1], s.expected))
        if s.sid in RECEIPTS:
            path = OUT / f"{s.sid}_receipt.pdf"
            receipt(path, s)
            sheet.append([path.name, *truth(s, "delivery_receipt", 1)])
            cases.append((f"{s.sid}-receipt", path.name, "", "Not applicable"))
    cases.append(("F03-invoice-only", "F03_invoice.pdf", "", "Incomplete"))
    with open(OUT / "final_sheet.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["file", "expected_document_type", *FIELDS])
        writer.writerows(sheet)
    with open(OUT / "final_cases.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["case", "file", "file2", "expected_status"])
        writer.writerows(cases)
    print(f"Wrote {len(sheet)} documents and {len(cases)} rule cases to {OUT}")


if __name__ == "__main__":
    main()
