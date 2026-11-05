"""Find the active workflow by name, without the pipeline importing any one of them."""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from ..core import config
from .base import Domain

_MODULES = {"meridian": "app.domains.meridian.domain"}
_extra: dict[str, Domain] = {}


def register(domain: Domain) -> None:
    _extra[domain.name] = domain


def get(name: str) -> Domain:
    if name in _extra:
        return _extra[name]
    if name not in _MODULES:
        raise ValueError(f"Unknown domain: {name}")
    return import_module(_MODULES[name]).DOMAIN


def configuration(version: str) -> dict | None:
    """Any released version, so a saved result can be explained by the rules that produced it."""
    for path in Path(__file__).parent.glob("*/config/*.json"):
        if path.stem == version:
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def active() -> Domain:
    return get(config.DOMAIN)
