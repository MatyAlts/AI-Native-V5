"""Cliente de storage S3-compatible para materiales originales.

Usa boto3/aioboto3 contra MinIO en dev y S3 real en producción. Los
objetos se nombran por convención:

    materials/{tenant_id}/{comision_id}/{material_id}/original.{ext}

En tests, se puede usar un MockStorage que guarda en memoria.
"""

from __future__ import annotations

import contextlib
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any
from uuid import UUID


class BaseStorage(ABC):
    @abstractmethod
    async def put(self, key: str, content: bytes, content_type: str) -> str:
        """Sube un objeto y devuelve el storage_path guardable."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Descarga el contenido."""

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class MockStorage(BaseStorage):
    """In-memory, para tests y desarrollo sin MinIO."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes, content_type: str) -> str:
        self._objects[key] = content
        return f"mock://{key}"

    async def get(self, key: str) -> bytes:
        if key not in self._objects:
            raise FileNotFoundError(key)
        return self._objects[key]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


class S3Storage(BaseStorage):
    """Cliente S3 real (MinIO o AWS). Lazy-loaded para no forzar boto3 en tests."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.client import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=Config(signature_version="s3v4"),
            )
            # Crear bucket si no existe (MinIO lo hace en arranque)
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except Exception:
                with contextlib.suppress(Exception):
                    self._client.create_bucket(Bucket=self.bucket)
        return self._client

    async def put(self, key: str, content: bytes, content_type: str) -> str:
        import asyncio

        client = self._ensure_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return f"s3://{self.bucket}/{key}"

    async def get(self, key: str) -> bytes:
        import asyncio

        client = self._ensure_client()
        obj = await asyncio.to_thread(client.get_object, Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    async def delete(self, key: str) -> None:
        import asyncio

        client = self._ensure_client()
        await asyncio.to_thread(client.delete_object, Bucket=self.bucket, Key=key)


def make_storage_key(tenant_id: UUID, comision_id: UUID, material_id: UUID, filename: str) -> str:
    """Convención de naming de objetos en storage."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    return f"materials/{tenant_id}/{comision_id}/{material_id}/original.{ext}"


@lru_cache(maxsize=1)
def get_storage() -> BaseStorage:
    """Factory: elige storage según env. STORAGE=mock|s3."""
    which = os.environ.get("STORAGE", "").lower()
    if which == "mock":
        return MockStorage()

    # Default: intentar S3/MinIO
    endpoint = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9000")
    access_key = os.environ.get("S3_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("S3_SECRET_KEY", "minioadmin")
    bucket = os.environ.get("S3_BUCKET_MATERIALS", "materials")
    try:
        return S3Storage(endpoint, access_key, secret_key, bucket)
    except ImportError:
        return MockStorage()
