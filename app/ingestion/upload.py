"""Step 1: accept a file, check the bytes (not the extension), store under a random id."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from ..core import config
from ..core.errors import PipelineError

_MAGIC = (
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
)


def sniff_kind(data: bytes) -> str | None:
    head = data[:16]
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    return None


@dataclass
class StoredUpload:
    file_id: str
    path: Path
    kind: str  # pdf | png | jpg
    size: int

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def store(data: bytes) -> StoredUpload:
    """The original filename is deliberately not a parameter: people name files after themselves."""
    if not data:
        raise PipelineError("upload_empty")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise PipelineError("upload_too_large")
    kind = sniff_kind(data)
    if kind is None:
        raise PipelineError("upload_bad_type")
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex
    path = config.UPLOAD_DIR / f"{file_id}.{kind}"
    path.write_bytes(data)
    return StoredUpload(file_id=file_id, path=path, kind=kind, size=len(data))
