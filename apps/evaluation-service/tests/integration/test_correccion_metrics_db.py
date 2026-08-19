"""El desenlace que se mide es el que quedó en la fila (tareas 6.2 y 6.3).

Una métrica que nadie verifica es peor que no tenerla: se mira el panel, se ve
plano, y se concluye que no está pasando nada. Estos tests fijan las tres
propiedades de las que depende que el panel diga la verdad.

**1. `in_flight` tiene que bajar SIEMPRE.** Sube al disparar y baja en el
`finally`. Si sólo bajara en el camino feliz, cada corrección fallida dejaría
el contador un punto más arriba para siempre, y el indicador de saturación —el
que se mira cuando el sistema parece colgado— mentiría justo cuando hace falta.

**2. El outcome sale de la FILA, no de una variable.** Hay caminos que cierran
la corrección desde adentro (`marcar_error` dentro de `_cerrar_con_resultado`)
sin volver con un valor de retorno. Una variable local se desincronizaría del
estado real precisamente en los caminos de error, que son los que se miden.

**3. Infra y rechazo se cuentan por separado.** `GEMINI_OVERLOADED` es "Active-IA
se cayó" y `HTTP_422` es "el motor rechazó el disparo". Contarlos juntos haría
que un incidente del proveedor se lea como un día con muchas entregas mal
configuradas. Los códigos de estos tests salen de grepear qué escribe
producción: usar uno inventado hace el test vacuo, porque cualquier código
desconocido cae en "rechazo" por default.

Contra Postgres real porque lo que se prueba es la lectura de la fila.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_correccion_metrics_db.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services.correccion_ejecutor import _registrar_desenlace
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(TENANT)}
        )
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()

    # `_registrar_desenlace` abre su propia sesión con el engine GLOBAL del
    # servicio, que se crea perezosamente y queda atado al event loop del
    # primer test. pytest-asyncio da un loop nuevo por test, así que a partir
    # del segundo las queries mueren con "attached to a different loop" — y el
    # `except` de `_registrar_desenlace` se las traga, con lo cual el test ve
    # una métrica que no se emitió y culpa al código. Resetearlo entre tests
    # deja que cada uno cree el suyo.
    import evaluation_service.db.session as _sesion_mod

    if _sesion_mod._engine is not None:
        await _sesion_mod._engine.dispose()
        _sesion_mod._engine = None
        _sesion_mod._session_factory = None


async def _entrega_real(db: AsyncSession) -> UUID:
    """`correcciones_ia` tiene FK a `entregas`, que a su vez la tiene a
    `comisiones` y `tareas_practicas`: los ids no se pueden inventar."""
    com = (
        await db.execute(
            text("SELECT id FROM comisiones WHERE tenant_id = :t LIMIT 1"), {"t": str(TENANT)}
        )
    ).scalar_one_or_none()
    if com is None:
        pytest.skip("la base no tiene comisiones sembradas")

    tp_id, entrega_id = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tareas_practicas "
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by, language) "
            "VALUES (:id, :t, :c, :cod, 'Test', 'Test', :u, 'java')"
        ),
        {
            "id": str(tp_id),
            "t": str(TENANT),
            "c": str(com),
            "cod": f"MET-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    await db.execute(
        text(
            "INSERT INTO entregas "
            "(id, tenant_id, tarea_practica_id, student_pseudonym, comision_id, estado, "
            " ejercicio_estados) "
            "VALUES (:id, :t, :tp, :st, :c, 'submitted', '[]'::jsonb)"
        ),
        {
            "id": str(entrega_id),
            "t": str(TENANT),
            "tp": str(tp_id),
            "st": str(uuid.uuid4()),
            "c": str(com),
        },
    )
    return entrega_id


async def _correccion(db: AsyncSession, *, estado: str, error_code: str | None = None) -> UUID:
    """Siembra una corrección ya cerrada, en el estado que el test necesita."""
    cid = uuid.uuid4()
    c = CorreccionIA(
        id=cid,
        tenant_id=TENANT,
        entrega_id=await _entrega_real(db),
        orden=1,
        disparado_por=uuid.uuid4(),
        rubrica_id="RUB-TEST",
        artefacto_sha256="0" * 64,
        estado=estado,
        error_code=error_code,
    )
    if estado == "done":
        c.nota_100 = 87  # el CHECK exige nota si y solo si `done`
    db.add(c)
    await db.flush()
    await db.commit()  # `_registrar_desenlace` abre su PROPIA sesión
    return cid


async def _limpiar(db: AsyncSession, cid: UUID) -> None:
    """Borra la corrección y lo que se sembró para sostenerla. Va explícito
    porque estos tests COMMITEAN — `_registrar_desenlace` abre su propia
    sesión y no vería una transacción sin cerrar."""
    ent = (
        await db.execute(
            text("SELECT entrega_id FROM correcciones_ia WHERE id = :i"), {"i": str(cid)}
        )
    ).scalar_one_or_none()
    await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(cid)})
    if ent is not None:
        tp = (
            await db.execute(
                text("SELECT tarea_practica_id FROM entregas WHERE id = :e"), {"e": str(ent)}
            )
        ).scalar_one_or_none()
        await db.execute(text("DELETE FROM entregas WHERE id = :e"), {"e": str(ent)})
        if tp is not None:
            await db.execute(text("DELETE FROM tareas_practicas WHERE id = :t"), {"t": str(tp)})
    await db.commit()


async def _desenlace(cid: UUID) -> dict[str, list]:
    """Corre el registro espiando las métricas, sin exportar nada."""
    espia: dict[str, list] = {"completada": [], "infra": []}

    def _completada(*, outcome: str, duration_seconds: float) -> None:
        espia["completada"].append(outcome)

    def _infra(*, causa: str) -> None:
        espia["infra"].append(causa)

    with (
        patch(
            "evaluation_service.services.correccion_ejecutor.metrics.record_completada",
            _completada,
        ),
        patch(
            "evaluation_service.services.correccion_ejecutor.metrics.record_infra_failure",
            _infra,
        ),
    ):
        await _registrar_desenlace(TENANT, cid, 3.5)
    return espia


class TestElOutcomeSaleDeLaFila:
    async def test_done_cuenta_como_con_nota(self, db: AsyncSession) -> None:
        cid = await _correccion(db, estado="done")
        try:
            espia = await _desenlace(cid)
            assert espia["completada"] == ["con_nota"]
            assert espia["infra"] == []
        finally:
            await _limpiar(db, cid)

    async def test_gemini_saturado_cuenta_como_infra_y_no_como_rechazo(
        self, db: AsyncSession
    ) -> None:
        cid = await _correccion(db, estado="error", error_code="GEMINI_OVERLOADED")
        try:
            espia = await _desenlace(cid)
            assert espia["completada"] == ["infra_failure"]
            assert espia["infra"] == ["GEMINI_OVERLOADED"]
        finally:
            await _limpiar(db, cid)

    async def test_un_rechazo_del_motor_no_cuenta_como_infra(self, db: AsyncSession) -> None:
        """El código era `NO_COMPILA` hasta el 19/08 — y ese día dejó de
        emitirlo producción, con lo cual el test pasó a ser vacuo: ninguna
        mutación podía hacerlo fallar. Lo encontró la auditoría (séptimo test
        vacuo del epic).

        `HTTP_422` sí lo emite `_subir_y_corregir` cuando el motor rechaza el
        disparo. Es un rechazo de verdad: reintentar devuelve lo mismo, y no
        puede contarse junto a un incidente del proveedor."""
        cid = await _correccion(db, estado="error", error_code="HTTP_422")
        try:
            espia = await _desenlace(cid)
            assert espia["completada"] == ["rechazada"]
            assert espia["infra"] == []
        finally:
            await _limpiar(db, cid)

    async def test_sin_rubrica_tambien_es_rechazo(self, db: AsyncSession) -> None:
        cid = await _correccion(db, estado="error", error_code="SIN_RUBRICA")
        try:
            espia = await _desenlace(cid)
            assert espia["completada"] == ["rechazada"]
        finally:
            await _limpiar(db, cid)

    async def test_la_fila_borrada_igual_cierra_el_contador(self) -> None:
        """Si la fila desapareció, `in_flight` tiene que bajar lo mismo. Sin
        esto, una corrección borrada a mitad de camino deja el contador
        permanentemente alto."""
        espia = await _desenlace(uuid.uuid4())
        assert espia["completada"] == ["desaparecida"]


class TestNuncaTumbaLaCorreccion:
    async def test_una_metrica_rota_no_levanta(self, db: AsyncSession) -> None:
        """`_registrar_desenlace` corre en un `finally`. Si levantara, se
        comería el error original de la corrección y encima dejaría la fila
        sin cerrar."""
        cid = await _correccion(db, estado="done")
        try:

            def _explota(**_: object) -> None:
                raise RuntimeError("el exportador se cayó")

            with patch(
                "evaluation_service.services.correccion_ejecutor.metrics.record_completada",
                _explota,
            ):
                await _registrar_desenlace(TENANT, cid, 1.0)  # no debe levantar
        finally:
            await _limpiar(db, cid)
