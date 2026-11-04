"""Modelos del estudio de codificación ciega (change cibse-codificacion-ciega, design D1).

Tablas SEPARADAS del piloto inter-jueces (`interrater_ratings`): nada de acá lo
lee el agregado κ del piloto, `pedagogia.py` ni la exportación del eje fino.

Compatibilidad con SQLite: varios tests de otros paquetes hacen
`Base.metadata.create_all` de todo `classifier_service.models` sobre SQLite.
Por eso este módulo usa solo lo que ya usa el resto (`JSONB`, `PgUUID`,
`UniqueConstraint`, `Index` simples) y todo lo exclusivo de Postgres vive solo
en la migración `20261104_0007`:

- unicidad PARCIAL de membresía activa por `(estudio_id, lower(email))`;
- la FK `estudio_codificacion.codebook_vigente_id` (circular con
  `codebook_version.estudio_id`);
- los triggers de inmutabilidad de design D2;
- RLS por tenant (`apply_tenant_rls`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from classifier_service.models import Base, TenantMixin, utc_now_f


class EstudioCodificacion(Base, TenantMixin):
    """Un estudio de codificación humana (p. ej. `cibse-2027`).

    `traza_version` se fija en el alta con la versión vigente de la lista
    blanca de la traza ciega y rige muestra, anclas, entrenamiento y
    etiquetas (design D4b)."""

    __tablename__ = "estudio_codificacion"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clave: Mapped[str] = mapped_column(String(41), nullable=False)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    # FK a codebook_version solo en la migración (circular).
    codebook_vigente_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    muestra_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    muestra_cargada_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    traza_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (UniqueConstraint("tenant_id", "clave", name="uq_estudio_codificacion_clave"),)


class EstudioMembresia(Base, TenantMixin):
    """Asignación de un email a un estudio con UN rol (design D3).

    El email (minúsculas) solo sirve para la asignación inicial: en el primer
    uso se ata `user_id` (el campo que la firma del gateway sí cubre) y desde
    ahí la identidad del dato es la membresía. Revocar fija `revocada_at`; una
    re-asignación crea una fila nueva."""

    __tablename__ = "estudio_membresia"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_codificacion.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    alias: Mapped[str] = mapped_column(String(20), nullable=False)
    semilla: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    cerrada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("estudio_id", "alias", name="uq_estudio_membresia_alias"),
        UniqueConstraint("estudio_id", "semilla", name="uq_estudio_membresia_semilla"),
    )


class EstudioMuestra(Base, TenantMixin):
    """Ítem de la muestra fija: `item_id` opaco + evidencia fija (design D4b, D14).

    El codificador nunca recibe `episode_id`. Las columnas de evidencia fija
    y de enunciado (`problema_id`, `ejercicio_id`) no admiten UPDATE (D2)."""

    __tablename__ = "estudio_muestra"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_codificacion.id"), nullable=False, index=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    seq_tope: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_hash_tope: Mapped[str] = mapped_column(String(64), nullable=False)
    events_count_carga: Mapped[int] = mapped_column(Integer, nullable=False)
    last_chain_hash_carga: Mapped[str] = mapped_column(String(64), nullable=False)
    estado_carga: Mapped[str] = mapped_column(String(20), nullable=False)
    problema_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    ejercicio_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    cargado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("estudio_id", "episode_id", name="uq_estudio_muestra_episodio"),
    )


class EstudioEnunciado(Base, TenantMixin):
    """Enunciado de TP o de ejercicio cargado a mano por el investigador (D14).

    El original y su hash no cambian una vez revisado; lo mostrado tampoco."""

    __tablename__ = "estudio_enunciado"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_codificacion.id"), nullable=False, index=True
    )
    fuente: Mapped[str] = mapped_column(String(12), nullable=False)
    fuente_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    archivo_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    cargado_por: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cargado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )
    contenido_original_md: Mapped[str] = mapped_column(Text, nullable=False)
    sha256_original: Mapped[str] = mapped_column(String(64), nullable=False)
    contenido_mostrado_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256_mostrado: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alertas: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    revisado_por: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    revisado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("estudio_id", "fuente", "fuente_id", name="uq_estudio_enunciado_fuente"),
    )


class CodebookVersion(Base, TenantMixin):
    """Versión del codebook de un estudio: Markdown + esquema de formulario (D8, D9).

    Nace `borrador`; `congelada` no admite UPDATE ni DELETE (trigger, D2).
    `contenido_sha256` cubre texto, esquema y anclas en forma canónica."""

    __tablename__ = "codebook_version"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_codificacion.id"), nullable=False, index=True
    )
    etiqueta: Mapped[str] = mapped_column(String(40), nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="borrador")
    contenido_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    esquema_formulario: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    contenido_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    congelada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    congelada_por: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("estudio_id", "etiqueta", name="uq_codebook_version_etiqueta"),
    )


class EstudioAncla(Base, TenantMixin):
    """Ancla de entrenamiento (`ejemplo` o `practica`) de una versión del codebook (D11).

    Misma evidencia fija y mismos campos de enunciado que la muestra. Las
    anclas de una versión congelada no se agregan, editan ni borran (D2)."""

    __tablename__ = "estudio_ancla"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estudio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_codificacion.id"), nullable=False, index=True
    )
    codebook_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("codebook_version.id"), nullable=False, index=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    seq_tope: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_hash_tope: Mapped[str] = mapped_column(String(64), nullable=False)
    events_count_carga: Mapped[int] = mapped_column(Integer, nullable=False)
    last_chain_hash_carga: Mapped[str] = mapped_column(String(64), nullable=False)
    estado_carga: Mapped[str] = mapped_column(String(20), nullable=False)
    problema_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    ejercicio_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    uso: Mapped[str] = mapped_column(String(12), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    respuesta_esperada: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    explicacion_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    consensuado_por: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )


class EstudioEtiqueta(Base, TenantMixin):
    """Etiqueta vigente de un codificador sobre un ítem (D9, D10).

    `regimen` es el derivado por la regla o el exento elegido; `regimen_regla`
    el que da la regla siempre que sea calculable; `disiente_de_regla` NO se
    persiste: se deriva de `regimen_propuesto` y `regimen`."""

    __tablename__ = "estudio_etiqueta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    membresia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_membresia.id"), nullable=False, index=True
    )
    muestra_item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_muestra.item_id"), nullable=False, index=True
    )
    codebook_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("codebook_version.id"), nullable=False
    )
    traza_version: Mapped[str] = mapped_column(String(20), nullable=False)
    respuestas: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    regimen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    regimen_regla: Mapped[str | None] = mapped_column(String(40), nullable=True)
    regimen_propuesto: Mapped[str | None] = mapped_column(String(40), nullable=True)
    es_frontera: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confianza: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("membresia_id", "muestra_item_id", name="uq_estudio_etiqueta_item"),
    )


class EstudioEtiquetaHistorial(Base, TenantMixin):
    """Snapshot de cada guardado de etiqueta. Append-only por trigger (D2)."""

    __tablename__ = "estudio_etiqueta_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    etiqueta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("estudio_etiqueta.id"), nullable=False, index=True
    )
    membresia_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    muestra_item_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    guardado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )


class EntrenamientoRespuesta(Base, TenantMixin):
    """Respuesta de un miembro a un ancla de práctica. Append-only por trigger (D2, D11)."""

    __tablename__ = "entrenamiento_respuesta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    membresia_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_membresia.id"), nullable=False, index=True
    )
    ancla_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("estudio_ancla.item_id"), nullable=False, index=True
    )
    codebook_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("codebook_version.id"), nullable=False
    )
    traza_version: Mapped[str] = mapped_column(String(20), nullable=False)
    respuestas: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    regimen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    regimen_regla: Mapped[str | None] = mapped_column(String(40), nullable=True)
    regimen_propuesto: Mapped[str | None] = mapped_column(String(40), nullable=True)
    es_frontera: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confianza: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    respondida_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now_f, nullable=False
    )


__all__ = [
    "CodebookVersion",
    "EntrenamientoRespuesta",
    "EstudioAncla",
    "EstudioCodificacion",
    "EstudioEnunciado",
    "EstudioEtiqueta",
    "EstudioEtiquetaHistorial",
    "EstudioMembresia",
    "EstudioMuestra",
]
