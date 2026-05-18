"""Base declarativa del ctr-service.

El CTR (Cuaderno de Trabajo Reflexivo) es una cadena criptográfica
append-only. Cada evento tiene:
  - self_hash = SHA256(event_payload_canónico)
  - chain_hash = SHA256(self_hash || prev_chain_hash)

El GENESIS_HASH es el prev_chain_hash del primer evento de cada episodio.

Propiedades que debemos preservar:
1. Integridad: cualquier manipulación de un evento rompe la cadena.
2. Orden estricto: los eventos de un episodio se procesan en orden de `seq`.
3. Idempotencia: eventos duplicados (mismo event_uuid) se ignoran.
4. Append-only: nunca UPDATE ni DELETE de eventos persistidos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Constante canónica de 64 hex chars usada como `prev_chain_hash` del primer
# evento (seq=0) de cada episodio. NO es SHA-256("")
# (que sería e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855).
# La elección de "0"*64 es arbitraria pero estable: cualquier cambio invalida
# toda cadena existente del piloto. Replicado bit-a-bit en
# `packages/contracts/src/platform_contracts/ctr/hashing.py::GENESIS_HASH`.
GENESIS_HASH = "0" * 64


NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        dict[str, Any]: "JSONB",
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


class TenantMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
