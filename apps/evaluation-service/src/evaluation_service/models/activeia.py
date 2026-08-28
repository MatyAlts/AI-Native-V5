"""Modelos de la integración con Active-IA (Epic 2 de `correccion-activeia`).

Tablas en `academic_main`, mismo criterio que `entregas`/`calificaciones`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from evaluation_service.models.base import Base, TenantMixin, uuid_pk


class ActiveIACredencial(Base, TenantMixin):
    """La cuenta de Active-IA de UN docente.

    Por docente y no por tenant: del otro lado los `comision_id` y
    `rubrica_id` salen de la cuenta logueada, así que la credencial de otro
    devolvería ids que para este docente no existen.

    La RLS de esta tabla es SÓLO por tenant. El aislamiento por usuario va
    como `WHERE user_id = :uid` explícito en cada query — ver design D6: una
    policy sobre `app.current_user_id` haría que el reconciliador del
    lifespan, que corre sin request, viera cero filas sin tirar error.
    """

    __tablename__ = "activeia_credenciales"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # AES-256-GCM (`nonce || ciphertext+tag`). NUNCA se serializa ni se loguea.
    # Sin columna de fingerprint a propósito: guardar los últimos caracteres de
    # un password humano es una fuga, no un identificador.
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        # Parcial: una credencial VIGENTE por docente, pero las revocadas se
        # acumulan. Un UNIQUE total impediría reconectar la cuenta.
        Index(
            "uq_activeia_credencial_vigente",
            "tenant_id",
            "user_id",
            unique=True,
            postgresql_where=sa.text("revoked_at IS NULL"),
        ),
    )


class ActiveIARubricaEjercicio(Base, TenantMixin):
    """El vínculo entre un ejercicio del banco y la rúbrica que lo corrige.

    `rubrica_hash` es el hash de la rúbrica LOCAL al momento de sincronizar.
    Cuando deja de coincidir con la de hoy, la de allá quedó vieja — y una
    rúbrica equivocada no da una nota floja, corrige otra cosa.
    """

    __tablename__ = "activeia_rubrica_ejercicio"

    id: Mapped[uuid.UUID] = uuid_pk()
    ejercicio_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # Texto y no int: la API no garantiza el tipo (12 vs "12"). Comparar como
    # texto ya evitó un bug real de matcheo en la skill de Moodle.
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rubrica_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rubrica_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sincronizado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "ejercicio_id", name="uq_activeia_rubrica_ejercicio"),
    )
