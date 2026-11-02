"""Generate synthetic Meridian Freight documents + ground truth + the 20-document test sheet.

All companies, people, phone numbers and emails are invented. Run:
    python scripts/make_samples.py
Outputs to samples/ : PDFs, PNG/JPEG "scans", ground_truth.json, test_sheet.csv, test_cases.csv
"""
from __future__ import annotations

import csv
import json
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
random.seed(7)
W, H = A4


@dataclass
class Party:
    company: str
    contact: str
    phone: str
    email: str
    address: str


SHIPPERS = [
    Party("Kestrel Exports", "Priya Raman", "+91 98450 12345", "priya.raman@kestrel-exports.example", "14 Harbour Road, Kochi"),
    Party("Bluefin Textiles Pvt Ltd", "Arjun Nair", "+91 99001 23456", "arjun.nair@bluefin.example", "Plot 7, SIPCOT, Hosur"),
    Party("Saffron Agro Traders", "Meena Iyer", "+91 90031 77889", "meena@saffronagro.example", "22 Market Lane, Nashik"),
    Party("Northwind Electronics Ltd", "Rohan Das", "+91 87654 32109", "rohan.das@northwind.example", "B-11 Okhla Phase 2, New Delhi"),
    Party("Coral Ceramics Industries", "Kavya Menon", "+91 70123 45678", "kavya.menon@coralceramics.example", "Morbi Road, Rajkot"),
]
RECEIVER = Party("Meridian Freight Warehouse", "Anil Kapoor", "+91 93222 41187", "receiving@meridianfreight.example",
                 "Gate 3, JNPT Logistics Park, Navi Mumbai")
DRIVERS = ["Suresh Kumar", "Imran Shaikh", "Gopal Reddy", "Vikram Singh"]
DRIVER_PHONES = ["9876543210", "9123456780", "8899776655", "7766554433"]
RECEIVING_CLERKS = ["Deepa Pillai", "Farhan Ali", "Lakshmi Rao"]

# id, invoice no, shipper idx, date (printed), ISO date, invoice totals, packing totals, weight inv, weight pl, weight unit, render
SHIPMENTS = [
    ("S01", "MF-10040", 0, "12 Jan 2026", "2026-01-12", [(40, "CTNS")], [(40, "CTNS")], 312.0, 312.0, "KG", "pdf"),
    ("S02", "MF-88421", 0, "2026-02-02", "2026-02-02", [(120, "CTNS")], [(120, "CTNS")], 860.5, 860.5, "KG", "pdf"),
    ("S03", "MF-31200", 1, "05/02/2026", "2026-02-05", [(1200, "PCS")], [(50, "CARTONS"), (1200, "PCS")], 1450.0, 1450.0, "KG", "pdf"),
    ("S04", "MF-41180", 2, "09 Feb 2026", "2026-02-09", [(120, "CTNS")], [(118, "CTNS")], 905.0, 890.2, "KG", "pdf"),
    ("S05", "MF-51440", 3, "11.02.2026", "2026-02-11", [(1440, "PCS")], [(120, "CTNS")], 640.0, 640.0, "KG", "pdf"),
    ("S06", "MF-60120", 4, "February 14, 2026", "2026-02-14", [(120, "CTNS")], [(120, "CTNS")], 1897.0, 1897.0, "LB", "pdf"),
    ("S07", "MF-70075", 1, "16 Feb 2026", "2026-02-16", [(75, "CTNS")], [(75, "CTNS")], 520.0, 515.5, "KG", "pdf"),
    ("S08", "MF-80300", 2, "18-02-2026", "2026-02-18", [(300, "PCS")], [(310, "PCS")], 210.0, 214.0, "KG", "pdf"),
    ("S09", "MF-90018", 3, "20 Feb 2026", "2026-02-20", [(18, "PALLETS")], [(18, "PALLETS")], 7420.0, 7420.0, "KG", "pdf"),
    ("S10", "MF-10250", 4, "23 Feb 2026", "2026-02-23", [(250, "CTNS")], [(250, "CTNS")], 2210.0, 2210.0, "KG", "png"),
    ("S11", "MF-11500", 0, "25 Feb 2026", "2026-02-25", [(500, "CTNS")], [(50, "CTNS")], 3980.0, 410.0, "KG", "jpg"),
    ("S12", "MF-12120", 1, "27 Feb 2026", "2026-02-27", [(1200, "CTNS")], [(1200, "CTNS")], 9100.0, 9100.0, "KG", "pdf"),
    ("S13", "MF-13096", 2, "02 Mar 2026", "2026-03-02", [(96, "BOXES")], [(96, "BOXES")], 288.0, 288.0, "KG", "png"),
]
LB_TO_KG = 0.45359237


def _canvas(path: Path) -> canvas.Canvas:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Synthetic document")
    c.setAuthor("synthetic")
    return c


def _header(c, title: str, ref_label: str, ref: str, date: str, shipper: Party, show_contact: bool):
    y = H - 60
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, y, title)
    c.setFont("Helvetica", 11)
    y -= 34
    c.drawString(50, y, f"{ref_label}: {ref}")
    y -= 18
    c.drawString(50, y, f"Date: {date}")
    y -= 30
    c.drawString(50, y, f"Shipper: {shipper.company}")
    y -= 16
    c.drawString(50, y, shipper.address)
    if show_contact:
        y -= 16
        c.drawString(50, y, f"Attn: {shipper.contact}")
        y -= 16
        c.drawString(50, y, f"Phone: {shipper.phone}")
        y -= 16
        c.drawString(50, y, f"Email: {shipper.email}")
    y -= 28
    c.drawString(50, y, f"Consignee: {RECEIVER.company}")
    y -= 16
    c.drawString(50, y, RECEIVER.address)
    y -= 16
    c.drawString(50, y, f"Contact: {RECEIVER.contact}")
    return y - 34


def _lines(total: int, unit: str, n: int = 3) -> list[tuple[str, int, str]]:
    goods = ["Cotton T-shirts", "Ceramic tiles", "Spice jars", "LED panels", "Steel fasteners", "Packaged tea"]
    parts, left = [], total
    for i in range(n - 1):
        q = max(1, total // n + random.randint(-2, 2)) if total >= n * 3 else 0
        if q:
            parts.append(q)
            left -= q
    parts.append(left)
    return [(random.choice(goods), q, unit) for q in parts if q > 0]


def _table(c, y: float, total_q: int, unit: str):
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(380, y, "Unit")
    c.setFont("Helvetica", 11)
    for desc, q, u in _lines(total_q, unit):
        y -= 18
        c.drawString(50, y, desc)
        c.drawString(300, y, f"{q:,}")
        c.drawString(380, y, u)
    return y - 30


def _weight(value: float, unit: str) -> str:
    return f"{value:,.1f} {unit}"


def invoice(path: Path, s) -> None:
    sid, ref, si, date, _, inv_totals, _, w_inv, _, wunit, _ = s
    c = _canvas(path)
    y = _header(c, "COMMERCIAL INVOICE", "Invoice No", ref, date, SHIPPERS[si], True)
    q, u = inv_totals[0]
    y = _table(c, y, q, u)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total Quantity: {q:,} {u}")
    c.drawString(50, y - 20, f"Gross Weight: {_weight(w_inv, wunit)}")
    c.setFont("Helvetica", 10)
    c.drawString(50, 80, "Terms: FOB Kochi. Payment 30 days. This is a synthetic test document.")
    c.save()


def packing(path: Path, s) -> None:
    sid, ref, si, date, _, _, pl_totals, _, w_pl, wunit, _ = s
    c = _canvas(path)
    y = _header(c, "PACKING LIST", "Invoice Ref", ref, date, SHIPPERS[si], sid in {"S02", "S04", "S06"})
    q, u = pl_totals[-1] if len(pl_totals) > 1 else pl_totals[0]
    y = _table(c, y, q, u)
    c.setFont("Helvetica-Bold", 12)
    if len(pl_totals) > 1:  # prints two totals on purpose (edge case)
        for i, (tq, tu) in enumerate(pl_totals):
            label = "Cartons" if tu.upper().startswith("CART") else "Pieces"
            c.drawString(50, y - 20 * i, f"Total {label}: {tq:,}")
        y -= 20 * len(pl_totals)
    else:
        c.drawString(50, y, f"Total Quantity: {q:,} {u}")
        y -= 20
    c.drawString(50, y, f"Gross Weight: {_weight(w_pl, wunit)}")
    c.save()


def receipt(path: Path, s, idx: int) -> None:
    sid, ref, si, date, _, _, pl_totals, _, _, _, _ = s
    c = _canvas(path)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, H - 60, "DELIVERY RECEIPT")
    c.setFont("Helvetica", 11)
    y = H - 94
    for line in (f"Shipment Ref: {ref}", f"Delivery Date: {date}", f"Shipper: {SHIPPERS[si].company}",
                 f"Consignee: {RECEIVER.company}", RECEIVER.address):
        c.drawString(50, y, line)
        y -= 18
    q, u = pl_totals[0]
    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total Received: {q:,} {u}")
    c.setFont("Helvetica", 11)
    y -= 30
    c.drawString(50, y, f"Driver: {DRIVERS[idx % 4]}   Mobile: {DRIVER_PHONES[idx % 4]}")
    y -= 18
    c.drawString(50, y, "Condition on arrival: Good, seals intact.")
    # signature block in the bottom band
    c.drawString(50, 150, f"Received by: {RECEIVING_CLERKS[idx % 3]}")
    c.drawString(50, 125, "Signature:")
    c.setLineWidth(1.4)
    p = c.beginPath()
    p.moveTo(130, 122)
    for k in range(10):
        p.curveTo(140 + k * 14, 140, 146 + k * 14, 105, 154 + k * 14, 124)
    c.drawPath(p)
    c.line(125, 115, 330, 115)
    c.save()


def faint_receipt(path: Path) -> None:
    """A scan so faint OCR fails: exercises the fallback / manual-review path."""
    tmp = OUT / "_tmp_faint.pdf"
    receipt(tmp, SHIPMENTS[0], 3)
    img = _rasterize(tmp)
    tmp.unlink()
    img = ImageEnhance.Contrast(img).enhance(0.08).filter(ImageFilter.GaussianBlur(3))
    img.save(path)


def _rasterize(pdf: Path, dpi: int = 150) -> Image.Image:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", str(pdf), f"{d}/p"], check=True)
        return Image.open(f"{d}/p.png").convert("RGB")


def to_scan(pdf: Path, target: Path) -> None:
    img = _rasterize(pdf, 200)
    img = img.rotate(random.uniform(-1.2, 1.2), expand=True, fillcolor="white")
    img = ImageEnhance.Contrast(img).enhance(0.85).filter(ImageFilter.GaussianBlur(0.4))
    if target.suffix == ".jpg":
        img.save(target, quality=82)
    else:
        img.save(target)
    pdf.unlink()


def gt_fields(s, kind: str) -> dict:
    sid, ref, si, _, iso, inv_t, pl_t, w_inv, w_pl, wunit, _ = s
    totals = inv_t if kind == "commercial_invoice" else pl_t
    if kind == "delivery_receipt":
        qty, weight = pl_t[0][0], None
    else:
        shipping = [t for t in totals if not t[1].upper().startswith(("PC", "PIECE"))]
        qty = (shipping or totals)[0][0]
        w = w_inv if kind == "commercial_invoice" else w_pl
        weight = round(w * LB_TO_KG, 2) if wunit == "LB" else w
    return {
        "invoice_number": ref, "shipper_name": SHIPPERS[si].company, "receiver_name": RECEIVER.company,
        "shipment_date": iso, "total_quantity": qty, "total_weight_kg": weight,
    }


def expected_status(s) -> str:
    _, _, _, _, _, inv_t, pl_t, *_ = s
    inv_units = {u.upper().rstrip("S"): q for q, u in inv_t}
    pl_units = {u.upper().rstrip("S"): q for q, u in pl_t}
    norm = lambda u: {"CTN": "CARTON", "CARTON": "CARTON", "PC": "PIECE", "PIECE": "PIECE"}.get(u, u)
    inv_units = {norm(k): v for k, v in inv_units.items()}
    pl_units = {norm(k): v for k, v in pl_units.items()}
    common = set(inv_units) & set(pl_units)
    if not common:
        return "Mismatch"
    u = common.pop()
    return "Match" if inv_units[u] == pl_units[u] else "Mismatch"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*"):
        if old.is_file():
            old.unlink()
    truth: dict[str, dict] = {}

    for idx, s in enumerate(SHIPMENTS):
        sid, render = s[0], s[-1]
        for kind, fn in (("commercial_invoice", invoice), ("packing_list", packing), ("delivery_receipt", receipt)):
            short = {"commercial_invoice": "invoice", "packing_list": "packing", "delivery_receipt": "receipt"}[kind]
            pdf = OUT / f"{sid}_{short}.pdf"
            fn(pdf, s) if kind != "delivery_receipt" else fn(pdf, s, idx)
            name = pdf.name
            if render in ("png", "jpg"):
                target = pdf.with_suffix(f".{render}")
                to_scan(pdf, target)
                name = target.name
            truth[name] = {"document_type": kind, "shipment": sid, "fields": gt_fields(s, kind)}

    faint_receipt(OUT / "S14_receipt_faint.png")
    truth["S14_receipt_faint.png"] = {"document_type": "delivery_receipt", "shipment": "S14",
                                      "fields": gt_fields(SHIPMENTS[0], "delivery_receipt"), "expect_error": True}
    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2))

    def f(sid, short):
        return next(n for n in truth if n.startswith(f"{sid}_{short}"))

    # ---- 20-document test sheet ---------------------------------------
    pair_ids = ["S01", "S02", "S03", "S04", "S05", "S06", "S08", "S11"]
    sheet_docs = [f(s, k) for s in pair_ids for k in ("invoice", "packing")]
    sheet_docs += [f("S02", "receipt"), f("S04", "receipt"), f("S10", "receipt"), f("S10", "invoice")]
    assert len(sheet_docs) == 20

    with open(OUT / "test_sheet.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "expected_document_type", "invoice_number", "shipper_name", "receiver_name",
                    "shipment_date", "total_quantity", "total_weight_kg"])
        for name in sheet_docs:
            t = truth[name]
            w.writerow([name, t["document_type"], *[t["fields"][k] for k in
                        ("invoice_number", "shipper_name", "receiver_name", "shipment_date", "total_quantity", "total_weight_kg")]])

    by_id = {s[0]: s for s in SHIPMENTS}
    with open(OUT / "test_cases.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "file", "file2", "expected_status"])
        for sid in pair_ids:
            w.writerow([f"{sid}-pair", f(sid, "invoice"), f(sid, "packing"), expected_status(by_id[sid])])
        for sid in ("S02", "S04", "S10"):
            w.writerow([f"{sid}-receipt", f(sid, "receipt"), "", "Not applicable"])
        w.writerow(["S10-invoice-only", f("S10", "invoice"), "", "Incomplete"])

    print(f"Wrote {len(truth)} documents to {OUT}")


if __name__ == "__main__":
    main()
