"""Step 3: find personal data with Presidio and replace it with stable placeholders.

Runs locally, before any network call. The placeholder vault lives in memory for one
request and is cleared in the pipeline's `finally` block. It is never logged.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from ..core import config

# Entities we mask. DATE_TIME is deliberately absent: the shipment date is a field.
MASKED_ENTITIES = [
    "PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "LOCATION", "URL",
    "IN_MOBILE", "IN_AADHAAR", "IN_PAN", "BANK_ACCOUNT", "IFSC", "IN_GSTIN_PERSONAL",
    "POLICY_NUMBER", "ROLL_NUMBER", "CREDIT_CARD", "IBAN_CODE", "SIGNATURE", "IP_ADDRESS",
]

# Placeholder names in the prompt. Many types collapse to a few readable tokens.
_TOKEN_NAME = {
    "IN_MOBILE": "PHONE", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL",
    "LOCATION": "ADDRESS", "IN_AADHAAR": "GOV_ID", "IN_PAN": "GOV_ID",
}

# spaCy often tags company names as PERSON. If a flagged span looks like a company, keep it.
_COMPANY_WORDS = re.compile(
    r"\b(exports?|imports?|logistics|freight|warehouse|traders?|trading|industries|"
    r"ltd|limited|pvt|private|inc|llc|llp|co|corp|company|enterprises|shipping|"
    r"cargo|carriers?|textiles?|foods?|agro|mills?|works|international|global|"
    r"solutions|supplies|distributors?|retail|electronics|motors|forwarders?)\b\.?",
    re.IGNORECASE,
)
# Document labels the NER model sometimes mistakes for names or places.
_LABEL_WORDS = {
    "commercial invoice", "packing list", "delivery receipt", "invoice", "shipper",
    "consignee", "receiver", "total", "gross weight", "net weight", "cartons", "pieces",
    "description", "qty", "quantity", "date", "signature",
}

PLACEHOLDER_RE = re.compile(r"<[A-Z_]+_\d+>")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    score: float


# --------------------------------------------------------------------- vault
class PlaceholderVault:
    """Maps a normalized value to one token for the life of one request."""

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._real: dict[str, str] = {}
        self._counters: Counter[str] = Counter()
        self.entity_counts: Counter[str] = Counter()

    @staticmethod
    def normalize(value: str) -> str:
        # "Ravi Menon" and "RAVI  MENON" share a token; "Ravi M." does not.
        return " ".join(value.split()).casefold()

    def token_for(self, entity_type: str, value: str) -> str:
        name = _TOKEN_NAME.get(entity_type, entity_type)
        key = (name, self.normalize(value))
        token = self._by_value.get(key)
        if token is None:
            self._counters[name] += 1
            token = f"<{name}_{self._counters[name]}>"
            self._by_value[key] = token
            self._real[token] = " ".join(value.split())
        self.entity_counts[entity_type] += 1
        return token

    def restore(self, text: str) -> str:
        """Only for the operator's screen, inside this process. Never for logs."""
        return PLACEHOLDER_RE.sub(lambda m: self._real.get(m.group(0), m.group(0)), text)

    @property
    def placeholder_count(self) -> int:
        return len(self._real)

    def clear(self) -> None:
        self._by_value.clear()
        self._real.clear()
        self._counters.clear()


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Keep the higher-scoring (then longer) span when two overlap."""
    ordered = sorted(spans, key=lambda s: (-s.score, -(s.end - s.start), s.start))
    kept: list[Span] = []
    for s in ordered:
        if all(s.end <= k.start or s.start >= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)


def apply_mask(text: str, spans: list[Span], vault: PlaceholderVault) -> str:
    out, cursor = [], 0
    for s in resolve_overlaps(spans):
        out.append(text[cursor:s.start])
        out.append(vault.token_for(s.entity_type, text[s.start:s.end]))
        cursor = s.end
    out.append(text[cursor:])
    return "".join(out)


def _looks_like_company_or_label(value: str) -> bool:
    v = " ".join(value.split())
    return bool(_COMPANY_WORDS.search(v)) or v.casefold() in _LABEL_WORDS


# ----------------------------------------------------------------- Presidio
_LABELED_PERSON = re.compile(
    r"(?im)\b(?:contact(?:\s+person)?|attn\.?|attention|received\s+by|signed\s+by|"
    r"delivered\s+by|driver(?:\s+name)?|name)\s*[:\-]\s*"
    r"((?:[A-Z][a-zA-Z'.]+|[A-Z]{2,})(?:[ \t]+(?!(?:mobile|phone|tel|email|e-mail|signature|date)\b)"
    r"(?:[A-Z][a-zA-Z'.]+|[A-Z]{2,})){0,3})"
)
_SIGNATURE_LINE = re.compile(r"(?im)^[ \t]*(?:signature|signed|sign)\b[^\n]*$")


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import (
        AnalyzerEngine, EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult,
    )
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    class LabeledFieldRecognizer(EntityRecognizer):
        """'Contact: Priya Raman' -> PERSON over the name only. Signature lines -> SIGNATURE."""

        def load(self):  # noqa: D401
            pass

        def analyze(self, text, entities, nlp_artifacts=None):
            results = []
            if "PERSON" in entities:
                for m in _LABELED_PERSON.finditer(text):
                    if not _looks_like_company_or_label(m.group(1)):
                        results.append(RecognizerResult("PERSON", m.start(1), m.end(1), 0.9))
            if "SIGNATURE" in entities:
                for m in _SIGNATURE_LINE.finditer(text):
                    results.append(RecognizerResult("SIGNATURE", m.start(), m.end(), 0.95))
            return results

    def pattern(entity, regex, score, context=None, name=None):
        return PatternRecognizer(
            supported_entity=entity,
            patterns=[Pattern(name or entity.lower(), regex, score)],
            context=context or [],
        )

    custom = [
        LabeledFieldRecognizer(supported_entities=["PERSON", "SIGNATURE"], name="labeled_fields"),
        # Indian mobile: optional +91 / 0, starts 6-9, 10 digits, optional space/dash after 5.
        pattern("IN_MOBILE", r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)", 0.75,
                ["mobile", "phone", "tel", "contact", "ph"]),
        # Aadhaar-shaped: 12 digits, first digit 2-9, optional spaces in groups of four.
        pattern("IN_AADHAAR", r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)", 0.6,
                ["aadhaar", "aadhar", "uid", "uidai"]),
        pattern("IN_PAN", r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b", 0.8, ["pan", "income tax"]),
        pattern("IFSC", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", 0.7, ["ifsc", "bank", "branch"]),
        # Bank accounts need context words, or every long reference number would be masked.
        pattern("BANK_ACCOUNT", r"(?<!\d)\d{9,18}(?!\d)", 0.3,
                ["account", "a/c", "acct", "acc", "bank", "savings", "current"]),
        pattern("POLICY_NUMBER", r"\b(?:POL|PLCY|POLICY)[-/ ]?\d{6,12}\b", 0.7, ["policy"]),
        pattern("ROLL_NUMBER", r"\b(?:ROLL|RN)[-/ ]?\d{4,10}\b", 0.6, ["roll"]),
    ]

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": config.SPACY_MODEL}],
    })
    engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    for rec in custom:
        engine.registry.add_recognizer(rec)
    return engine


def detect(text: str) -> list[Span]:
    results = _analyzer().analyze(
        text=text, language="en", entities=MASKED_ENTITIES,
        score_threshold=config.PII_SCORE_THRESHOLD,
    )
    spans = []
    for r in results:
        value = text[r.start:r.end]
        if r.entity_type in ("PERSON", "LOCATION") and _looks_like_company_or_label(value):
            continue  # company names may stay in the prompt
        spans.append(Span(r.start, r.end, r.entity_type, r.score))
    return resolve_overlaps(spans)


def mask(text: str, vault: PlaceholderVault, extra: list[Span] | None = None) -> tuple[str, list[Span]]:
    """`extra` carries spans found by layout, e.g. the signature band of a delivery receipt."""
    spans = resolve_overlaps(detect(text) + list(extra or []))
    return apply_mask(text, spans, vault), spans


def warm_up() -> None:
    """Load spaCy once at startup so the first request's pii timing is honest."""
    _analyzer()
