"""Build synthetic .eml packets for the stretch goal: python scripts/make_eml.py"""
from email.message import EmailMessage
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
MIME = {".pdf": ("application", "pdf"), ".png": ("image", "png"), ".jpg": ("image", "jpeg")}


def build(name: str, files: list[str]) -> None:
    msg = EmailMessage()
    msg["From"] = "dispatch@kestrel-exports.example"
    msg["To"] = "receiving@meridianfreight.example"
    msg["Subject"] = f"Shipment documents ({name})"
    msg.set_content("Please find the shipment documents attached. Synthetic test email.")
    for f in files:
        p = SAMPLES / f
        maintype, subtype = MIME[p.suffix]
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
    (SAMPLES / f"{name}.eml").write_bytes(bytes(msg))


if __name__ == "__main__":
    build("packet_S02_match", ["S02_invoice.pdf", "S02_packing.pdf", "S02_receipt.pdf"])
    build("packet_S04_mismatch", ["S04_invoice.pdf", "S04_packing.pdf"])
    print("Wrote 2 .eml packets to samples/")
