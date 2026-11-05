"""A document workflow described by a configuration file, and the deterministic engine that runs it.

A configuration chooses the document types, fields, units and rule reasons. The status always comes from
this code and never from the model. A released version is never edited: changes go in a new file, so a saved
result can always be explained by the version it names.
"""
from __future__ import annotations

import json
import re
import string
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model, field_validator, model_validator

from .base import Domain, PIIInfo, PipelineInfo

CheckStatus = Literal["Match", "Mismatch", "Incomplete", "Not applicable"]

_DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d %b, %Y", "%Y/%m/%d",
)
_REASON_VALUES = {"left_value", "right_value", "unit", "left_unit", "right_unit"}
REASON_KEYS = {"not_applicable", "none_recognized", "missing_left", "missing_right", "too_many", "unreadable",
               "unit_clash", "match", "differ"}


def parse_number(value) -> float | None:
    """'1,200' -> 1200.0, '860.5 kg' -> 860.5, 120 -> 120.0. Thousands separators stripped."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def normalize_date(value) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split()).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text  # keep as printed when not parseable


def _clean_text(value) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).split()) or None


def _count(value) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(number) if float(number).is_integer() else None  # 120.0 -> 120; 120.5 is not a count


FIELD_TYPES: dict[str, Any] = {
    "text": Annotated[str | None, BeforeValidator(_clean_text)],
    "date": Annotated[str | None, BeforeValidator(normalize_date)],
    "count": Annotated[int | None, BeforeValidator(_count)],
    "number": Annotated[float | None, BeforeValidator(parse_number)],
}
_PRIVATE_ERRORS = ConfigDict(hide_input_in_errors=True)  # validation errors must not echo values


class QuantityTotal(BaseModel):
    model_config = _PRIVATE_ERRORS

    value: float
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _v(cls, v):
        n = parse_number(v)
        if n is None:
            raise ValueError("not a number")
        return n


class Check(BaseModel):
    status: CheckStatus
    reason: str  # never contains names, IDs, phones, emails


@dataclass
class ParsedDoc:
    document_type: str
    fields: Any
    totals: list[QuantityTotal]  # units normalized
    quantity_field: str = "total_quantity"

    @property
    def quantity(self) -> int | None:
        return getattr(self.fields, self.quantity_field)

    @property
    def unit(self) -> str | None:
        """Unit of the document's stated total."""
        if self.quantity is None:
            return None
        for t in self.totals:
            if t.value == self.quantity:
                return t.unit
        return self.totals[0].unit if self.totals else None


class Privacy(BaseModel):
    reference_fields: list[str]
    party_fields: list[str]
    signed_document: str
    unsigned_title: str


class Weight(BaseModel):
    field: str
    convert_from: list[str]
    factor: float = Field(gt=0)


class CheckRule(BaseModel):
    type: Literal["compare_totals"]
    field: str
    left: str
    right: str
    not_applicable_alone: str
    reasons: dict[str, str]


class WorkflowConfig(BaseModel):
    """Refuses a broken file at startup, instead of a wrong answer later."""
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    domain: str
    prompt_version: str
    system_prompt: str = Field(min_length=1)
    image_instruction: str
    document_types: dict[str, list[str]]
    fields: dict[str, Literal["text", "date", "count", "number"]]
    privacy: Privacy
    units: dict[str, list[str]]
    primary_units: list[str]
    weight: Weight | None = None
    check: CheckRule

    @model_validator(mode="after")
    def _references_exist(self) -> "WorkflowConfig":
        def need(condition: bool, problem: str) -> None:
            if not condition:
                raise ValueError(problem)

        rule = self.check
        for kind in (rule.left, rule.right, rule.not_applicable_alone):
            need(kind in self.document_types, f"unknown document type: {kind}")
        need(rule.left != rule.right, "a rule must compare two document types")
        need("unknown" in self.document_types, "document types must include unknown")
        need(self.fields.get(rule.field) == "count", "the compared field must be a count")
        if self.weight:
            need(self.fields.get(self.weight.field) == "number", "the weight field must be a number")
        for name in self.privacy.reference_fields + self.privacy.party_fields:
            need(self.fields.get(name) == "text", f"privacy needs a text field: {name}")
        for unit in self.primary_units:
            need(unit in self.units, f"unknown unit: {unit}")
        need(set(rule.reasons) == REASON_KEYS, "the rule must define every reason, and no others")
        for key, template in rule.reasons.items():
            names = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
            need(names <= _REASON_VALUES, f"reason {key} uses a value it can't have")
        for pattern in (self.privacy.signed_document, self.privacy.unsigned_title):
            try:
                re.compile(pattern)
            except re.error as err:
                raise ValueError("a privacy pattern is not valid") from err
        return self


def _plural(unit: str) -> str:
    return unit + ("es" if unit.endswith("x") else "s")


def _fmt(n: float) -> str:
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,}"


def _totals_only(totals: list[QuantityTotal], stated: int | None) -> list[QuantityTotal]:
    """Models sometimes list item rows beside the total. A total is never smaller than its rows,
    so keep the largest value for each unit. Different units stay apart: no pack size is guessed."""
    largest: dict[str | None, QuantityTotal] = {}
    for total in totals:
        if total.unit not in largest or total.value > largest[total.unit].value:
            largest[total.unit] = total
    if stated is not None and len(largest) == 1:
        only = next(iter(largest.values()))
        if stated > only.value:  # the model's own total field saw a total its list missed
            largest[only.unit] = QuantityTotal(value=stated, unit=only.unit)
    return list(largest.values())


def _pick_comparable(left: ParsedDoc, right: ParsedDoc) -> tuple[QuantityTotal, QuantityTotal] | None:
    for a in left.totals:
        for b in right.totals:
            if a.unit and a.unit == b.unit:
                return a, b
    return None


class Workflow:
    """One configuration, turned into the models and functions the pipeline calls."""

    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config
        self._aliases = {kind: kind for kind in config.document_types}
        self._aliases.update({alias: kind for kind, aliases in config.document_types.items() for alias in aliases})

    @classmethod
    def load(cls, path: Path) -> "Workflow":
        return cls(WorkflowConfig.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    @cached_property
    def document_type(self) -> Any:
        return Literal[tuple(self.config.document_types)]

    @cached_property
    def fields_model(self) -> type[BaseModel]:
        definitions = {name: (FIELD_TYPES[kind], None) for name, kind in self.config.fields.items()}
        return create_model(f"{self.config.domain.title()}Fields", __config__=_PRIVATE_ERRORS, **definitions)

    @cached_property
    def extraction_model(self) -> type[BaseModel]:
        """What the model must return. Extra helper keys live outside `fields`."""
        aliases = self._aliases

        def document_type(value) -> str:
            return aliases.get(" ".join(str(value or "").lower().replace("-", " ").split()), "unknown")

        return create_model(
            "LLMExtraction", __config__=_PRIVATE_ERRORS,
            document_type=(Annotated[self.document_type, BeforeValidator(document_type)], ...),
            fields=(self.fields_model, ...),
            quantity_totals=(list[QuantityTotal], Field(default_factory=list)),
            weight_unit=(str | None, None),
        )

    @cached_property
    def document_model(self) -> type[BaseModel]:
        return create_model(
            "DocumentResult", slot=(int, ...), document_type=(self.document_type, ...), fields=(self.fields_model, ...),
            quantity_unit=(str | None, None), quantity_totals=(list[QuantityTotal], Field(default_factory=list)),
            page_count=(int, 1), used_vision_fallback=(bool, False),
        )

    @cached_property
    def response_model(self) -> type[BaseModel]:
        return create_model(
            "ExtractResponse", request_id=(str, ...),
            document_type=(self.document_type, ...),  # first document, matches the brief's contract
            fields=(self.fields_model, ...), check=(Check, ...), pii=(PIIInfo, ...), pipeline=(PipelineInfo, ...),
            documents=(list[self.document_model], ...),  # one entry per uploaded file or attachment
        )

    def normalize_unit(self, unit: str | None) -> str | None:
        if not unit:
            return None
        u = unit.strip().lower()
        for canonical, names in self.config.units.items():
            if u in names:
                return canonical
        return u.rstrip("s.") or None

    def post_process(self, extraction: Any) -> ParsedDoc:
        """Deterministic clean-up after the model: units, converted weight, primary total."""
        quantity_field = self.config.check.field
        fields = extraction.fields.model_copy()
        totals = _totals_only([QuantityTotal(value=t.value, unit=self.normalize_unit(t.unit)) for t in extraction.quantity_totals],
                              getattr(fields, quantity_field))
        weight = self.config.weight
        if weight and getattr(fields, weight.field) is not None and (extraction.weight_unit or "").strip().lower() in weight.convert_from:
            setattr(fields, weight.field, round(getattr(fields, weight.field) * weight.factor, 2))
        if totals:
            primary = next((t for t in totals if t.unit in self.config.primary_units), totals[0])
            if float(primary.value).is_integer():
                setattr(fields, quantity_field, int(primary.value))
        elif getattr(fields, quantity_field) is not None:
            totals = [QuantityTotal(value=getattr(fields, quantity_field), unit=None)]
        return ParsedDoc(extraction.document_type, fields, totals, quantity_field)

    def check(self, docs: list[ParsedDoc]) -> Check:
        rule = self.config.check
        said = rule.reasons
        lefts = [d for d in docs if d.document_type == rule.left]
        rights = [d for d in docs if d.document_type == rule.right]
        alone = [d for d in docs if d.document_type == rule.not_applicable_alone]

        if not lefts and not rights:
            if alone and len(alone) == len(docs):
                return Check(status="Not applicable", reason=said["not_applicable"])
            return Check(status="Incomplete", reason=said["none_recognized"])
        if not lefts:
            return Check(status="Incomplete", reason=said["missing_left"])
        if not rights:
            return Check(status="Incomplete", reason=said["missing_right"])
        if len(lefts) > 1 or len(rights) > 1:
            return Check(status="Incomplete", reason=said["too_many"])

        left, right = lefts[0], rights[0]
        if left.quantity is None or right.quantity is None:
            return Check(status="Mismatch", reason=said["unreadable"])

        pair = _pick_comparable(left, right)
        if pair is None:
            lu, ru = left.unit, right.unit
            if lu and ru and lu != ru:
                return Check(status="Mismatch", reason=said["unit_clash"].format(left_unit=_plural(lu), right_unit=_plural(ru)))
            pair = (QuantityTotal(value=left.quantity, unit=lu), QuantityTotal(value=right.quantity, unit=ru))

        a, b = pair
        unit = f" {_plural(a.unit)}" if a.unit else ""
        if a.value == b.value:
            return Check(status="Match", reason=said["match"].format(left_value=_fmt(a.value), unit=unit))
        return Check(status="Mismatch", reason=said["differ"].format(left_value=_fmt(a.value), right_value=_fmt(b.value), unit=unit))

    def build_document(self, slot: int, parsed: ParsedDoc, page_count: int, used_vision_fallback: bool) -> BaseModel:
        return self.document_model(slot=slot, document_type=parsed.document_type, fields=parsed.fields,
                                   quantity_unit=parsed.unit, quantity_totals=parsed.totals,
                                   page_count=page_count, used_vision_fallback=used_vision_fallback)

    def build_response(self, request_id: str, documents: list[BaseModel], check: Check, pii: PIIInfo, pipeline: PipelineInfo) -> BaseModel:
        return self.response_model(request_id=request_id, document_type=documents[0].document_type, fields=documents[0].fields,
                                   check=check, pii=pii, pipeline=pipeline, documents=documents)

    def domain(self, mock_extract: Callable[[str], Any] | None = None) -> Domain:
        def no_mock(_: str) -> Any:
            raise RuntimeError("This workflow has no offline stand-in")

        config = self.config
        return Domain(
            name=config.domain, prompt_version=config.prompt_version, system_prompt=config.system_prompt,
            image_instruction=config.image_instruction, extraction_model=self.extraction_model,
            response_model=self.response_model, mock_extract=mock_extract or no_mock,
            reference_fields=tuple(config.privacy.reference_fields), party_fields=tuple(config.privacy.party_fields),
            signed_document=re.compile(config.privacy.signed_document, re.IGNORECASE),
            unsigned_title=re.compile(config.privacy.unsigned_title, re.IGNORECASE),
            post_process=self.post_process, check=self.check, build_document=self.build_document,
            build_response=self.build_response, config_version=config.version,
        )
