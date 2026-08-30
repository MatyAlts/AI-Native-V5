"""byok_keys: aceptar `openrouter` como provider.

El check `ck_byok_provider` nacio el 2026-05-04 con cuatro proveedores
(`anthropic`, `gemini`, `mistral`, `openai`). Despues se agrego OpenRouter al
codigo —`services/byok.py:422` lo valida y lo acepta— y el constraint nunca se
actualizo. El codigo dice que si y la base dice que no.

El sintoma es traicionero porque NO rompe el arranque. El ai-gateway siembra
la key desde la variable de entorno en cada boot (`fingerprint_last4='ENVF'`),
la base la rechaza con `CheckViolationError`, se loguea el traceback y el
servicio sigue andando. Resultado: OpenRouter configurado, aparentemente
funcionando, y sin una sola key guardada. Encontrado el 2026-08-28 leyendo los
logs de produccion por otro motivo.

Va en academic-service porque `byok_keys` vive en `academic_main` — la creo
`20260504_0002_add_byok_keys`, en este mismo arbol de migraciones.

Revision ID: 20260830_0001
Revises: 20260723_0001
"""

from __future__ import annotations

from alembic import op

revision = "20260830_0001"
down_revision = "20260723_0001"
branch_labels = None
depends_on = None

# El orden alfabetico no es cosmetico: es el mismo de `services/byok.py:422`,
# para que comparar las dos listas sea leerlas en paralelo.
PROVIDERS_NUEVOS = "'anthropic', 'gemini', 'mistral', 'openai', 'openrouter'"
PROVIDERS_VIEJOS = "'anthropic', 'gemini', 'mistral', 'openai'"


def upgrade() -> None:
    op.drop_constraint("ck_byok_provider", "byok_keys", type_="check")
    op.create_check_constraint("ck_byok_provider", "byok_keys", f"provider IN ({PROVIDERS_NUEVOS})")


def downgrade() -> None:
    # Al volver atras, cualquier fila con `openrouter` haria fallar la creacion
    # del constraint viejo. Se revocan en vez de borrarse: `byok_keys` es
    # append-only por diseño (el UNIQUE parcial es `WHERE revoked_at IS NULL`),
    # y borrar una key es perder el rastro de que existio.
    op.execute(
        "UPDATE byok_keys SET revoked_at = NOW() "
        "WHERE provider = 'openrouter' AND revoked_at IS NULL"
    )
    op.execute("DELETE FROM byok_keys WHERE provider = 'openrouter'")
    op.drop_constraint("ck_byok_provider", "byok_keys", type_="check")
    op.create_check_constraint("ck_byok_provider", "byok_keys", f"provider IN ({PROVIDERS_VIEJOS})")
