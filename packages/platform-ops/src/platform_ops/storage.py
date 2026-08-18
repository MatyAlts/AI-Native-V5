"""Storage S3-compatible compartido entre servicios.

Vivia en `content-service/services/storage.py` y lo usaba solo el modulo de
materiales. Se movio aca cuando el `evaluation-service` necesito guardar los
PDF de devolucion de Active-IA: duplicar el cliente habria significado dos
implementaciones del `S3Storage` divergiendo, y dos lugares donde acordarse de
que `MockStorage` es lo que hace correr los tests sin MinIO.

**Cada consumidor trae su propio bucket y su propio prefijo de key.** No hay
una convencion de naming global aca a proposito: los materiales de una
comision y el PDF de la correccion de un alumno son cosas distintas con
sensibilidad distinta, y mezclarlas en un bucket haria que un permiso pensado
para una alcance a la otra.
"""

from __future__ import annotations

import contextlib
import os
from abc import ABC, abstractmethod
from typing import Any


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


def storage_key_from_path(storage_path: str) -> str:
    """Recupera la key de storage desde el `storage_path` persistido.

    `put()` devuelve `mock://{key}` (MockStorage) o `s3://{bucket}/{key}`
    (S3Storage). Para volver a bajar el objeto hace falta la key desnuda, sin
    el esquema ni el bucket.
    """
    if storage_path.startswith("mock://"):
        return storage_path[len("mock://") :]
    if storage_path.startswith("s3://"):
        # s3://{bucket}/{key} -> descartar esquema + bucket, quedarse con la key
        parts = storage_path[len("s3://") :].split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    return storage_path


def build_storage(bucket_env: str, bucket_default: str) -> BaseStorage:
    """Factory: elige storage segun env. `STORAGE=mock|s3`.

    El bucket lo elige el CONSUMIDOR, no esta funcion: cada servicio pasa su
    propia env var. Un bucket compartido entre materiales y PDF de correcciones
    haria que un permiso pensado para uno alcance al otro.

    Sin `lru_cache` aca: la cachea el consumidor si quiere. Un cache de tamano
    1 compartido devolveria el storage del primer servicio que llame, con el
    bucket del otro.
    """
    which = os.environ.get("STORAGE", "").lower()
    if which == "mock":
        return MockStorage()

    endpoint = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9000")
    access_key = os.environ.get("S3_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("S3_SECRET_KEY", "minioadmin")
    bucket = os.environ.get(bucket_env, bucket_default)
    try:
        return S3Storage(endpoint, access_key, secret_key, bucket)
    except ImportError:
        return MockStorage()
