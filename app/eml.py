"""Stretch goal: pull PDF / PNG / JPEG attachments out of an .eml file."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser

from . import config
from .errors import PipelineError
from .upload import sniff_kind


def attachments(eml_bytes: bytes) -> list[bytes]:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml_bytes)
    except Exception as exc:
        raise PipelineError("eml_unreadable") from exc
    found: list[bytes] = []
    for part in msg.iter_attachments():
        payload = part.get_payload(decode=True) or b""
        if sniff_kind(payload):  # trust bytes, not the declared content type or filename
            found.append(payload)
        if len(found) >= config.MAX_EML_ATTACHMENTS:
            break
    if not found:
        raise PipelineError("eml_no_attachments")
    return found
