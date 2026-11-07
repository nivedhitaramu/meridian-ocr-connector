"""Find the active workflow by name, without the pipeline importing any one of them."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from ..core import config
from .base import Domain

_extra: dict[str, Domain] = {}


def register(domain: Domain) -> None:
    _extra[domain.name] = domain


def get(name: str) -> Domain:
    """A workflow is a package here with a domain.py, so adding one needs no change to this file."""
    if name in _extra:
        return _extra[name]
    if not name.isidentifier() or not (Path(__file__).parent / name / "domain.py").is_file():
        raise ValueError(f"Unknown domain: {name}")
    return import_module(f"{__package__}.{name}.domain").DOMAIN


def configuration(version: str) -> dict | None:
    """Any released version, so a saved result can be explained by the rules that produced it."""
    for path in Path(__file__).parent.glob("*/config/*.json"):
        if path.stem == version:
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def active() -> Domain:
    return get(config.DOMAIN)
