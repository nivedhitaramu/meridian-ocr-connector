"""Decide which shipment a document belongs to, using only what OCR read on this machine.

Grouping never guesses. A document joins a shipment only when its reference is clear and nothing conflicts.
Anything else goes to a person, with a reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_REFERENCE = re.compile(
    r"\b(?:invoice\s*(?:no|number|ref(?:erence)?)|bill\s*(?:no|number)|against\s*invoice|"
    r"(?:shipment|consignment)\s*(?:ref(?:erence)?|no|number))\b\.?\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9/._-]{2,})",
    re.IGNORECASE,
)
_TITLES = (
    ("commercial_invoice", re.compile(r"^\s*(?:commercial\s+invoice|tax\s+invoice)\b", re.IGNORECASE)),
    ("packing_list", re.compile(r"^\s*packing\s+list\b", re.IGNORECASE)),
    ("delivery_receipt", re.compile(r"^\s*(?:delivery\s+receipt|proof\s+of\s+delivery)\b", re.IGNORECASE)),
)
TITLE_LINES = 3

# Characters OCR commonly reads as each other.
_LOOKALIKE = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})

AUTO = "grouped"
REVIEW = "needs_review"


@dataclass(frozen=True)
class Read:
    document_type: str
    reference: str | None
    problem: str | None = None  # poor_scan, no_reference or conflicting_references


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str | None = None


def normalize(reference: str) -> str:
    """So MF-1001, mf 1001 and MF/1001 are recognized as one reference."""
    return re.sub(r"[^A-Z0-9]", "", reference.upper())


def document_type(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()][:TITLE_LINES]
    for line in lines:
        for kind, title in _TITLES:
            if title.search(line):
                return kind
    return "unknown"


def read_text(text: str, poor_scan: bool = False) -> Read:
    kind = document_type(text)
    if poor_scan:
        return Read(kind, None, "poor_scan")
    found = {}
    for match in _REFERENCE.finditer(text):
        value = match.group(1).rstrip("./-_")
        if any(c.isdigit() for c in value):
            found.setdefault(normalize(value), value)
    if not found:
        return Read(kind, None, "no_reference")
    if len(found) > 1:
        return Read(kind, None, "conflicting_references")
    return Read(kind, next(iter(found.values())))


def _distance_at_most_one(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i, j = i + 1, j + 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) == len(b):
            i += 1
        j += 1
    return edits + (len(b) - j) <= 1


def looks_similar(a: str, b: str) -> bool:
    """Two different references a misread could have produced. Never treated as the same shipment."""
    if a == b:
        return False
    return a.translate(_LOOKALIKE) == b.translate(_LOOKALIKE) or _distance_at_most_one(a, b)


def decide(reads: list[Read], shipments: dict[str, bool]) -> list[Decision]:
    """Decide a whole batch together. `shipments` maps each known normalized reference to whether it was checked already."""
    keys = [normalize(read.reference) if read.reference else None for read in reads]
    seen_types: dict[tuple[str, str], int] = {}
    for key, read in zip(keys, reads):
        if key:
            seen_types[(key, read.document_type)] = seen_types.get((key, read.document_type), 0) + 1
    known = set(shipments) | {key for key in keys if key}
    copies = {key: keys.count(key) for key in keys if key}

    decisions = []
    for key, read in zip(keys, reads):
        if read.problem:
            decisions.append(Decision(REVIEW, read.problem))
        elif read.document_type == "unknown":
            decisions.append(Decision(REVIEW, "unknown_type"))
        elif seen_types[(key, read.document_type)] > 1:
            decisions.append(Decision(REVIEW, "duplicate_type"))
        elif any(looks_similar(key, other) for other in known):
            decisions.append(Decision(REVIEW, "similar_reference"))
        elif shipments.get(key):
            decisions.append(Decision(REVIEW, "shipment_already_checked"))
        elif key not in shipments and copies[key] < 2:
            # One OCR read alone could be a misread. A new shipment needs a second document to agree.
            decisions.append(Decision(REVIEW, "no_matching_document"))
        else:
            decisions.append(Decision(AUTO))
    return decisions
