"""activeia_credenciales + activeia_rubrica_ejercicio

Dos tablas del Epic 2 de `correccion-activeia`.

**`activeia_credenciales`** — la cuenta de Active-IA de cada docente. Es por
DOCENTE y no por tenant porque del lado de Active-IA los `comision_id` y
`rubrica_id` salen de la cuenta logueada: cada tutor ve sólo sus comisiones, y
usar la cuenta de otro devolvería ids que no existen para él.

No va en `byok_keys` (design D5): el scope de esa tabla es tenant/facultad/
materia, y además guarda los últimos 4 caracteres del plaintext en claro
(`ai-gateway/services/byok.py:434`) — con una API key es un fingerprint útil,
con un password humano es una fuga. Acá **no hay columna de fingerprint**.

**`activeia_rubrica_ejercicio`** — el vínculo entre un ejercicio del banco y la
rúbrica que lo corrige del otro lado. `rubrica_hash` guarda el hash de la
rúbrica local al momento de sincronizar, para poder detectar que la de acá
cambió y la de allá quedó vieja. Una rúbrica equivocada no da una nota floja:
corrige otra cosa, y ese número termina en un legajo.

RLS por tenant SOLAMENTE, más `WHERE user_id = :uid` explícito en las queries
(design D6). Una policy que evaluara `app.current_user_id` haría que el
reconciliador del lifespan —que corre sin request y sin headers `X-*`— viera
cero filas SIN tirar error: en Postgres una policy que no matchea filtra en el
SELECT, no falla. Fallo silencioso.

El `FORCE` no es opcional: ya se olvidó una vez en este mismo servicio y tiene
una migration entera dedicada a repararlo.

Revision ID: 20260818_0002
Revises: 20260818_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0002"
down_revision: str | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = ("activeia_credenciales", "activeia_rubrica_ejercicio")


def _rls(tabla: str) -> None:
    op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {tabla}_tenant_isolation ON {tabla} "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def upgrade() -> None:
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())

    if "activeia_credenciales" not in existing:
        op.create_table(
            "activeia_credenciales",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            # BYTEA: `nonce (12) || ciphertext+tag` de AES-256-GCM, cifrado con
            # ACTIVEIA_MASTER_KEY (`platform_ops/crypto.py`). NUNCA se devuelve
            # por API ni se loguea.
            sa.Column("encrypted_password", postgresql.BYTEA(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            # Revocacion en vez de DELETE: saber que un docente tuvo una cuenta
            # conectada y la desconectó es parte de la trazabilidad de quién
            # mandó código de alumnos afuera.
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_ok", sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_activeia_credenciales"),
        )
        op.create_index(
            "ix_activeia_credenciales_tenant_id", "activeia_credenciales", ["tenant_id"]
        )
        op.create_index("ix_activeia_credenciales_user_id", "activeia_credenciales", ["user_id"])
        # UNIQUE PARCIAL: un docente tiene a lo sumo UNA credencial vigente,
        # pero puede acumular las revocadas. Un UNIQUE total impediría volver a
        # conectar la cuenta después de desconectarla.
        op.create_index(
            "uq_activeia_credencial_vigente",
            "activeia_credenciales",
            ["tenant_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("revoked_at IS NULL"),
        )
        _rls("activeia_credenciales")

    if "activeia_rubrica_ejercicio" not in existing:
        op.create_table(
            "activeia_rubrica_ejercicio",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("ejercicio_id", postgresql.UUID(as_uuid=True), nullable=False),
            # Lo que Active-IA devolvió al crear/identificar el recurso. Es un
            # int del otro lado, pero se guarda como texto: la API no garantiza
            # el tipo (12 vs "12") y comparar como texto ya evitó un bug real
            # en la skill de Moodle.
            sa.Column("external_ref", sa.String(length=100), nullable=True),
            sa.Column("rubrica_id", sa.String(length=100), nullable=False),
            # Hash de la rubrica LOCAL al sincronizar. Si la de acá cambia, el
            # hash deja de coincidir y la UI puede decir "desactualizada" en
            # vez de corregir con una rúbrica vieja en silencio.
            sa.Column("rubrica_hash", sa.String(length=64), nullable=True),
            sa.Column("sincronizado_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_activeia_rubrica_ejercicio"),
            sa.UniqueConstraint("tenant_id", "ejercicio_id", name="uq_activeia_rubrica_ejercicio"),
        )
        op.create_index(
            "ix_activeia_rubrica_ejercicio_tenant_id",
            "activeia_rubrica_ejercicio",
            ["tenant_id"],
        )
        op.create_index(
            "ix_activeia_rubrica_ejercicio_ejercicio_id",
            "activeia_rubrica_ejercicio",
            ["ejercicio_id"],
        )
        _rls("activeia_rubrica_ejercicio")


def downgrade() -> None:
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())
    for tabla in _TABLAS:
        if tabla in existing:
            op.execute(f"DROP POLICY IF EXISTS {tabla}_tenant_isolation ON {tabla}")
            op.drop_table(tabla)
