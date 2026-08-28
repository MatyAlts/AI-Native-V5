"""El reconciliador tiene que ver los tenants siendo un rol SIN privilegios.

Este archivo existe porque ningun otro test podia atrapar el bug: **la receta
documentada para correr la suite de integracion usa `postgres`, que es
superusuario y bypassea RLS por construccion**. Con esa conexion, la query del
reconciliador devuelve todas las filas y todo parece andar. En produccion el
runtime conecta como `academic_user` —`CREATE USER` pelado, sin `SUPERUSER` ni
`BYPASSRLS`— y la misma query devuelve CERO, sin tirar error.

Por eso el test **se crea su propio rol** NOSUPERUSER/NOBYPASSRLS en vez de usar
la conexion del fixture. Es el mismo patron que `test_ctr_end_to_end.py` y que
`scripts/setup-rls-test-user.sh`, cuyo comentario ya avisaba que con `postgres`
las policies se bypassean y los tests pasan sin verificar nada.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_reconciliador_rls_db.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: este test necesita Postgres real"
)

_ROL = "eval_rls_probe"
_PASS = "eval_rls_probe"

# La query EXACTA de `correccion_worker.tenants_con_running()`.
_QUERY_DEL_RECONCILIADOR = (
    "SELECT DISTINCT tenant_id FROM correcciones_ia WHERE estado IN ('running', 'pending')"
)


def _dsn_del_rol(dsn: str) -> str:
    """Reescribe el DSN del fixture para entrar con el rol sin privilegios."""
    cola = dsn.split("@", 1)[1]
    return f"postgresql+asyncpg://{_ROL}:{_PASS}@{cola}"


@pytest_asyncio.fixture
async def rol_sin_privilegios():
    """Crea el rol, le da los GRANT minimos, y lo limpia al terminar."""
    admin = create_async_engine(_DSN)
    async with admin.begin() as c:
        await c.execute(text(f"DROP ROLE IF EXISTS {_ROL}"))
        await c.execute(
            text(f"CREATE ROLE {_ROL} LOGIN PASSWORD '{_PASS}' NOSUPERUSER NOBYPASSRLS")
        )
        await c.execute(text(f"GRANT USAGE ON SCHEMA public TO {_ROL}"))
        await c.execute(text(f"GRANT SELECT, INSERT, UPDATE ON correcciones_ia TO {_ROL}"))

    engine = create_async_engine(_dsn_del_rol(_DSN))
    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()
    async with admin.begin() as c:
        await c.execute(text(f"REVOKE ALL ON correcciones_ia FROM {_ROL}"))
        await c.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {_ROL}"))
        await c.execute(text(f"DROP ROLE IF EXISTS {_ROL}"))
    await admin.dispose()


@pytest_asyncio.fixture
async def dos_tenants_colgados():
    """Dos tenants distintos con una correccion `running` cada uno."""
    admin = create_async_engine(_DSN)
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    async with admin.begin() as c:
        for t in (t1, t2):
            await c.execute(
                text(
                    "INSERT INTO correcciones_ia "
                    "(id, tenant_id, entrega_id, orden, disparado_por, rubrica_id, "
                    " estado, artefacto_sha256) "
                    "VALUES (gen_random_uuid(), :t, :e, 1, :u, 'r1', 'running', :h)"
                ),
                {"t": str(t), "e": str(uuid.uuid4()), "u": str(uuid.uuid4()), "h": "f" * 64},
            )
    yield t1, t2
    async with admin.begin() as c:
        for t in (t1, t2):
            await c.execute(text("DELETE FROM correcciones_ia WHERE tenant_id = :t"), {"t": str(t)})
    await admin.dispose()


class TestElReconciliadorVeLosTenants:
    async def test_el_rol_de_la_prueba_NO_puede_bypassear_rls(self, rol_sin_privilegios) -> None:
        """Sin esto el resto del archivo no prueba nada.

        Es la misma trampa que documenta `setup-rls-test-user.sh`: con un rol
        superusuario las policies se bypassean y toda la suite pasa en verde
        sin haber verificado una sola.
        """
        async with rol_sin_privilegios() as db:
            fila = (
                await db.execute(
                    text("SELECT usesuper, usebypassrls FROM pg_user WHERE usename = current_user")
                )
            ).first()
        assert fila is not None
        assert fila[0] is False, "el rol de la prueba no puede ser superusuario"
        assert fila[1] is False, "el rol de la prueba no puede tener BYPASSRLS"

    async def test_ve_los_tenants_con_el_flag_del_reconciliador(
        self, rol_sin_privilegios, dos_tenants_colgados
    ) -> None:
        """La propiedad que sostiene el design D9.

        Sin esto, `tenants_con_running()` devuelve una lista vacia y el
        reconciliador —el de arranque y el periodico— itera sobre nada. Las
        correcciones huerfanas de un deploy quedan girando en el panel del
        docente Y le comen la cuota diaria, que cuenta `pending` y `running`.

        Verificado por reversion: sacando el `set_config` de esta transaccion
        (o borrando la policy `correcciones_ia_reconciliador_lectura` de la
        migracion 20260827_0001), la lista vuelve a salir vacia y este test cae.
        """
        t1, t2 = dos_tenants_colgados
        async with rol_sin_privilegios() as db:
            await db.execute(text("SELECT set_config('app.reconciliador', 'on', true)"))
            vistos = {r[0] for r in (await db.execute(text(_QUERY_DEL_RECONCILIADOR))).all()}

        assert t1 in vistos, "el reconciliador no ve el primer tenant colgado"
        assert t2 in vistos, "el reconciliador no ve el segundo tenant colgado"

    async def test_sin_el_flag_el_aislamiento_por_tenant_sigue_intacto(
        self, rol_sin_privilegios, dos_tenants_colgados
    ) -> None:
        """La policy nueva no puede abrir la puerta para el resto del servicio.

        Fuera de la transaccion del reconciliador, un caller sin
        `app.current_tenant` tiene que seguir viendo CERO — que es justo lo que
        hace que el resto del epic sea seguro.
        """
        async with rol_sin_privilegios() as db:
            vistos = (await db.execute(text(_QUERY_DEL_RECONCILIADOR))).all()
        assert vistos == [], "sin el flag no se puede ver nada de otros tenants"

    async def test_el_flag_habilita_LEER_pero_no_escribir(
        self, rol_sin_privilegios, dos_tenants_colgados
    ) -> None:
        """La policy es `FOR SELECT` a proposito.

        Aunque el flag se filtrara a una transaccion que no deberia tenerlo, lo
        unico que habilita es leer. Las escrituras del reconciliador siguen
        yendo por `tenant_session(tenant_id)`, una por tenant, bajo la policy de
        aislamiento de siempre.
        """
        async with rol_sin_privilegios() as db:
            await db.execute(text("SELECT set_config('app.reconciliador', 'on', true)"))
            res = await db.execute(
                text("UPDATE correcciones_ia SET estado = 'error' WHERE estado = 'running'")
            )
            await db.rollback()
        assert (getattr(res, "rowcount", 0) or 0) == 0, (
            "el flag del reconciliador NO puede habilitar escrituras cross-tenant"
        )
