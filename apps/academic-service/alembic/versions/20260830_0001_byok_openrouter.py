"""byok_keys: aceptar `openrouter` como provider.

El check `ck_byok_provider` nacio el 2026-05-04 con cuatro proveedores
(`anthropic`, `gemini`, `mistral`, `openai`). Despues se agrego OpenRouter al
codigo —`services/byok.py` y el `Literal` de `routes/byok.py` lo aceptan— y el
constraint nunca se actualizo.

## Que se rompio de verdad

NO fue "OpenRouter no funciona". OpenRouter anduvo todo el tiempo por el
camino del **env fallback**, que no necesita ninguna fila en `byok_keys`.

Lo que se rompio fue el registro de COSTO. Cuando se resuelve por env
fallback, `_ensure_env_fallback_sentinel` crea una fila centinela
(`fingerprint_last4='ENVF'`, `encrypted_value=b""`, `revoked_at=created_at`
para quedar fuera del UNIQUE parcial activo) cuyo unico proposito es servir de
FK para `byok_keys_usage`. Esa fila la rechazaba el constraint:

    CheckViolationError: new row for relation "byok_keys" violates check
    constraint "ck_byok_keys_ck_byok_provider"
    DETAIL: Failing row contains (..., 'openrouter', <bytea vacio>, 'ENVF', ...)

El `except Exception` de `complete.py:520` se comia el error para no tumbar la
respuesta del LLM —que es lo correcto para el alumno— y asi el uso de
OpenRouter quedo **sin auditar durante cuatro meses**. Se descubrio el
2026-08-28 leyendo logs de produccion por un motivo distinto.

Esos cuatro meses **no se pueden backfillear**. Para un repo cuya
justificacion es la auditabilidad academica, ese es el daño real: no un
proveedor caido, un agujero en el registro de costos.

Va en academic-service porque `byok_keys` vive en `academic_main` — la creo
`20260504_0002_add_byok_keys`, en este mismo arbol.

## Sobre el nombre del constraint

Se lo nombra `ck_byok_provider` y en la base figura como
`ck_byok_keys_ck_byok_provider`: la naming convention de
`models/base.py` (`"ck": "ck_%(table_name)s_%(constraint_name)s"`) la aplica
Alembic tanto al DROP como al CREATE. Verificado contra Postgres real, y con
el mismo patron ya aplicado en produccion por `20260604_0001`.

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
    """NO se puede revertir automaticamente. Se documenta por que.

    Un downgrade tendria que sacar las filas con `openrouter` antes de
    restaurar el check viejo, y las tres formas de hacerlo estan cerradas:

    1. **No corre con el rol de produccion.** `byok_keys` tiene FORCE RLS
       (`20260507_0001`) y su policy usa `current_setting('app.current_tenant')`
       SIN el segundo argumento `missing_ok` —a diferencia del helper
       `apply_tenant_rls()`, que si lo pasa—. Como `academic_user`, cualquier
       UPDATE o DELETE sobre la tabla explota con
       `unrecognized configuration parameter "app.current_tenant"`.
    2. **Con un tenant seteado, borra de menos.** La RLS deja fuera las filas
       de los otros tenants, el DELETE se lleva solo las del tenant activo, y
       el `ADD CONSTRAINT` siguiente falla igual por las que quedaron.
    3. **Borrar cascadearia la auditoria.** `byok_keys_usage.key_id` es
       `ON DELETE CASCADE`: borrar los centinelas de openrouter destruye
       exactamente las filas de costo que esta migracion existe para habilitar.
       Verificado: despues del DELETE, `byok_keys_usage` queda en 0.

    En la practica no se revierte un CHECK ensanchado —todos los valores
    viejos siguen siendo validos, asi que dejarlo puesto no rompe nada—. Si
    hiciera falta de verdad, es a mano y como superuser, decidiendo antes que
    se hace con `byok_keys_usage`.

    Fallar explicito es mejor que publicar un downgrade que no anda: el de la
    version anterior de esta migracion pasaba los tests y reventaba en prod.
    """
    raise NotImplementedError(
        "El downgrade de 20260830_0001 no es automatizable: RLS bloquea el "
        "DELETE con el rol de la app, y el ON DELETE CASCADE de byok_keys_usage "
        "destruiria la auditoria de costos. Ver el docstring."
    )
