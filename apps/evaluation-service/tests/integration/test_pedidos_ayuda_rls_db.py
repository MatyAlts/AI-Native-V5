"""`pedidos_ayuda` aislada por tenant, vista como un rol SIN privilegios.

Mismo patron (y misma razon) que `test_reconciliador_rls_db.py`: con `postgres`
—el usuario de la receta de integracion— RLS se bypassea y todo pasa en verde
sin haber verificado nada. El test crea su propio rol NOSUPERUSER/NOBYPASSRLS.

El job "RLS isolation tests" del CI cubre solo `ctr_store`; esta tabla no tiene
otra red que este archivo (y `make check-rls`, que no corre en CI).

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/<db migrada> \
        uv run pytest apps/evaluation-service/tests/integration/test_pedidos_ayuda_rls_db.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: este test necesita Postgres real"
)

_ROL = "eval_pedidos_probe"
_PASS = "eval_pedidos_probe"

_INSERT = (
    "INSERT INTO pedidos_ayuda "
    "(tenant_id, comision_id, student_pseudonym, tarea_practica_id, categoria) "
    "VALUES (:t, :c, :s, :tp, 'otro')"
)


def _dsn_del_rol(dsn: str) -> str:
    cola = dsn.split("@", 1)[1]
    return f"postgresql+asyncpg://{_ROL}:{_PASS}@{cola}"


@pytest_asyncio.fixture
async def rol_sin_privilegios():
    admin = create_async_engine(_DSN)
    async with admin.begin() as c:
        await c.execute(text(f"DROP ROLE IF EXISTS {_ROL}"))
        await c.execute(
            text(f"CREATE ROLE {_ROL} LOGIN PASSWORD '{_PASS}' NOSUPERUSER NOBYPASSRLS")
        )
        await c.execute(text(f"GRANT USAGE ON SCHEMA public TO {_ROL}"))
        await c.execute(text(f"GRANT SELECT, INSERT, UPDATE ON pedidos_ayuda TO {_ROL}"))

    engine = create_async_engine(_dsn_del_rol(_DSN))
    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()
    async with admin.begin() as c:
        await c.execute(text(f"REVOKE ALL ON pedidos_ayuda FROM {_ROL}"))
        await c.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {_ROL}"))
        await c.execute(text(f"DROP ROLE IF EXISTS {_ROL}"))
    await admin.dispose()


@pytest_asyncio.fixture
async def pedido_del_tenant_a():
    """Un pedido del tenant A, sembrado como superusuario (sin FK a entregas)."""
    admin = create_async_engine(_DSN)
    ta, tb = uuid.uuid4(), uuid.uuid4()
    async with admin.begin() as c:
        await c.execute(
            text(_INSERT),
            {
                "t": str(ta),
                "c": str(uuid.uuid4()),
                "s": str(uuid.uuid4()),
                "tp": str(uuid.uuid4()),
            },
        )
    yield ta, tb
    async with admin.begin() as c:
        await c.execute(
            text("DELETE FROM pedidos_ayuda WHERE tenant_id IN (:a, :b)"),
            {"a": str(ta), "b": str(tb)},
        )
    await admin.dispose()


async def _set_tenant(db, tenant: uuid.UUID | None) -> None:
    if tenant is not None:
        await db.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant)}
        )


async def _contar(db) -> int:
    return (await db.execute(text("SELECT count(*) FROM pedidos_ayuda"))).scalar_one()


class TestAislamientoPorTenant:
    async def test_el_rol_de_la_prueba_NO_puede_bypassear_rls(self, rol_sin_privilegios) -> None:
        """Sin esto el resto no prueba nada (ver docstring del modulo)."""
        async with rol_sin_privilegios() as db:
            fila = (
                await db.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
                    {"r": _ROL},
                )
            ).one()
        assert tuple(fila) == (False, False)

    async def test_la_tabla_tiene_rls_enable_y_force(self, rol_sin_privilegios) -> None:
        """FORCE importa: sin el, el dueno de la tabla se saltea la policy."""
        async with rol_sin_privilegios() as db:
            fila = (
                await db.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname = 'pedidos_ayuda'"
                    )
                )
            ).one()
        assert tuple(fila) == (True, True)

    async def test_el_tenant_dueno_ve_su_fila(
        self, rol_sin_privilegios, pedido_del_tenant_a
    ) -> None:
        ta, _ = pedido_del_tenant_a
        async with rol_sin_privilegios() as db, db.begin():
            await _set_tenant(db, ta)
            assert await _contar(db) == 1

    async def test_otro_tenant_no_ve_nada(self, rol_sin_privilegios, pedido_del_tenant_a) -> None:
        _, tb = pedido_del_tenant_a
        async with rol_sin_privilegios() as db, db.begin():
            await _set_tenant(db, tb)
            assert await _contar(db) == 0

    async def test_sin_tenant_no_ve_nada(self, rol_sin_privilegios, pedido_del_tenant_a) -> None:
        async with rol_sin_privilegios() as db, db.begin():
            await _set_tenant(db, None)
            assert await _contar(db) == 0

    async def test_insert_con_tenant_ajeno_falla(
        self, rol_sin_privilegios, pedido_del_tenant_a
    ) -> None:
        ta, tb = pedido_del_tenant_a
        with pytest.raises(DBAPIError):
            async with rol_sin_privilegios() as db, db.begin():
                await _set_tenant(db, tb)
                await db.execute(
                    text(_INSERT),
                    {
                        "t": str(ta),
                        "c": str(uuid.uuid4()),
                        "s": str(uuid.uuid4()),
                        "tp": str(uuid.uuid4()),
                    },
                )
