import pytest

pytest.importorskip("presidio_analyzer")

from app.pipeline.pii import PlaceholderVault  # noqa: E402


def test_presidio_masks_contacts_keeps_companies():
    from app.pipeline.pii import mask

    text = ("COMMERCIAL INVOICE\nShipper: Kestrel Exports\nAttn: Priya Raman\n"
            "Phone: +91 98450 12345\nEmail: priya.raman@kestrel-exports.example\n"
            "Consignee: Meridian Freight Warehouse\nTotal Quantity: 120 CTNS\nSignature: ~~~~")
    v = PlaceholderVault()
    masked, _ = mask(text, v)
    for secret in ("Priya", "98450", "priya.raman@", "~~~~"):
        assert secret not in masked
    for keep in ("Kestrel Exports", "Meridian Freight Warehouse", "120 CTNS"):
        assert keep in masked
