"""Find the active workflow by name, without the pipeline importing any one of them."""
from __future__ import annotations

from importlib import import_module

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


def active() -> Domain:
    return get(config.DOMAIN)
