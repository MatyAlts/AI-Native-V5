"""dedup_classifications_rls_policy

Revision ID: 20260905_0005
Revises: 20260904_0004
Create Date: 2026-09-05

Elimina la policy RLS DUPLICADA sobre ``classifications`` (P-14).

Hoy la tabla tiene DOS policies permissive ``FOR ALL`` que aplican la MISMA
regla de aislamiento multi-tenant (``tenant_id`` == ``app.current_tenant``),
solo que escritas distinto:

  - ``tenant_isolation``                 -> creada por ``apply_tenant_rls()``
    en la migracion 20260901_0001. Es el patron CANONICO del schema (misma
    policy que tienen todas las demas tablas con ``tenant_id``, incluida
    ``interrater_ratings``). USING: ``tenant_id = current_setting(...)::uuid``.
  - ``tenant_isolation_classifications`` -> agregada por la migracion
    20260902_0002 SIN dropear la anterior (re-CREATE sin DROP previo).
    USING/WITH CHECK: ``tenant_id::text = current_setting(...)``.

Postgres evalua TODAS las policies permissive por query y las combina con OR.
Como ambas expresan la MISMA condicion, el OR es redundante: no cambia el
resultado (no debilita ni fortalece el aislamiento) pero agrega overhead por
query y confunde el modelo de seguridad.

Esta migracion deja UNA sola policy canonica (``tenant_isolation``) y borra la
redundante. NO toca ENABLE/FORCE ROW LEVEL SECURITY: el aislamiento sigue
forzado por ``tenant_isolation`` (FOR ALL: su USING aplica tambien como
WITH CHECK a los writes). Idempotente via ``DROP POLICY IF EXISTS``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260905_0005"
down_revision: str | None = "20260904_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Borra la policy redundante; conserva la canonica `tenant_isolation`
    # creada por apply_tenant_rls() (migracion 20260901_0001).
    op.execute("DROP POLICY IF EXISTS tenant_isolation_classifications ON classifications")


def downgrade() -> None:
    # Recrea la policy redundante para restaurar el estado previo. Misma
    # semantica que la canonica -> no cambia el aislamiento, solo re-agrega
    # la redundancia OR.
    op.execute("""
        CREATE POLICY tenant_isolation_classifications
        ON classifications
        FOR ALL
        USING (
            tenant_id::text = current_setting('app.current_tenant', true)
        )
        WITH CHECK (
            tenant_id::text = current_setting('app.current_tenant', true)
        )
    """)
