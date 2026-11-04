"""Vision fallback. Only a redacted image ever leaves the machine.

If OCR found no word boxes we cannot know where the personal data is, so we refuse
to send the raw scan anywhere and return a manual-review error instead.
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

from ..core.errors import PipelineError
from .ocr import OCRResult
from .pii import Span
from ..domains.base import Domain

PAD_PX = 6
SIGNATURE_BAND = 0.18  # bottom 18% of a delivery receipt page
_CONTACT_LINE = re.compile(r"contact|attn|attention|phone|mobile|tel|email|e-mail|signature|signed",
                           re.IGNORECASE)
TITLE_REGION = 0.25  # top 25% of the first page


def _has_unsigned_title(ocr: OCRResult, domain: Domain) -> bool:
    """Only a title counts: a signed document can mention an unsigned one in its body."""
    cutoff = ocr.images[0].size[1] * TITLE_REGION
    return bool(domain.unsigned_title.search(" ".join(w.text for w in ocr.words if w.page == 0 and w.top < cutoff)))


def signature_band_spans(ocr: OCRResult, domain: Domain) -> list[Span]:
    """Text-path twin of the image band: on a delivery receipt, everything OCR read in the
    bottom band (signature, scribble misread as letters, 'Received by') becomes one SIGNATURE span
    per page, so it never reaches the prompt even when 'Signature:' itself is misread."""
    if not domain.signed_document.search(ocr.text):
        return []
    spans = []
    for page_no, img in enumerate(ocr.images):
        cutoff = img.size[1] * (1 - SIGNATURE_BAND)
        band = [w for w in ocr.words if w.page == page_no and w.top + w.height > cutoff]
        if band:
            spans.append(Span(min(w.start for w in band), max(w.end for w in band), "SIGNATURE", 1.0))
    return spans


def redact_pages(ocr: OCRResult, spans: list[Span], domain: Domain) -> list[Image.Image]:
    if not ocr.words:
        raise PipelineError("manual_review_no_boxes")

    # Fallback runs because OCR is poor, so a receipt's title may be unreadable. The band would
    # erase an invoice's totals, so without a clear answer nothing is sent at all.
    is_signed = bool(domain.signed_document.search(ocr.text))
    if not is_signed and not _has_unsigned_title(ocr, domain):
        raise PipelineError("manual_review_unknown_type")

    flagged_lines: set[tuple] = set()
    out = [img.copy() for img in ocr.images]
    draws = [ImageDraw.Draw(img) for img in out]

    # 1) Every word whose characters overlap a Presidio span.
    for w in ocr.words:
        if any(w.start < s.end and w.end > s.start for s in spans):
            _box(draws[w.page], w.left, w.top, w.width, w.height)

    # 2) Whole contact lines (label words like "Phone:" / "Email:" plus the rest of that line).
    for w in ocr.words:
        if _CONTACT_LINE.search(w.text):
            flagged_lines.add((w.page, w.line))
    for w in ocr.words:
        if (w.page, w.line) in flagged_lines:
            _box(draws[w.page], w.left, w.top, w.width, w.height)

    # 3) Bottom band of a delivery receipt, where the signature sits.
    if is_signed:
        for img, draw in zip(out, draws):
            w, h = img.size
            draw.rectangle([0, int(h * (1 - SIGNATURE_BAND)), w, h], fill="black")
    return out


def _box(draw: ImageDraw.ImageDraw, left: int, top: int, width: int, height: int) -> None:
    draw.rectangle([left - PAD_PX, top - PAD_PX, left + width + PAD_PX, top + height + PAD_PX], fill="black")
