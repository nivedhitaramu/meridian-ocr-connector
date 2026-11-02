"""Step 2: local OCR with Tesseract. Keeps word boxes so the vision fallback can redact."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from ..core import config
from ..core.errors import PipelineError


@dataclass
class Word:
    page: int
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    start: int  # char offset in OCRResult.text
    end: int
    line: tuple[int, int, int] = (0, 0, 0)  # Tesseract's block, paragraph and line numbers


@dataclass
class OCRResult:
    text: str
    words: list[Word]
    images: list[Image.Image] = field(repr=False)
    mean_confidence: float | None
    engine: str = "tesseract"

    @property
    def page_count(self) -> int:
        return len(self.images)

    @property
    def alnum_count(self) -> int:
        return sum(ch.isalnum() for ch in self.text)

    def needs_fallback(self) -> bool:
        if self.alnum_count < config.OCR_MIN_ALNUM:
            return True
        if self.mean_confidence is not None and self.mean_confidence < config.OCR_MIN_CONFIDENCE:
            return True
        return False


def load_pages(path: Path, kind: str) -> list[Image.Image]:
    try:
        if kind == "pdf":
            from pdf2image import convert_from_path  # needs poppler installed

            pages = convert_from_path(str(path), dpi=config.OCR_DPI, first_page=1, last_page=5)
        else:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            pages = [img.convert("RGB")]
    except Exception as exc:  # corrupt file, poppler missing, etc.
        raise PipelineError("file_unreadable") from exc
    if not pages:
        raise PipelineError("file_unreadable")
    return pages


def run_ocr(images: list[Image.Image]) -> OCRResult:
    """Build text line by line and remember each word's box and char span."""
    parts: list[str] = []
    words: list[Word] = []
    confs: list[float] = []
    cursor = 0

    for page_no, img in enumerate(images):
        try:
            data = pytesseract.image_to_data(
                img, lang=config.OCR_LANG, config=f"--psm {config.OCR_PSM}", output_type=pytesseract.Output.DICT
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise PipelineError("ocr_engine_missing") from exc

        last_line = None
        for i, raw in enumerate(data["text"]):
            token = (raw or "").strip()
            if not token:
                continue
            line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            if last_line is not None:
                sep = " " if line_key == last_line else "\n"
                parts.append(sep)
                cursor += 1
            last_line = line_key
            conf = float(data["conf"][i])
            if conf >= 0:
                confs.append(conf)
            words.append(Word(
                page=page_no, text=token,
                left=data["left"][i], top=data["top"][i],
                width=data["width"][i], height=data["height"][i],
                conf=conf, start=cursor, end=cursor + len(token), line=line_key,
            ))
            parts.append(token)
            cursor += len(token)
        if page_no < len(images) - 1:
            parts.append("\n\n")
            cursor += 2

    mean = round(sum(confs) / len(confs), 1) if confs else None
    return OCRResult(text="".join(parts), words=words, images=images, mean_confidence=mean)
