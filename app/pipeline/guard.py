"""Send a document to a person if its text is giving orders to the model.

Text in a document must never steer extraction. This catches the plain attempts without any model. It can't catch
every rewording, so the prompt also treats the text as data, and the rules and a person still decide the outcome.
Patterns stay narrow, because shipping documents often say "handling instructions" or "see note above".
"""
from __future__ import annotations

import re

_PATTERNS = (
    r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(instructions?|prompts?|rules?|figures?|above|previous|earlier)\b",
    r"\b(system|developer|assistant)\s+(note|prompt|message|instructions?)\b",
    r"\b(notes?|messages?|instructions?)\s+(to|for)\s+(the\s+)?(ai|assistant|model|llm|chatbot|extractor)\b",
    r"\byour\s+(instructions|prompt|rules)\b",
    r"\b(you\s+are|act\s+as)\s+(now\s+)?(an?\s+)?(ai|assistant|model|llm|chatbot)\b",
)
_ORDERS = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def gives_orders(text: str) -> bool:
    return _ORDERS.search(" ".join(text.split())) is not None
