import pytest
from PIL import Image

from app.core.errors import PipelineError
from app.domains.meridian.schemas import MeridianFields
from app.domains.meridian.domain import DOMAIN
from app.pipeline import pii, vision
from app.pipeline.ocr import OCRResult, Word
from app.pipeline.pii import PlaceholderVault, Span


def _ocr(lines, size=(1000, 1000)):
    """lines: (text, top). Each string becomes one OCR line."""
    words, parts, cursor = [], [], 0
    for n, (text, top) in enumerate(lines):
        for token in text.split():
            words.append(Word(0, token, 10, top, 50, 20, 40.0, cursor, cursor + len(token), (1, 1, n)))
            parts.append(token)
            cursor += len(token) + 1
    return OCRResult(" ".join(parts), words, [Image.new("RGB", size, "white")], 40.0)


def _is_black(img, xy):
    return img.getpixel(xy) == (0, 0, 0)


@pytest.mark.parametrize("name", ["John Mills", "Priya Co", "Asha Global", "Sam Works", "Ravi Motors"])
def test_surnames_are_not_company_words(name):
    assert not pii._looks_like_company_or_label(name)


@pytest.mark.parametrize("name", ["Kestrel Exports", "Meridian Freight Warehouse", "Bluefin Textiles Pvt Ltd",
                                  "Saffron Agro Traders", "Northwind Electronics Ltd", "Coral Ceramics Industries"])
def test_sample_companies_stay_visible(name):
    assert pii._looks_like_company_or_label(name)


def test_personal_gstin_is_caught_but_a_company_gstin_is_not():
    assert pii.residual_types("GSTIN 29ABCPE1234F1Z5") == {"IN_GSTIN_PERSONAL"}
    assert pii.residual_types("GSTIN 29ABCHE1234F1Z5") == {"IN_GSTIN_PERSONAL"}
    assert pii.residual_types("GSTIN 29ABCCE1234F1Z5") == set()


def test_residual_scan_finds_shapes_and_ignores_placeholders():
    assert pii.residual_types("Call 98450 12345") == {"IN_MOBILE"}
    assert pii.residual_types("a.b@example.com") == {"EMAIL_ADDRESS"}
    assert pii.residual_types("ABCPE1234F") == {"IN_PAN"}
    assert pii.residual_types("id 2345 6789 0123") == {"IN_AADHAAR"}
    assert pii.residual_types("<PERSON_1> <PHONE_1> MF-88421 120 CTNS 860.5 kg 2026-02-02") == set()


def test_unreadable_type_blocks_the_vision_call():
    with pytest.raises(PipelineError) as e:
        vision.redact_pages(_ocr([("smudged title", 50), ("Total 120", 500), ("scribble", 950)]), [], DOMAIN)
    assert e.value.error_class == "manual_review_unknown_type"


def test_invoice_mention_in_a_receipt_body_is_not_a_title():
    ocr = _ocr([("smudged title", 50), ("Commercial Invoice MF-88421", 500)])
    with pytest.raises(PipelineError):
        vision.redact_pages(ocr, [], DOMAIN)


def test_receipt_gets_signature_band():
    out = vision.redact_pages(_ocr([("Delivery Receipt", 50), ("Total 120", 500)]), [], DOMAIN)
    assert _is_black(out[0], (500, 950))


def test_titled_invoice_keeps_its_totals():
    out = vision.redact_pages(_ocr([("Commercial Invoice", 50), ("Total 120", 500)]), [], DOMAIN)
    assert not _is_black(out[0], (500, 950))


def test_contact_line_redacted_by_ocr_line_not_word_height():
    ocr = _ocr([("Commercial Invoice", 50), ("Phone: 12345", 500)])
    value = ocr.words[-1]
    value.height, value.top = 37, 493  # a taller word that top // height would put on another line
    out = vision.redact_pages(ocr, [], DOMAIN)
    assert _is_black(out[0], (value.left + 5, value.top + 5))


def test_flagged_word_is_painted_out():
    ocr = _ocr([("Commercial Invoice", 50), ("Priya", 300)])
    word = ocr.words[-1]
    out = vision.redact_pages(ocr, [Span(word.start, word.end, "PERSON", 0.9)], DOMAIN)
    assert _is_black(out[0], (word.left + 5, word.top + 5))


def test_scrub_masks_shapes_and_keeps_placeholders(monkeypatch):
    monkeypatch.setattr(pii, "detect", lambda text: [])
    fields = MeridianFields(invoice_number="98450 12345", shipper_name="<PERSON_1>", receiver_name="Kestrel Exports")
    assert pii.scrub_fields(fields, PlaceholderVault(), DOMAIN.reference_fields, DOMAIN.party_fields) == 1
    assert fields.invoice_number == "<PHONE_1>"
    assert fields.shipper_name == "<PERSON_1>"
    assert fields.receiver_name == "Kestrel Exports"


def test_validation_errors_do_not_echo_values():
    from pydantic import ValidationError

    from app.domains.meridian.schemas import LLMExtraction

    with pytest.raises(ValidationError) as e:
        LLMExtraction.model_validate({"document_type": "invoice", "fields": "Priya Raman"})
    assert "Priya" not in str(e.value)


def test_presidio_masks_surname_that_is_a_company_word():
    pytest.importorskip("presidio_analyzer")
    masked, _ = pii.mask("Shipper: Kestrel Exports\nAttn: John Mills\n", PlaceholderVault())
    assert "Mills" not in masked and "John" not in masked
    assert "Kestrel Exports" in masked


def test_presidio_masks_email_with_an_unusual_domain():
    pytest.importorskip("presidio_analyzer")
    masked, _ = pii.mask("Email: priya.raman@kestrel-exports.example\n", PlaceholderVault())
    assert "priya.raman" not in masked
    assert pii.residual_types(masked) == set()


def test_multi_line_entity_keeps_the_label_on_the_next_line(monkeypatch):
    text = "Plot 7, Hosur\nConsignee: Meridian Freight Warehouse\n"

    class FakeAnalyzer:
        def analyze(self, **kwargs):
            class Result:
                entity_type, score = "PERSON", 0.85
                start = text.index("Hosur")
                end = text.index("Consignee") + len("Consignee")
            return [Result()]

    monkeypatch.setattr(pii, "_analyzer", lambda: FakeAnalyzer())
    masked = pii.apply_mask(text, pii.detect(text), PlaceholderVault())
    assert masked == "Plot 7, <PERSON_1>\nConsignee: Meridian Freight Warehouse\n"


def _fake_analyzer(monkeypatch, text, word, entity):
    class Analyzer:
        def analyze(self, **kwargs):
            class Result:
                entity_type, score = entity, 0.85
                start = text.index(word)
                end = start + len(word)
            return [Result()]

    monkeypatch.setattr(pii, "_analyzer", lambda: Analyzer())


def test_place_after_a_party_label_is_kept_as_the_company(monkeypatch):
    text = "Exporter: Tarang Ship To: Meridian Freight Warehouse\n"
    _fake_analyzer(monkeypatch, text, "Tarang", "LOCATION")
    assert pii.detect(text) == []


def test_person_after_a_party_label_is_still_masked(monkeypatch):
    text = "Exporter: Asha Rao\n"
    _fake_analyzer(monkeypatch, text, "Asha Rao", "PERSON")
    assert [s.entity_type for s in pii.detect(text)] == ["PERSON"]


def test_place_elsewhere_is_still_masked(monkeypatch):
    text = "Attention: Chennai\n"
    _fake_analyzer(monkeypatch, text, "Chennai", "LOCATION")
    assert [s.entity_type for s in pii.detect(text)] == ["LOCATION"]


def test_scrub_keeps_a_company_that_reads_as_a_place(monkeypatch):
    monkeypatch.setattr(pii, "detect", lambda text: [Span(0, len(text), "LOCATION", 0.85)])
    fields = MeridianFields(shipper_name="Tarang")
    assert pii.scrub_fields(fields, PlaceholderVault(), DOMAIN.reference_fields, DOMAIN.party_fields) == 0
    assert fields.shipper_name == "Tarang"


def test_scrub_catches_a_name_the_model_returned():
    pytest.importorskip("presidio_analyzer")
    fields = MeridianFields(shipper_name="Priya Raman", receiver_name="Meridian Freight Warehouse")
    assert pii.scrub_fields(fields, PlaceholderVault(), DOMAIN.reference_fields, DOMAIN.party_fields) == 1
    assert "Priya" not in fields.shipper_name
    assert fields.receiver_name == "Meridian Freight Warehouse"
