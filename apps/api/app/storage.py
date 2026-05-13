"""Object storage abstraction. S3-compatible (AWS S3 / MinIO / …) when S3_BUCKET is configured,
otherwise a local-filesystem fallback so the no-Docker dev path works without MinIO.

The full product would hand the browser presigned PUT/GET URLs (docs/18); for the scaffold the
API streams bytes through (simpler, and avoids the MinIO-behind-Docker host-rewrite gotcha)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from .config import settings

log = logging.getLogger("uvicorn.error")


class StorageBackend(ABC):
    name: str

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def open_stream(self, key: str) -> BinaryIO: ...  # caller is responsible for closing

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    def ensure_ready(self) -> None:  # create bucket / base dir if needed
        return None


class LocalFsBackend(StorageBackend):
    name = "local"

    def __init__(self, base_dir: str) -> None:
        self.base = Path(base_dir).resolve()

    def _path(self, key: str) -> Path:
        # keep keys inside base; reject traversal
        p = (self.base / key).resolve()
        if not str(p).startswith(str(self.base)):
            raise ValueError("invalid storage key")
        return p

    def ensure_ready(self) -> None:
        self.base.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def open_stream(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3Backend(StorageBackend):
    name = "s3"

    def __init__(self) -> None:
        import boto3  # imported lazily so the dep is only needed when S3 is configured
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        kwargs: dict = {"region_name": settings.s3_region}
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
            # MinIO / Ceph / etc. need path-style addressing (http://host:port/bucket/key),
            # not virtual-hosted-style (http://bucket.host/key).
            kwargs["config"] = Config(s3={"addressing_style": "path"}, signature_version="s3v4")
        if settings.s3_access_key:
            kwargs["aws_access_key_id"] = settings.s3_access_key
            kwargs["aws_secret_access_key"] = settings.s3_secret_key
        self.client = boto3.client("s3", **kwargs)

    def ensure_ready(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError:
            pass
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                log.warning("Could not create S3 bucket %r: %s (note: bucket names must be 3-63 chars, lowercase)", self.bucket, e)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def open_stream(self, key: str) -> BinaryIO:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"]  # botocore StreamingBody — supports .read()/.iter_chunks()/.close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = S3Backend() if settings.use_s3 else LocalFsBackend(settings.local_storage_dir)
    return _backend


def tenant_key(tenant_id: str, *parts: str) -> str:
    """Per-tenant key prefix, e.g. tenants/<id>/ocr/<uuid>-<name>."""
    cleaned = [str(p).replace("\\", "/").lstrip("/") for p in parts if p]
    return "/".join(["tenants", tenant_id, *cleaned])
