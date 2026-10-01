"""`_tp_metadata` y `_notas_metadata` contra Postgres real.

Change `alumno-ve-su-nota-sin-depender-del-listado`: estas dos funciones
resuelven, en UNA consulta por lote, el código/título de la TP y la
nota/fecha de corrección de cada entrega — para que "Mis notas" no pida un
request por fila. `_tp_metadata` arma un `IN` con
`bindparam("ids", expanding=True)` sobre `tareas_practicas` (tabla de
academic-service, SQL crudo); `_notas_metadata` usa el ORM sobre
`Calificacion` (propio de evaluation-service).

**Por qué contra Postgres real y no alcanza con la sesión mockeada.** Dos
motivos, no uno — y los dos los señaló la revisión de DBA:

1. El `IN` con `expanding=True` de `_tp_metadata` **compila** limpio en
   abstracto (verificado por el DBA leyendo el código), pero compilar no es
   ejecutar contra el driver asyncpg real. Hay precedente exacto citado en
   `CLAUDE.md`: el bind param de `SET LOCAL` de BYOK compilaba bien y pasaba
   tests con DB mockeada, y recién falló en runtime contra Postgres real. Un
   test unitario con sesión mockeada NUNCA manda esa query a un driver —
   pasaría con el `IN` bien armado Y con uno roto. Es la misma clase de test
   vacuo que `test_aislamiento_comision_db.py` describe en su propio
   docstring: "con una sesión mockeada, el test pasaría con el guard puesto Y
   con el guard sacado".
2. RLS: `entregas`, `tareas_practicas` y `calificaciones` tienen `ENABLE` +
   `FORCE ROW LEVEL SECURITY` (verificado por el DBA leyendo las policies).
   Que el filtro de tenant lo aplique Postgres —y no sólo el `WHERE` que
   Python arma— es algo que una sesión mockeada no puede ni prometer probar.

Mismo patrón que los dos hermanos de esta carpeta
(`test_entrega_comision_de_la_tp_db.py`, `test_aislamiento_comision_db.py`):
se SKIPEAN sin `EVAL_TEST_DB_URL`, y el test de RLS se SKIPEA además si el rol
de la conexión bypassa RLS (superuser) — con ese rol la fila ajena se vería
igual y el test no probaría nada.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_tp_notas_metadata_db.py -v

Sin esa env var se SKIPEAN. Cada test revierte lo que crea (rollback).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import _notas_metadata, _tp_metadata, get_entrega
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTRO_TENANT = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Se descubre de la base: `tareas_practicas` tiene FK a `comisiones`, no se
# puede inventar un UUID.
COMISION: UUID
# `True` cuando el rol de la conexión bypassa RLS (superuser). Ver
# `TestTpMetadataRespetaRLS`.
BYPASSA_RLS: bool


def _alumno(uid: UUID) -> User:
    return User(
        id=uid,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    global COMISION, BYPASSA_RLS
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(TENANT)},
        )
        BYPASSA_RLS = bool(
            (
                await session.execute(
                    text(
                        "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = CURRENT_USER"
                    )
                )
            ).scalar_one()
        )
        com = (
            await session.execute(
                text("SELECT id FROM comisiones WHERE tenant_id = :t LIMIT 1"),
                {"t": str(TENANT)},
            )
        ).scalar_one_or_none()
        if com is None:
            pytest.skip("la base no tiene comisiones sembradas")
        COMISION = com
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _tp(
    db: AsyncSession,
    *,
    codigo: str,
    titulo: str,
    comision: UUID | None = None,
    tenant: UUID = TENANT,
) -> UUID:
    """Siembra una TP con código y título CONOCIDOS — a diferencia de los
    hermanos (que sólo necesitan que la TP exista), acá los valores son lo
    que se afirma en los asserts."""
    tp_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tareas_practicas "
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by) "
            "VALUES (:id, :t, :c, :cod, :tit, 'Test', :u)"
        ),
        {
            "id": str(tp_id),
            "t": str(tenant),
            "c": str(comision if comision is not None else COMISION),
            "cod": codigo,
            "tit": titulo,
            "u": str(uuid.uuid4()),
        },
    )
    return tp_id


async def _entrega(db: AsyncSession, *, tp: UUID, estado: str = "submitted") -> Entrega:
    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp,
        student_pseudonym=uuid.uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    db.add(entrega)
    await db.flush()
    return entrega


async def _calificacion(
    db: AsyncSession, *, entrega_id: UUID, nota: Decimal, graded_at: datetime
) -> None:
    await db.execute(
        text(
            "INSERT INTO calificaciones (id, tenant_id, entrega_id, nota_final, graded_by, graded_at) "
            "VALUES (:id, :t, :e, :n, :u, :g)"
        ),
        {
            "id": str(uuid.uuid4()),
            "t": str(TENANT),
            "e": str(entrega_id),
            "n": str(nota),
            "u": str(uuid.uuid4()),
            "g": graded_at,
        },
    )
    await db.flush()


class TestTpMetadataEjecutaContraPostgres:
    """El `IN` con `expanding=True` tiene que EJECUTAR, no sólo compilar."""

    async def test_trae_codigo_y_titulo_de_varias_tps_en_un_solo_batch(
        self, db: AsyncSession
    ) -> None:
        tp1 = await _tp(db, codigo="TPM-1", titulo="Primeros programas")
        tp2 = await _tp(db, codigo="TPM-2", titulo="Agenda de turnos")

        meta = await _tp_metadata(db, {tp1, tp2})

        assert meta[tp1] == ("TPM-1", "Primeros programas")
        assert meta[tp2] == ("TPM-2", "Agenda de turnos")

    async def test_tp_inexistente_no_entra_al_dict_y_no_revienta(self, db: AsyncSession) -> None:
        meta = await _tp_metadata(db, {uuid.uuid4()})
        assert meta == {}


class TestNotasMetadataEjecutaContraPostgres:
    async def test_trae_nota_y_fecha_de_la_calificacion(self, db: AsyncSession) -> None:
        tp = await _tp(db, codigo="NM-1", titulo="Con nota")
        entrega = await _entrega(db, tp=tp, estado="graded")
        graded_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        await _calificacion(db, entrega_id=entrega.id, nota=Decimal("8.50"), graded_at=graded_at)

        meta = await _notas_metadata(db, {entrega.id})

        nota, fecha = meta[entrega.id]
        assert nota == Decimal("8.50")
        assert fecha == graded_at

    async def test_entrega_sin_calificacion_no_entra_al_dict(self, db: AsyncSession) -> None:
        tp = await _tp(db, codigo="NM-2", titulo="Sin nota")
        entrega = await _entrega(db, tp=tp, estado="submitted")

        meta = await _notas_metadata(db, {entrega.id})

        assert entrega.id not in meta


class TestGetEntregaConMetadataCompletaContraPostgres:
    """Las dos funciones ejecutando JUNTAS, por el camino real del endpoint —
    la forma más fuerte de probar "ejecuta y devuelve lo que debe": no alcanza
    con que cada helper funcione aislado si el endpoint arma mal el `set` de
    ids o pisa un campo con el otro."""

    async def test_entrega_con_tp_y_calificacion_trae_los_cuatro_campos(
        self, db: AsyncSession
    ) -> None:
        tp = await _tp(db, codigo="E2E-1", titulo="Completo")
        entrega = await _entrega(db, tp=tp, estado="graded")
        graded_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        await _calificacion(db, entrega_id=entrega.id, nota=Decimal("9.00"), graded_at=graded_at)

        out = await get_entrega(entrega.id, user=_alumno(entrega.student_pseudonym), db=db)

        assert out.tarea_codigo == "E2E-1"
        assert out.tarea_titulo == "Completo"
        assert out.nota_final == 9.0
        assert out.graded_at == graded_at


class TestTpMetadataRespetaRLS:
    """RLS: `tareas_practicas` filtra por `app.current_tenant`, igual que
    `TestLaTPDeOtroTenantNoSeVe` en `test_entrega_comision_de_la_tp_db.py`.

    No se duplica la misma verificación para `calificaciones`: es una tabla
    propia de evaluation-service consultada por ORM bajo la MISMA sesión y el
    MISMO `app.current_tenant` que ya fija este fixture — el camino de RLS que
    atraviesa es el estándar, no uno especial como el SQL crudo cross-service
    de `_tp_metadata`. Queda sin cubrir acá por acotar el alcance, no por
    haberlo verificado.
    """

    async def test_tp_de_otro_tenant_no_aparece_aunque_se_pida_por_id(
        self, db: AsyncSession
    ) -> None:
        if BYPASSA_RLS:
            pytest.skip(
                "el rol de EVAL_TEST_DB_URL bypassa RLS (superuser): la TP ajena "
                "se vería igual y el test no probaría el aislamiento. Usar un rol "
                "NOBYPASSRLS."
            )
        ajena = await _tp(db, codigo="RLS-1", titulo="Ajena", tenant=OTRO_TENANT)

        meta = await _tp_metadata(db, {ajena})

        assert ajena not in meta
