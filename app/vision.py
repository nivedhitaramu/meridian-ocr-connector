"""Vision fallback. Only a redacted image ever leaves the machine.

If OCR found no word boxes we cannot know where the personal data is, so we refuse
to send the raw scan anywhere and return a manual-review error instead.
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

from .errors import PipelineError
from .ocr import OCRResult
from .pii import Span

PAD_PX = 6
SIGNATURE_BAND = 0.18  # bottom 18% of a delivery receipt page
_RECEIPT_HINT = re.compile(r"delivery\s+receipt|proof\s+of\s+delivery|\bPOD\b|received\s+by|consignee\s+sign",
                           re.IGNORECASE)
_CONTACT_LINE = re.compile(r"contact|attn|attention|phone|mobile|tel|email|e-mail|signature|signed",
                           re.IGNORECASE)


def looks_like_receipt(text: str) -> bool:
    return bool(_RECEIPT_HINT.search(text))


def signature_band_spans(ocr: OCRResult) -> list[Span]:
    """Text-path twin of the image band: on a delivery receipt, everything OCR read in the
    bottom band (signature, scribble misread as letters, 'Received by') becomes one SIGNATURE span
    per page, so it never reaches the prompt even when 'Signature:' itself is misread."""
    if not looks_like_receipt(ocr.text):
        return []
    spans = []
    for page_no, img in enumerate(ocr.images):
        cutoff = img.size[1] * (1 - SIGNATURE_BAND)
        band = [w for w in ocr.words if w.page == page_no and w.top + w.height > cutoff]
        if band:
            spans.append(Span(min(w.start for w in band), max(w.end for w in band), "SIGNATURE", 1.0))
    return spans


def redact_pages(ocr: OCRResult, spans: list[Span]) -> list[Image.Image]:
    if not ocr.words:
        raise PipelineError("manual_review_no_boxes")

    flagged_pages_lines: set[tuple[int, int]] = set()
    out = [img.copy() for img in ocr.images]
    draws = [ImageDraw.Draw(img) for img in out]

    # 1) Every word whose characters overlap a Presidio span.
    for w in ocr.words:
        if any(w.start < s.end and w.end > s.start for s in spans):
            _box(draws[w.page], w.left, w.top, w.width, w.height)

    # 2) Whole contact lines (label words like "Phone:" / "Email:" plus the rest of that line).
    for w in ocr.words:
        if _CONTACT_LINE.search(w.text):
            flagged_pages_lines.add((w.page, w.top // max(w.height, 1)))
    for w in ocr.words:
        if (w.page, w.top // max(w.height, 1)) in flagged_pages_lines:
            _box(draws[w.page], w.left, w.top, w.width, w.height)

    # 3) Bottom band of a delivery receipt, where the signature sits.
    if looks_like_receipt(ocr.text):
        for img, draw in zip(out, draws):
            w, h = img.size
            draw.rectangle([0, int(h * (1 - SIGNATURE_BAND)), w, h], fill="black")
    return out


def _box(draw: ImageDraw.ImageDraw, left: int, top: int, width: int, height: int) -> None:
    draw.rectangle([left - PAD_PX, top - PAD_PX, left + width + PAD_PX, top + height + PAD_PX], fill="black")
