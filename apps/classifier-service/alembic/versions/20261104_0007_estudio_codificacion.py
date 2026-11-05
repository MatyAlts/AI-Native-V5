"""estudio_codificacion

Revision ID: 20261104_0007
Revises: 20260906_0006
Create Date: 2026-11-04

Tablas del estudio de codificación ciega (change cibse-codificacion-ciega,
design D1). ADITIVA: crea nueve tablas nuevas y no toca `classifications`,
`classification_reviews` ni `interrater_ratings`.

Todo lo exclusivo de Postgres vive solo acá, no en la metadata del modelo
(varios tests de otros paquetes hacen `create_all` sobre SQLite):

- RLS por tenant con `apply_tenant_rls` en cada tabla (ADR-001).
- Unicidad PARCIAL de membresía activa por `(estudio_id, lower(email))`.
- FK circular `estudio_codificacion.codebook_vigente_id -> codebook_version.id`.
- Triggers de inmutabilidad (design D2), al final de `upgrade()`: de fila para
  UPDATE/DELETE y, en cada tabla inmutable, uno de SENTENCIA `BEFORE TRUNCATE`
  (TRUNCATE no dispara los de fila y RLS no lo filtra: vaciaría todos los
  tenants; verify-1, F5).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261104_0007"
down_revision: str | None = "20260906_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLAS = (
    "estudio_codificacion",
    "estudio_membresia",
    "estudio_muestra",
    "estudio_enunciado",
    "codebook_version",
    "estudio_ancla",
    "estudio_etiqueta",
    "estudio_etiqueta_historial",
    "entrenamiento_respuesta",
)


def _uuid(name: str, *, nullable: bool = False, **kw) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable, **kw)


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _evidencia_fija() -> list[sa.Column]:
    """Evidencia fija por ítem (D4b) más los ids de enunciado (D14)."""
    return [
        _uuid("episode_id"),
        sa.Column("seq_tope", sa.Integer, nullable=False),
        sa.Column("chain_hash_tope", sa.String(64), nullable=False),
        sa.Column("events_count_carga", sa.Integer, nullable=False),
        sa.Column("last_chain_hash_carga", sa.String(64), nullable=False),
        sa.Column("estado_carga", sa.String(20), nullable=False),
        _uuid("problema_id"),
        _uuid("ejercicio_id", nullable=True),
    ]


def _respuesta() -> list[sa.Column]:
    """Formato de respuesta de design D9 (etiqueta y respuesta de entrenamiento)."""
    return [
        sa.Column("traza_version", sa.String(20), nullable=False),
        sa.Column(
            "respuestas",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("regimen", sa.String(40), nullable=True),
        sa.Column("regimen_regla", sa.String(40), nullable=True),
        sa.Column("regimen_propuesto", sa.String(40), nullable=True),
        sa.Column("es_frontera", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("confianza", sa.String(40), nullable=True),
        sa.Column("notas", sa.Text, nullable=True),
    ]


def upgrade() -> None:
    uuid_pk = {"server_default": sa.text("gen_random_uuid()")}

    op.create_table(
        "estudio_codificacion",
        _uuid("id", **uuid_pk),
        _uuid("tenant_id"),
        sa.Column("clave", sa.String(41), nullable=False),
        sa.Column("titulo", sa.Text, nullable=False),
        _uuid("codebook_vigente_id", nullable=True),
        sa.Column("muestra_sha256", sa.String(64), nullable=True),
        _ts("muestra_cargada_at", nullable=True),
        sa.Column("traza_version", sa.String(20), nullable=False),
        _uuid("created_by"),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_estudio_codificacion"),
        sa.UniqueConstraint("tenant_id", "clave", name="uq_estudio_codificacion_clave"),
    )

    op.create_table(
        "estudio_membresia",
        _uuid("id", **uuid_pk),
        _uuid("tenant_id"),
        _uuid("estudio_id"),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("alias", sa.String(20), nullable=False),
        sa.Column("semilla", sa.BigInteger, nullable=False),
        _uuid("user_id", nullable=True),
        _ts("cerrada_at", nullable=True),
        _ts("revocada_at", nullable=True),
        _uuid("created_by"),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_estudio_membresia"),
        sa.ForeignKeyConstraint(
            ["estudio_id"],
            ["estudio_codificacion.id"],
            name="fk_estudio_membresia_estudio_id_estudio_codificacion",
        ),
        sa.UniqueConstraint("estudio_id", "alias", name="uq_estudio_membresia_alias"),
        sa.UniqueConstraint("estudio_id", "semilla", name="uq_estudio_membresia_semilla"),
        sa.CheckConstraint(
            "rol IN ('investigador', 'codificador')", name="ck_estudio_membresia_rol"
        ),
    )
    # D3: una sola membresía ACTIVA por (estudio, email), sin distinguir mayúsculas.
    op.execute(
        "CREATE UNIQUE INDEX uq_estudio_membresia_activa_email "
        "ON estudio_membresia (estudio_id, lower(email)) WHERE revocada_at IS NULL"
    )

    op.create_table(
        "estudio_muestra",
        _uuid("item_id", **uuid_pk),
        _uuid("tenant_id"),
        _uuid("estudio_id"),
        *_evidencia_fija(),
        _ts("cargado_at"),
        sa.PrimaryKeyConstraint("item_id", name="pk_estudio_muestra"),
        sa.ForeignKeyConstraint(
            ["estudio_id"],
            ["estudio_codificacion.id"],
            name="fk_estudio_muestra_estudio_id_estudio_codificacion",
        ),
        sa.UniqueConstraint("estudio_id", "episode_id", name="uq_estudio_muestra_episodio"),
    )

    op.create_table(
        "estudio_enunciado",
        _uuid("id", **uuid_pk),
        _uuid("tenant_id"),
        _uuid("estudio_id"),
        sa.Column("fuente", sa.String(12), nullable=False),
        _uuid("fuente_id"),
        sa.Column("archivo_sha256", sa.String(64), nullable=False),
        _uuid("cargado_por"),
        _ts("cargado_at"),
        sa.Column("contenido_original_md", sa.Text, nullable=False),
        sa.Column("sha256_original", sa.String(64), nullable=False),
        sa.Column("contenido_mostrado_md", sa.Text, nullable=True),
        sa.Column("sha256_mostrado", sa.String(64), nullable=True),
        sa.Column(
            "alertas", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        _uuid("revisado_por", nullable=True),
        _ts("revisado_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_estudio_enunciado"),
        sa.ForeignKeyConstraint(
            ["estudio_id"],
            ["estudio_codificacion.id"],
            name="fk_estudio_enunciado_estudio_id_estudio_codificacion",
        ),
        sa.UniqueConstraint(
            "estudio_id", "fuente", "fuente_id", name="uq_estudio_enunciado_fuente"
        ),
        sa.CheckConstraint("fuente IN ('tp', 'ejercicio')", name="ck_estudio_enunciado_fuente"),
    )

    op.create_table(
        "codebook_version",
        _uuid("id", **uuid_pk),
        _uuid("tenant_id"),
        _uuid("estudio_id"),
        sa.Column("etiqueta", sa.String(40), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, server_default="borrador"),
        sa.Column("contenido_md", sa.Text, nullable=False, server_default=""),
        sa.Column("esquema_formulario", postgresql.JSONB, nullable=True),
        sa.Column("contenido_sha256", sa.String(64), nullable=True),
        _ts("congelada_at", nullable=True),
        _uuid("congelada_por", nullable=True),
        _uuid("created_by"),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_codebook_version"),
        sa.ForeignKeyConstraint(
            ["estudio_id"],
            ["estudio_codificacion.id"],
            name="fk_codebook_version_estudio_id_estudio_codificacion",
        ),
        sa.UniqueConstraint("estudio_id", "etiqueta", name="uq_codebook_version_etiqueta"),
        sa.CheckConstraint(
            "estado IN ('borrador', 'congelada')", name="ck_codebook_version_estado"
        ),
    )
    op.create_foreign_key(
        "fk_estudio_codificacion_codebook_vigente_id_codebook_version",
        "estudio_codificacion",
        "codebook_version",
        ["codebook_vigente_id"],
        ["id"],
    )

    op.create_table(
        "estudio_ancla",
        _uuid("item_id", **uuid_pk),
        _uuid("tenant_id"),
        _uuid("estudio_id"),
        _uuid("codebook_version_id"),
        *_evidencia_fija(),
        sa.Column("uso", sa.String(12), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("respuesta_esperada", postgresql.JSONB, nullable=False),
        sa.Column("explicacion_md", sa.Text, nullable=False, server_default=""),
        sa.Column("consensuado_por", sa.Text, nullable=False, server_default=""),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("item_id", name="pk_estudio_ancla"),
        sa.ForeignKeyConstraint(
            ["estudio_id"],
            ["estudio_codificacion.id"],
            name="fk_estudio_ancla_estudio_id_estudio_codificacion",
        ),
        sa.ForeignKeyConstraint(
            ["codebook_version_id"],
            ["codebook_version.id"],
            name="fk_estudio_ancla_codebook_version_id_codebook_version",
        ),
        sa.CheckConstraint("uso IN ('ejemplo', 'practica')", name="ck_estudio_ancla_uso"),
    )

    op.create_table(
        "estudio_etiqueta",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        _uuid("tenant_id"),
        _uuid("membresia_id"),
        _uuid("muestra_item_id"),
        _uuid("codebook_version_id"),
        *_respuesta(),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_estudio_etiqueta"),
        sa.ForeignKeyConstraint(
            ["membresia_id"],
            ["estudio_membresia.id"],
            name="fk_estudio_etiqueta_membresia_id_estudio_membresia",
        ),
        sa.ForeignKeyConstraint(
            ["muestra_item_id"],
            ["estudio_muestra.item_id"],
            name="fk_estudio_etiqueta_muestra_item_id_estudio_muestra",
        ),
        sa.ForeignKeyConstraint(
            ["codebook_version_id"],
            ["codebook_version.id"],
            name="fk_estudio_etiqueta_codebook_version_id_codebook_version",
        ),
        sa.UniqueConstraint("membresia_id", "muestra_item_id", name="uq_estudio_etiqueta_item"),
    )

    op.create_table(
        "estudio_etiqueta_historial",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        _uuid("tenant_id"),
        sa.Column("etiqueta_id", sa.BigInteger, nullable=False),
        _uuid("membresia_id"),
        _uuid("muestra_item_id"),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        _ts("guardado_at"),
        sa.PrimaryKeyConstraint("id", name="pk_estudio_etiqueta_historial"),
        sa.ForeignKeyConstraint(
            ["etiqueta_id"],
            ["estudio_etiqueta.id"],
            name="fk_estudio_etiqueta_historial_etiqueta_id_estudio_etiqueta",
        ),
    )

    op.create_table(
        "entrenamiento_respuesta",
        sa.Column("id", sa.BigInteger, nullable=False, autoincrement=True),
        _uuid("tenant_id"),
        _uuid("membresia_id"),
        _uuid("ancla_id"),
        _uuid("codebook_version_id"),
        *_respuesta(),
        _ts("respondida_at"),
        sa.PrimaryKeyConstraint("id", name="pk_entrenamiento_respuesta"),
        sa.ForeignKeyConstraint(
            ["membresia_id"],
            ["estudio_membresia.id"],
            name="fk_entrenamiento_respuesta_membresia_id_estudio_membresia",
        ),
        sa.ForeignKeyConstraint(
            ["ancla_id"],
            ["estudio_ancla.item_id"],
            name="fk_entrenamiento_respuesta_ancla_id_estudio_ancla",
        ),
        sa.ForeignKeyConstraint(
            ["codebook_version_id"],
            ["codebook_version.id"],
            name="fk_entrenamiento_respuesta_codebook_version_id_codebook_version",
        ),
    )

    for tabla in TABLAS:
        op.create_index(f"ix_{tabla}_tenant_id", tabla, ["tenant_id"])
    op.create_index("ix_estudio_membresia_estudio_id", "estudio_membresia", ["estudio_id"])
    op.create_index("ix_estudio_muestra_estudio_id", "estudio_muestra", ["estudio_id"])
    op.create_index("ix_estudio_enunciado_estudio_id", "estudio_enunciado", ["estudio_id"])
    op.create_index("ix_codebook_version_estudio_id", "codebook_version", ["estudio_id"])
    op.create_index("ix_estudio_ancla_estudio_id", "estudio_ancla", ["estudio_id"])
    op.create_index(
        "ix_estudio_ancla_codebook_version_id", "estudio_ancla", ["codebook_version_id"]
    )
    op.create_index("ix_estudio_etiqueta_membresia_id", "estudio_etiqueta", ["membresia_id"])
    op.create_index("ix_estudio_etiqueta_muestra_item_id", "estudio_etiqueta", ["muestra_item_id"])
    op.create_index(
        "ix_estudio_etiqueta_historial_etiqueta_id", "estudio_etiqueta_historial", ["etiqueta_id"]
    )
    op.create_index(
        "ix_entrenamiento_respuesta_membresia_id", "entrenamiento_respuesta", ["membresia_id"]
    )
    op.create_index("ix_entrenamiento_respuesta_ancla_id", "entrenamiento_respuesta", ["ancla_id"])

    for tabla in TABLAS:
        op.execute(f"SELECT apply_tenant_rls('{tabla}')")

    _crear_triggers()


# ── Inmutabilidad (design D2) ────────────────────────────────────────────────
# Todos los mensajes llevan la marca `estudio_inmutable` (los tests la buscan).
# SQLSTATE 'P0001' (raise_exception, el default de RAISE).

_EVIDENCIA_FIJA = (
    "item_id",
    "estudio_id",
    "episode_id",
    "seq_tope",
    "chain_hash_tope",
    "events_count_carga",
    "last_chain_hash_carga",
    "estado_carga",
    "problema_id",
    "ejercicio_id",
)

_FUNCIONES = {
    # UPDATE o DELETE de una versión ya congelada. El paso borrador -> congelada
    # pasa porque OLD.estado todavía es 'borrador'.
    "estudio_codebook_congelado": """
        BEGIN
            IF OLD.estado = 'congelada' THEN
                RAISE EXCEPTION 'estudio_inmutable: codebook_version % congelada', OLD.id;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
    """,
    # INSERT, UPDATE o DELETE de un ancla cuya versión (nueva o vieja) está
    # congelada. Falla CERRADO si la versión no se ve (RLS de otro tenant): la
    # FK garantiza que existe, así que no verla es un pedido cruzado.
    "estudio_ancla_de_congelada": """
        DECLARE
            v_estado text;
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT estado INTO v_estado FROM codebook_version
                    WHERE id = NEW.codebook_version_id;
                IF v_estado IS NULL OR v_estado = 'congelada' THEN
                    RAISE EXCEPTION 'estudio_inmutable: ancla de version congelada o no visible %',
                        NEW.codebook_version_id;
                END IF;
            END IF;
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT estado INTO v_estado FROM codebook_version
                    WHERE id = OLD.codebook_version_id;
                IF v_estado IS NULL OR v_estado = 'congelada' THEN
                    RAISE EXCEPTION 'estudio_inmutable: ancla de version congelada o no visible %',
                        OLD.codebook_version_id;
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
    """,
    # Append-only: historial de etiquetas y respuestas de entrenamiento.
    "estudio_append_only": """
        BEGIN
            RAISE EXCEPTION 'estudio_inmutable: % es append-only (% rechazado)',
                TG_TABLE_NAME, TG_OP;
        END;
    """,
    # Evidencia fija e ids de enunciado de muestra y anclas: sin UPDATE nunca.
    "estudio_evidencia_fija": """
        BEGIN
            IF ROW("""
    + ", ".join(f"OLD.{c}" for c in _EVIDENCIA_FIJA)
    + """) IS DISTINCT FROM ROW("""
    + ", ".join(f"NEW.{c}" for c in _EVIDENCIA_FIJA)
    + """) THEN
                RAISE EXCEPTION 'estudio_inmutable: evidencia fija de % no se actualiza',
                    TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
    """,
    # TRUNCATE de una tabla inmutable: nunca (trigger de SENTENCIA, verify-1 F5).
    # El nombre de la tabla va en el mensaje: los tests lo exigen para que el
    # CASCADE no tape una tabla sin trigger propio.
    "estudio_sin_truncate": """
        BEGIN
            RAISE EXCEPTION 'estudio_inmutable: TRUNCATE de % rechazado', TG_TABLE_NAME;
        END;
    """,
    # Enunciado revisado: ni UPDATE ni DELETE. Sin revisar se puede reemplazar
    # (D14) y la revisión misma es un UPDATE con OLD.revisado_at nulo.
    "estudio_enunciado_revisado": """
        BEGIN
            IF OLD.revisado_at IS NOT NULL THEN
                RAISE EXCEPTION 'estudio_inmutable: enunciado % ya revisado', OLD.id;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
    """,
}

# (nombre del trigger, tabla, eventos, función)
_TRIGGERS = (
    (
        "trg_codebook_version_congelada",
        "codebook_version",
        "UPDATE OR DELETE",
        "estudio_codebook_congelado",
    ),
    (
        "trg_estudio_ancla_congelada",
        "estudio_ancla",
        "INSERT OR UPDATE OR DELETE",
        "estudio_ancla_de_congelada",
    ),
    (
        "trg_estudio_etiqueta_historial_append_only",
        "estudio_etiqueta_historial",
        "UPDATE OR DELETE",
        "estudio_append_only",
    ),
    (
        "trg_entrenamiento_respuesta_append_only",
        "entrenamiento_respuesta",
        "UPDATE OR DELETE",
        "estudio_append_only",
    ),
    ("trg_estudio_muestra_evidencia_fija", "estudio_muestra", "UPDATE", "estudio_evidencia_fija"),
    ("trg_estudio_ancla_evidencia_fija", "estudio_ancla", "UPDATE", "estudio_evidencia_fija"),
    (
        "trg_estudio_enunciado_revisado",
        "estudio_enunciado",
        "UPDATE OR DELETE",
        "estudio_enunciado_revisado",
    ),
)


# Tablas que D2 declara inmutables (en todo o en parte): ninguna admite TRUNCATE.
_TABLAS_SIN_TRUNCATE = (
    "codebook_version",
    "estudio_ancla",
    "estudio_etiqueta_historial",
    "entrenamiento_respuesta",
    "estudio_muestra",
    "estudio_enunciado",
)


def _trigger_truncate(tabla: str) -> str:
    return f"trg_{tabla}_sin_truncate"


def _crear_triggers() -> None:
    for nombre, cuerpo in _FUNCIONES.items():
        op.execute(
            f"CREATE FUNCTION {nombre}() RETURNS trigger LANGUAGE plpgsql AS $fn${cuerpo}$fn$"
        )
    for trigger, tabla, eventos, funcion in _TRIGGERS:
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE {eventos} ON {tabla} "
            f"FOR EACH ROW EXECUTE FUNCTION {funcion}()"
        )
    for tabla in _TABLAS_SIN_TRUNCATE:
        op.execute(
            f"CREATE TRIGGER {_trigger_truncate(tabla)} BEFORE TRUNCATE ON {tabla} "
            "FOR EACH STATEMENT EXECUTE FUNCTION estudio_sin_truncate()"
        )


def downgrade() -> None:
    for tabla in _TABLAS_SIN_TRUNCATE:
        op.execute(f"DROP TRIGGER IF EXISTS {_trigger_truncate(tabla)} ON {tabla}")
    for trigger, tabla, _eventos, _funcion in _TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {tabla}")
    for nombre in _FUNCIONES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}()")
    op.drop_constraint(
        "fk_estudio_codificacion_codebook_vigente_id_codebook_version",
        "estudio_codificacion",
        type_="foreignkey",
    )
    for tabla in reversed(TABLAS):
        op.drop_table(tabla)
