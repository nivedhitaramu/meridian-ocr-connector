"""Stop a webhook address being used to reach our own network."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from . import config


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_global


def acceptable(url: str, resolve: bool = True) -> bool:
    """Checked when an address is added, and again with DNS before every delivery."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # raises on a bad port
    except ValueError:
        return False
    if not host or parts.username or parts.password:
        return False
    if config.WEBHOOK_ALLOW_PRIVATE:
        return parts.scheme in ("http", "https")
    if parts.scheme != "https" or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        return _public(host)  # an IP address needs no lookup
    except ValueError:
        pass
    if not resolve:
        return True
    try:
        answers = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(answers) and all(_public(answer[4][0].split("%")[0]) for answer in answers)
