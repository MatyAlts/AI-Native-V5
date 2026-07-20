"""Test de RLS real en Postgres.

Estos tests son distintos a los de `test_real_datasources.py` porque
verifican el comportamiento de RLS **en Postgres** (no en SQLite, que
no soporta RLS). Se skippean por default; corren cuando se setea
`CTR_STORE_URL_FOR_RLS_TESTS` apuntando a un Postgres de test.

Propiedades verificadas:
  1. Sin SET LOCAL, no se ve ninguna fila (fail-safe).
  2. Con SET LOCAL tenant_a, solo se ven filas de tenant_a.
  3. Intentar INSERT con tenant_id ≠ SET LOCAL falla por WITH CHECK.
  4. Después de ROLLBACK, el SET LOCAL pierde efecto (transacción nueva
     requiere re-setear).

Corrida CI:
    export CTR_STORE_URL_FOR_RLS_TESTS="postgresql+asyncpg://test:test@localhost:5433/ctr_test"
    pytest packages/platform-ops/tests/test_rls_postgres.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

# Saltar el módulo entero si no hay DB Postgres disponible
RLS_TEST_URL = os.environ.get("CTR_STORE_URL_FOR_RLS_TESTS")
pytestmark = pytest.mark.skipif(
    not RLS_TEST_URL,
    reason="CTR_STORE_URL_FOR_RLS_TESTS no seteada; saltando tests de RLS",
)

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "apps/ctr-service/src"))

from platform_ops.real_datasources import set_tenant_rls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(RLS_TEST_URL)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as s:
        yield s
    await engine.dispose()


async def _insert_episode(session, tenant_id: UUID) -> UUID:
    from datetime import UTC, datetime

    from ctr_service.models import Episode

    ep_id = uuid4()
    ep = Episode(
        id=ep_id,
        tenant_id=tenant_id,
        comision_id=uuid4(),
        student_pseudonym=uuid4(),
        problema_id=uuid4(),
        opened_at=datetime.now(UTC),
        prompt_system_hash="p" * 64,
        prompt_system_version="v1.0.0",
        classifier_config_hash="c" * 64,
        curso_config_hash="d" * 64,
        events_count=0,
        last_chain_hash="0" * 64,
    )
    session.add(ep)
    await session.commit()
    return ep_id


# ── Tests RLS ────────────────────────────────────────────────────────


async def test_sin_set_local_no_ve_nada(session: AsyncSession) -> None:
    """Fail-safe: sin `SET LOCAL`, queries devuelven vacío (no explotan)."""
    # Sin set_tenant_rls → current_setting devuelve '' → ninguna fila matchea
    r = await session.execute(text("SELECT COUNT(*) FROM episodes"))
    # No debe fallar; devuelve 0 aunque haya filas en la tabla
    assert r.scalar() == 0


async def test_set_tenant_a_solo_ve_tenant_a(session: AsyncSession) -> None:
    # Necesitamos insertar con bypass RLS o como superuser para poder
    # crear data de prueba con ambos tenants.
    # En un test real usamos SET LOCAL para cada insert:
    async with session.begin():
        await set_tenant_rls(session, TENANT_A)
        ep_a = await _insert_episode(session, TENANT_A)

    async with session.begin():
        await set_tenant_rls(session, TENANT_B)
        ep_b = await _insert_episode(session, TENANT_B)

    # Leer como tenant_a
    async with session.begin():
        await set_tenant_rls(session, TENANT_A)
        r = await session.execute(text("SELECT id FROM episodes"))
        ids = {row[0] for row in r}
    assert ep_a in ids
    assert ep_b not in ids

    # Leer como tenant_b
    async with session.begin():
        await set_tenant_rls(session, TENANT_B)
        r = await session.execute(text("SELECT id FROM episodes"))
        ids = {row[0] for row in r}
    assert ep_b in ids
    assert ep_a not in ids


async def test_insert_con_tenant_mismatch_falla(session: AsyncSession) -> None:
    """WITH CHECK bloquea INSERTs cuyo tenant_id no coincide con SET LOCAL."""
    async with session.begin():
        await set_tenant_rls(session, TENANT_A)
        # Intentar insertar con tenant_id=TENANT_B — la policy debe rechazarlo
        with pytest.raises(Exception):
            await _insert_episode(session, TENANT_B)


async def test_set_local_solo_dura_la_transaccion(session: AsyncSession) -> None:
    """SET LOCAL se resetea al hacer COMMIT/ROLLBACK — transacción siguiente
    requiere re-setear."""
    async with session.begin():
        await set_tenant_rls(session, TENANT_A)
        r = await session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        assert r.scalar() == str(TENANT_A)

    # Nueva transacción — current_setting debe estar vacío
    async with session.begin():
        r = await session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        assert r.scalar() in ("", None)
