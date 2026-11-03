"""Generate a holdout set: synthetic documents the prompt and filters were never tuned on.

They differ from samples/ on purpose: new companies (some without words like "Ltd" or
"Exports"), new labels ("Exporter", "Ship To", "Total Packages"), a two-column header,
new reference formats and new quantities. All names, phones and emails are invented.

    python scripts/make_holdout.py
    python scripts/evaluate.py --sheet samples/holdout/holdout_sheet.csv --cases samples/holdout/holdout_cases.csv

Needs only reportlab, so it runs without Poppler. Outputs to samples/holdout/.
"""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples" / "holdout"
W, H = A4
LB_TO_KG = 0.45359237
random.seed(31)


@dataclass
class Party:
    company: str
    contact: str
    phone: str
    email: str
    address: str


# Two of these have no "company word", which is the case issue #9 is about.
EXPORTERS = [
    Party("Ashwood Mills", "Nandini Sharma", "+91 98201 55443", "nandini@ashwood.example", "41 Canal Street, Surat"),
    Party("Halden & Brook", "Karthik Subramanian", "+91 94440 18822", "karthik.s@haldenbrook.example", "9 Mount Road, Chennai"),
    Party("Velora Global Sourcing LLP", "Sneha Kulkarni", "+91 97300 66120", "sneha.k@velora.example", "Unit 5, MIDC Bhosari, Pune"),
    Party("Tarang", "Aditya Bose", "+91 90070 43219", "aditya@tarang.example", "17 Strand Road, Kolkata"),
]
CONSIGNEE = Party("Meridian Freight Warehouse", "Rekha Joshi", "+91 93222 98761", "inbound@meridianfreight.example",
                  "Gate 3, JNPT Logistics Park, Navi Mumbai")
DRIVERS = [("Manoj Yadav", "9988123456"), ("Salim Qureshi", "8877612345")]
CLERKS = ["Pooja Hegde", "Ramesh Iyengar"]

# id, ref, exporter, printed date, ISO date, invoice totals, packing totals, inv weight, pl weight, weight unit
SHIPMENTS = [
    ("H01", "INV/2026/0417", 0, "Mar 3, 2026", "2026-03-03", [(64, "CTNS")], [(64, "CTNS")], 498.0, 498.0, "KG"),
    ("H02", "HB-2026-118", 1, "2026/03/05", "2026-03-05", [(250, "PKGS")], [(205, "PKGS")], 1312.5, 1077.0, "KG"),
    ("H03", "VGS/EXP/2291", 2, "07-Mar-2026", "2026-03-07", [(2400, "PCS")], [(2400, "PCS")], 980.0, 980.0, "KG"),
    ("H04", "TR-55031", 3, "10.03.2026", "2026-03-10", [(36, "PALLETS")], [(36, "CTNS")], 6120.0, 6120.0, "KG"),
    ("H05", "INV/2026/0533", 0, "March 12, 2026", "2026-03-12", [(150, "CARTONS")], [(150, "CARTONS")], 2645.0, 2645.0, "LBS"),
    ("H06", "HB-2026-131", 1, "Mar 16, 2026", "2026-03-16", [(88, "CTNS")], [(88, "CTNS")], 702.0, 702.0, "KG"),
]


def _canvas(path: Path) -> canvas.Canvas:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Synthetic holdout document")
    c.setAuthor("synthetic")
    return c


def _two_column_header(c, title: str, ref_label: str, ref: str, date: str, exp: Party, contacts: bool) -> float:
    """Exporter on the left, consignee on the right: a layout the main samples never use."""
    c.setFont("Times-Bold", 22)
    c.drawCentredString(W / 2, H - 60, title)
    c.setFont("Times-Roman", 11)
    c.drawString(50, H - 92, f"{ref_label}: {ref}")
    c.drawRightString(W - 50, H - 92, f"Date: {date}")

    left = [f"Exporter: {exp.company}", exp.address]
    if contacts:
        left += [f"Attention: {exp.contact}", f"Tel: {exp.phone}", f"E-mail: {exp.email}"]
    right = [f"Ship To: {CONSIGNEE.company}", CONSIGNEE.address, f"Contact Person: {CONSIGNEE.contact}"]
    y0 = H - 130
    for i, line in enumerate(left):
        c.drawString(50, y0 - 16 * i, line)
    for i, line in enumerate(right):
        c.drawString(310, y0 - 16 * i, line)
    return y0 - 16 * max(len(left), len(right)) - 30


def _lines(total: int, unit: str) -> list[tuple[str, int, str]]:
    goods = ["Denim fabric rolls", "Brass fittings", "Basmati rice bags", "Leather wallets", "Glass jars", "Solar cables"]
    a = max(1, total // 2 - random.randint(0, 3))
    return [(random.choice(goods), a, unit), (random.choice(goods), total - a, unit)]


def _table(c, y: float, total: int, unit: str) -> float:
    c.setFont("Times-Bold", 11)
    for x, h in ((50, "Item"), (320, "Quantity"), (420, "Unit")):
        c.drawString(x, y, h)
    c.setFont("Times-Roman", 11)
    for desc, q, u in _lines(total, unit):
        y -= 18
        c.drawString(50, y, desc)
        c.drawString(320, y, f"{q:,}")
        c.drawString(420, y, u)
    return y - 32


def invoice(path: Path, s) -> None:
    sid, ref, ei, date, _, inv_t, _, w, _, wu = s
    c = _canvas(path)
    y = _two_column_header(c, "Commercial Invoice", "Bill No", ref, date, EXPORTERS[ei], True)
    q, u = inv_t[0]
    y = _table(c, y, q, u)
    c.setFont("Times-Bold", 12)
    c.drawString(50, y, f"Total Packages: {q:,} {u}")
    c.drawString(50, y - 20, f"Total Gross Wt: {w:,.1f} {wu}")
    c.setFont("Times-Roman", 10)
    c.drawString(50, 70, "Incoterms: CIF Nhava Sheva. Synthetic test document.")
    c.save()


def packing(path: Path, s) -> None:
    sid, ref, ei, date, _, _, pl_t, _, w, wu = s
    c = _canvas(path)
    y = _two_column_header(c, "Packing List", "Against Invoice", ref, date, EXPORTERS[ei], sid in {"H02", "H04"})
    q, u = pl_t[0]
    y = _table(c, y, q, u)
    c.setFont("Times-Bold", 12)
    c.drawString(50, y, f"Total Packages: {q:,} {u}")
    c.drawString(50, y - 20, f"Total Gross Wt: {w:,.1f} {wu}")
    c.save()


def receipt(path: Path, s, i: int) -> None:
    sid, ref, ei, date, _, _, pl_t, _, _, _ = s
    c = _canvas(path)
    c.setFont("Times-Bold", 22)
    c.drawCentredString(W / 2, H - 60, "Proof of Delivery")
    c.setFont("Times-Roman", 11)
    y = H - 100
    for line in (f"Consignment Ref: {ref}", f"Date: {date}", f"Exporter: {EXPORTERS[ei].company}",
                 f"Ship To: {CONSIGNEE.company}"):
        c.drawString(50, y, line)
        y -= 18
    q, u = pl_t[0]
    c.setFont("Times-Bold", 12)
    c.drawString(50, y - 10, f"Packages Received: {q:,} {u}")
    c.setFont("Times-Roman", 11)
    name, phone = DRIVERS[i % 2]
    c.drawString(50, y - 40, f"Driver: {name}   Mobile: {phone}")
    c.drawString(50, 150, f"Received by: {CLERKS[i % 2]}")
    c.drawString(50, 125, "Consignee Signature:")
    c.setLineWidth(1.3)
    p = c.beginPath()
    p.moveTo(170, 122)
    for k in range(8):
        p.curveTo(178 + k * 15, 138, 184 + k * 15, 108, 192 + k * 15, 125)
    c.drawPath(p)
    c.save()


def fields(s, kind: str) -> dict:
    sid, ref, ei, _, iso, inv_t, pl_t, w_inv, w_pl, wu = s
    if kind == "delivery_receipt":
        qty, weight = pl_t[0][0], None
    else:
        qty = (inv_t if kind == "commercial_invoice" else pl_t)[0][0]
        w = w_inv if kind == "commercial_invoice" else w_pl
        weight = round(w * LB_TO_KG, 2) if wu.startswith("LB") else w
    return {"invoice_number": ref, "shipper_name": EXPORTERS[ei].company, "receiver_name": CONSIGNEE.company,
            "shipment_date": iso, "total_quantity": qty, "total_weight_kg": weight}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        if old.is_file():
            old.unlink()

    truth, sheet = {}, []
    for s in SHIPMENTS:
        sid = s[0]
        for kind, short, fn in (("commercial_invoice", "invoice", invoice), ("packing_list", "packing", packing)):
            name = f"{sid}_{short}.pdf"
            fn(OUT / name, s)
            truth[name] = {"document_type": kind, "shipment": sid, "fields": fields(s, kind)}
            sheet.append(name)
    for i, sid in enumerate(("H01", "H02")):
        s = next(x for x in SHIPMENTS if x[0] == sid)
        name = f"{sid}_receipt.pdf"
        receipt(OUT / name, s, i)
        truth[name] = {"document_type": "delivery_receipt", "shipment": sid, "fields": fields(s, "delivery_receipt")}
        sheet.append(name)

    (OUT / "holdout_ground_truth.json").write_text(json.dumps(truth, indent=2))

    keys = ["invoice_number", "shipper_name", "receiver_name", "shipment_date", "total_quantity", "total_weight_kg"]
    with open(OUT / "holdout_sheet.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "expected_document_type", *keys])
        for name in sheet:
            w.writerow([name, truth[name]["document_type"], *[truth[name]["fields"][k] for k in keys]])

    cases = [
        ("H01-pair", "H01_invoice.pdf", "H01_packing.pdf", "Match"),           # 64 vs 64 cartons
        ("H02-pair", "H02_invoice.pdf", "H02_packing.pdf", "Mismatch"),        # 250 vs 205, digits swapped
        ("H03-pair", "H03_invoice.pdf", "H03_packing.pdf", "Match"),           # 2,400 pieces
        ("H04-pair", "H04_invoice.pdf", "H04_packing.pdf", "Mismatch"),        # pallets vs cartons
        ("H05-pair", "H05_invoice.pdf", "H05_packing.pdf", "Match"),           # weight in LBS
        ("H06-pair", "H06_invoice.pdf", "H06_packing.pdf", "Match"),
        ("H01-receipt", "H01_receipt.pdf", "", "Not applicable"),
        ("H03-invoice-only", "H03_invoice.pdf", "", "Incomplete"),
    ]
    with open(OUT / "holdout_cases.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "file", "file2", "expected_status"])
        w.writerows(cases)

    print(f"Wrote {len(truth)} holdout documents and {len(cases)} rule cases to {OUT}")


if __name__ == "__main__":
    main()
