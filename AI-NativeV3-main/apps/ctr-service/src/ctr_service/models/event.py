"""Modelos del CTR.

Un Episodio agrupa una sesión completa del estudiante con el tutor
(desde que abre el problema hasta que lo declara cerrado). Cada
interacción durante ese episodio es un Evento con su par
(self_hash, chain_hash) que forma la cadena criptográfica.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ctr_service.models.base import Base, TenantMixin, utc_now, uuid_pk


class Episode(Base, TenantMixin):
    """Episodio de trabajo con el tutor sobre un problema específico."""

    __tablename__ = "episodes"

    id: Mapped[uuid.UUID] = uuid_pk()
    comision_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    student_pseudonym: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    problema_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    # Hashes de configuración en el momento de apertura del episodio
    # (ADR-009: Git como fuente de verdad del prompt).
    prompt_system_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_system_version: Mapped[str] = mapped_column(String(30), nullable=False)
    classifier_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    curso_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Estados: open | closed | expired | integrity_compromised
    estado: Mapped[str] = mapped_column(String(30), default="open", nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Evento count: cuántos eventos se han persistido en este episodio
    # (útil como sequence en el worker para el próximo seq esperado)
    events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Último chain_hash computado — para verificar continuidad al agregar el próximo
    last_chain_hash: Mapped[str] = mapped_column(String(64), default="0" * 64, nullable=False)

    # Flag si la cadena se detecta rota por un consumer (p. ej. un evento
    # del stream falló y fue al DLQ con `integrity_compromised=true`).
    integrity_compromised: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Metadata (cantidad de prompts enviados, tiempo activo, etc.)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    events: Mapped[list[Event]] = relationship(back_populates="episode", cascade="all")


class Event(Base, TenantMixin):
    """Evento individual del CTR — append-only.

    El evento se persiste junto con su `self_hash` y `chain_hash` en la
    misma transacción que el ACK al stream de Redis. Nunca se hace UPDATE
    ni DELETE de eventos existentes.
    """

    __tablename__ = "events"

    # id autoincremental; el UUID lógico del evento es `event_uuid`
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_uuid: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # UUID producido por el emisor — sirve para deduplicación idempotente
    # en el consumer (si llega el mismo event_uuid dos veces, se ignora).

    episode_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("episodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Secuencia dentro del episodio. Orden estricto: seq=0 es EpisodioAbierto.

    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # "episodio_abierto" | "prompt_enviado" | "codigo_ejecutado" |
    # "tutor_respondio" | "anotacion_creada" | "cambio_de_estrategia" |
    # "episodio_cerrado" | "episodio_abandonado" | "edicion_codigo" |
    # "lectura_enunciado" | "intento_adverso_detectado" |
    # "reflexion_completada" (ADR-035, post-cierre, append-only) |
    # "tests_ejecutados" (ADR-033/034, sandbox client-side, conteos sin detalle) | ...

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Timestamp del emisor (no el de persistencia)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Payload tipado por event_type; schema en packages/contracts.

    # Hashes criptográficos
    self_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Hashes de configuración vigente al momento del evento
    prompt_system_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_system_version: Mapped[str] = mapped_column(String(30), nullable=False)
    classifier_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    episode: Mapped[Episode] = relationship(back_populates="events")

    __table_args__ = (
        # Idempotencia: mismo event_uuid se persiste una sola vez
        UniqueConstraint("tenant_id", "event_uuid", name="uq_events_event_uuid"),
        # Orden estricto por episodio
        UniqueConstraint("tenant_id", "episode_id", "seq", name="uq_events_episode_seq"),
        Index("ix_events_episode_seq", "episode_id", "seq"),
        Index("ix_events_chain_hash", "chain_hash"),
    )


class DeadLetter(Base, TenantMixin):
    """Eventos que fallaron persistentemente y fueron derivados a DLQ.

    Cuando un evento aparece aquí, el episodio al que pertenece se marca
    como `integrity_compromised=true` porque hay un "hueco" en la cadena
    que invalida la trazabilidad criptográfica para ese episodio.
    """

    __tablename__ = "dead_letters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_uuid: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    episode_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_reason: Mapped[str] = mapped_column(Text, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    moved_to_dlq_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
