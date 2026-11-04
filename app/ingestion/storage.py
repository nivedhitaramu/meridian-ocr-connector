"""Temporary storage for documents waiting on a background job. Files are deleted once a job finishes.

Keys are `<organization id>/<random id>.<kind>`, so no original filename is ever stored.
Local files suit one machine. Use S3-compatible storage when the API and workers run apart.
"""
from __future__ import annotations

import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from ..core import config


def new_key(organization_id: uuid.UUID, kind: str) -> str:
    return f"{organization_id}/{uuid.uuid4().hex}.{kind}"


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def older_than(self, age_seconds: int) -> list[str]: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, key: str, data: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)

    def older_than(self, age_seconds: int) -> list[str]:
        cutoff = time.time() - age_seconds
        if not self.root.exists():
            return []
        return [p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                if p.is_file() and p.stat().st_mtime < cutoff]


class S3Store:
    def __init__(self, bucket: str, endpoint_url: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None)

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def older_than(self, age_seconds: int) -> list[str]:
        cutoff = time.time() - age_seconds
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket)
        return [item["Key"] for page in pages for item in page.get("Contents", [])
                if item["LastModified"].timestamp() < cutoff]


@lru_cache(maxsize=1)
def store() -> ObjectStore:
    if config.STORAGE_BACKEND == "s3":
        return S3Store(config.S3_BUCKET, config.S3_ENDPOINT_URL)
    return LocalStore(config.STORAGE_DIR)
