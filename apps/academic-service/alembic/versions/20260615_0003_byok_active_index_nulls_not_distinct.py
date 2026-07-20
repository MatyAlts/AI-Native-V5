"""byok_keys: uq_byok_keys_active con NULLS NOT DISTINCT

Revision ID: 20260615_0003
Revises: 20260615_0002
Create Date: 2026-06-15

NB-2b (gate E2E): el indice unico parcial `uq_byok_keys_active` sobre
`(tenant_id, scope_type, scope_id, provider) WHERE revoked_at IS NULL` NO
usaba `NULLS NOT DISTINCT`. En Postgres los NULL son distintos en indices
unicos por default, por lo que para `scope_type='tenant'` (donde
`scope_id IS NULL`) se podian crear MULTIPLES keys activas del mismo provider.

Eso viola el invariante "una sola key activa por
(tenant, scope_type, scope_id, provider)" y hace que el resolver de la rama
tenant (`scalar_one_or_none()` en `ai-gateway/.../services/byok.py`) tire
500 `MultipleResultsFound`.

Fix (Postgres 16+): recrear el indice con `NULLS NOT DISTINCT` para que los
NULL de `scope_id` cuenten como iguales y el UNIQUE parcial cubra tambien el
scope 'tenant'.

Pasos del upgrade:
1. Dedupe defensivo: por cada grupo con >1 fila activa, dejar activa solo la
   mas reciente (`created_at DESC`, desempate `id DESC`) y soft-revocar el
   resto (`revoked_at = now()`). Necesario para que la creacion del indice
   unico no falle si ya hay duplicados. El `PARTITION BY` agrupa los NULL de
   `scope_id` juntos (las window functions tratan NULL como iguales para
   particionado), que es exactamente el caso que este fix ataca.
2. DROP del indice viejo + CREATE identico con `NULLS NOT DISTINCT`.

El downgrade revierte al indice sin `NULLS NOT DISTINCT` (el dedupe no se
revierte: soft-revoke es append-safe y no se puede saber que fila revocar).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260615_0003"
down_revision: str | None = "20260615_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Dedupe defensivo: soft-revocar duplicados activos, dejando la mas
    #    reciente por grupo. PARTITION BY agrupa NULL scope_id juntos.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY tenant_id, scope_type, scope_id, provider
                    ORDER BY created_at DESC, id DESC
                ) AS rn
            FROM byok_keys
            WHERE revoked_at IS NULL
        )
        UPDATE byok_keys AS b
        SET revoked_at = now()
        FROM ranked
        WHERE b.id = ranked.id
          AND ranked.rn > 1
        """
    )

    # 2. Recrear el indice con NULLS NOT DISTINCT (Postgres 16+).
    op.drop_index("uq_byok_keys_active", table_name="byok_keys")
    op.execute(
        "CREATE UNIQUE INDEX uq_byok_keys_active "
        "ON byok_keys (tenant_id, scope_type, scope_id, provider) "
        "NULLS NOT DISTINCT "
        "WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    # Volver al indice sin NULLS NOT DISTINCT (comportamiento default previo).
    # El dedupe del upgrade NO se revierte: el soft-revoke es informacion
    # perdida (no sabemos que fila re-activar sin reintroducir el bug).
    op.drop_index("uq_byok_keys_active", table_name="byok_keys")
    op.execute(
        "CREATE UNIQUE INDEX uq_byok_keys_active "
        "ON byok_keys (tenant_id, scope_type, scope_id, provider) "
        "WHERE revoked_at IS NULL"
    )
