"""correcciones_ia — el resultado de una corrección asistida, por ejercicio

Tabla del Epic 3 de `correccion-activeia`.

**FK a `entregas` SIN unique**: una entrega tiene N ejercicios y cada uno se
corrige por separado (design D1). Un unique por entrega colapsaría eso.

**`nota_100` es nullable, y eso es la propiedad central de la tabla.** Un
fallo de infraestructura —Gemini saturado, timeout, el servicio caído— NUNCA
puede convertirse en una nota. Si `nota_100` fuera NOT NULL, la única forma de
guardar una fila fallida sería inventarle un cero, y un cero que en realidad
significa "el servicio no respondió" termina en el legajo de una persona. Por
eso el estado terminal de un fallo es `estado='error'` con `error_code` y
`nota_100 IS NULL`.

**`artefacto_sha256`** congela QUÉ código se corrigió. Junto con
`(entrega_id, tp_ejercicio_id, rubrica_id)` forma la clave de idempotencia: si
el alumno no re-entregó y la rúbrica no cambió, re-disparar devuelve la
corrección que ya existe en vez de pagar otra corrida.

**`tests_snapshot`** guarda el resultado de correr los test cases en el
sandbox al momento de corregir. Se re-ejecutan y no se leen de la corrida
vieja porque el detalle de aquélla murió en Redis a los 600 segundos — y
además re-ejecutar hace la corrección reproducible.

RLS `ENABLE` + `FORCE` + policy por tenant, misma receta que las anteriores.

Revision ID: 20260818_0003
Revises: 20260818_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0003"
down_revision: str | None = "20260818_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if "correcciones_ia" in set(sa.inspect(conn).get_table_names()):
        return

    op.create_table(
        "correcciones_ia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entrega_id", postgresql.UUID(as_uuid=True), nullable=False),
        # El ejercicio dentro del TP. Nullable para la TP monolítica, que no
        # tiene filas en `tp_ejercicios`.
        sa.Column("tp_ejercicio_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False),
        # Quién apretó el botón. La corrección corre con SU cuenta de
        # Active-IA y contra SU cuota, así que sin esto no se puede ni contar
        # la cuota ni saber quién mandó el código de un alumno afuera.
        sa.Column("disparado_por", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rubrica_id", sa.String(length=100), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="pending"),
        # NULLABLE A PROPÓSITO: ver el docstring. Sin nota no hay nota.
        sa.Column("nota_100", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "desglose", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "tests_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("artefacto_sha256", sa.String(length=64), nullable=False),
        # `error_code` es el de Active-IA (ej. GEMINI_OVERLOADED) o el nuestro.
        # Se guarda crudo para poder distinguir después "el servicio estaba
        # saturado" de "esta entrega quedó atascada" — que se resuelven al
        # revés y confundirlas ya costó dos días de reintentos inútiles.
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        # `external_entrega_id` es el id que Active-IA le dio a la entrega
        # subida. Sin él, un reintento tras un timeout no puede retomar la que
        # ya está arriba y la sube de nuevo (y la cobra de nuevo).
        sa.Column("external_entrega_id", sa.String(length=100), nullable=True),
        sa.Column("external_correccion_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_correcciones_ia"),
        sa.ForeignKeyConstraint(
            ["entrega_id"],
            ["entregas.id"],
            name="fk_correcciones_ia_entrega",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "estado IN ('pending', 'running', 'done', 'error')",
            name="ck_correcciones_ia_estado",
        ),
        # Una nota sólo puede existir si la corrección terminó bien. Es la
        # propiedad de arriba, hecha constraint: sin esto, un bug futuro podría
        # dejar una fila en `error` con nota y nadie se enteraría.
        sa.CheckConstraint(
            "(estado = 'done' AND nota_100 IS NOT NULL) OR (estado <> 'done' AND nota_100 IS NULL)",
            name="ck_correcciones_ia_nota_solo_si_done",
        ),
        sa.CheckConstraint(
            "nota_100 IS NULL OR (nota_100 >= 0 AND nota_100 <= 100)",
            name="ck_correcciones_ia_nota_rango",
        ),
        # Idempotencia: mismo alumno + mismo ejercicio + misma rúbrica + mismo
        # código = la misma corrección. Un doble click no paga dos veces.
        sa.UniqueConstraint(
            "tenant_id",
            "entrega_id",
            "orden",
            "rubrica_id",
            "artefacto_sha256",
            name="uq_correccion_ia_idempotencia",
        ),
    )
    op.create_index("ix_correcciones_ia_tenant_id", "correcciones_ia", ["tenant_id"])
    op.create_index("ix_correcciones_ia_entrega_id", "correcciones_ia", ["entrega_id"])
    # Para la cuota diaria por docente y para el reconciliador del lifespan.
    op.create_index(
        "ix_correcciones_ia_disparado_por_fecha",
        "correcciones_ia",
        ["tenant_id", "disparado_por", "created_at"],
    )
    op.create_index("ix_correcciones_ia_estado", "correcciones_ia", ["estado"])

    op.execute("ALTER TABLE correcciones_ia ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE correcciones_ia FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY correcciones_ia_tenant_isolation ON correcciones_ia "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "correcciones_ia" in set(sa.inspect(conn).get_table_names()):
        op.execute("DROP POLICY IF EXISTS correcciones_ia_tenant_isolation ON correcciones_ia")
        op.drop_table("correcciones_ia")
