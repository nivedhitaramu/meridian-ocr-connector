import pytest

from app.pii import PlaceholderVault, Span, apply_mask, resolve_overlaps


def test_same_person_two_spellings_one_token():
    v = PlaceholderVault()
    assert v.token_for("PERSON", "Ravi Menon") == "<PERSON_1>"
    assert v.token_for("PERSON", "RAVI  MENON") == "<PERSON_1>"
    assert v.token_for("PERSON", "Ravi M.") == "<PERSON_2>"  # nickname matching is out of scope


def test_phone_types_share_one_namespace():
    v = PlaceholderVault()
    assert v.token_for("IN_MOBILE", "98450 12345") == "<PHONE_1>"
    assert v.token_for("PHONE_NUMBER", "98450  12345") == "<PHONE_1>"


def test_apply_mask_and_restore():
    text = "Attn: Priya Raman Phone: +91 98450 12345"
    spans = [Span(6, 17, "PERSON", 0.9), Span(25, len(text), "IN_MOBILE", 0.8)]
    v = PlaceholderVault()
    masked = apply_mask(text, spans, v)
    assert masked == "Attn: <PERSON_1> Phone: <PHONE_1>"
    assert "Priya" not in masked
    assert v.restore(masked) == text


def test_overlaps_keep_best():
    kept = resolve_overlaps([Span(0, 10, "PERSON", 0.6), Span(2, 8, "LOCATION", 0.4), Span(12, 15, "EMAIL_ADDRESS", 1.0)])
    assert [(s.entity_type) for s in kept] == ["PERSON", "EMAIL_ADDRESS"]


def test_clear_forgets_everything():
    v = PlaceholderVault()
    v.token_for("PERSON", "Ravi Menon")
    v.clear()
    assert v.placeholder_count == 0
    assert v.restore("<PERSON_1>") == "<PERSON_1>"
