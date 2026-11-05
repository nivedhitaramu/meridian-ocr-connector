import pytest

pytest.importorskip("presidio_analyzer")

from app.pipeline.pii import PlaceholderVault  # noqa: E402


def test_personal_gstin_is_masked_and_a_company_gstin_stays():
    from app.pipeline.pii import mask, residual_types

    v = PlaceholderVault()
    masked, _ = mask("GSTIN: 29ABCPE1234F1Z5\nSupplier GSTIN: 29AAACK1234F1Z9\nTotal Quantity: 120 CTNS", v)
    assert "29ABCPE1234F1Z5" not in masked and "ABCPE1234F" not in masked
    assert "29AAACK1234F1Z9" in masked
    assert v.entity_counts["IN_GSTIN_PERSONAL"] == 1
    assert residual_types(masked) == set()


def test_a_company_word_after_a_name_keeps_the_company_and_a_person_stays_masked():
    from app.pipeline.pii import mask

    v = PlaceholderVault()
    masked, _ = mask("Vendor: Sagar Bulk Traders\nContact: Lakshmi Menon\nReference Invoice: ZN/2026/1044\nID: ABCPE1234F", v)
    assert "Sagar Bulk Traders" in masked and "ZN/2026/1044" in masked
    assert "Lakshmi" not in masked and "ABCPE1234F" not in masked


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
