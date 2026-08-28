"""La cuota diaria, contando filas de verdad.

Los 4 tests de `TestCuotaFallaCerrada` (`tests/unit/test_correccion_ia.py`)
mockean `db.execute` y le devuelven un `scalar_one` fijo. Eso prueba la rama de
arriba —falla cerrada, excedida, cuantas quedan— y **no toca la query**. La
mutacion

    CorreccionIA.estado.in_(("pending", "running", "done"))
      ->  CorreccionIA.estado.in_(("done",))

sobrevive intacta a los cuatro: el doble contesta lo mismo con cualquier WHERE.
Y esa mutacion no es teorica — dejar de contar `pending` y `running` es
exactamente el bug que el docstring del modulo dice que evita ("las `pending` y
`running` si cuentan — estan en vuelo y van a gastar"). Un docente podria
disparar N correcciones en paralelo y ninguna contaria hasta terminar.

Este archivo cuenta filas reales. Las cuatro propiedades del WHERE se prueban
una por una, cada una con su fila que NO tiene que contar:

  - los tres estados en vuelo/cobrables cuentan; `error` no (un
    `GEMINI_OVERLOADED` no gasto una corrida de Gemini);
  - la ventana es de 24h, no del catalogo entero;
  - el contador es por docente (`disparado_por`), no del tenant;
  - y es por tenant, no global.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_correccion_cuota_db.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from evaluation_service.services.correccion_cuota import consumidas_hoy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)

TENANT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTRO_TENANT = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Sesion superuser con el tenant seteado, en transaccion que se revierte.

    Todo lo que siembran los tests muere en el rollback del final, asi que no
    hace falta limpiar a mano ni el orden de borrado importa.
    """
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


async def _entrega(db: AsyncSession, tenant: uuid.UUID) -> uuid.UUID:
    """Una entrega de la que colgar correcciones. La FK la exige."""
    fila = (
        await db.execute(
            text(
                "SELECT tp.id, tp.comision_id FROM tareas_practicas tp "
                "WHERE tp.deleted_at IS NULL LIMIT 1"
            )
        )
    ).first()
    if fila is None:
        pytest.skip("la base no tiene tareas_practicas")
    entrega_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO entregas (id, tenant_id, tarea_practica_id, student_pseudonym, "
            "comision_id, estado, ejercicio_estados) "
            "VALUES (:id, :t, :tp, :s, :c, 'submitted', '[]'::jsonb)"
        ),
        {
            "id": str(entrega_id),
            "t": str(tenant),
            "tp": str(fila[0]),
            "s": str(uuid.uuid4()),
            "c": str(fila[1]),
        },
    )
    return entrega_id


async def _correccion(
    db: AsyncSession,
    entrega_id: uuid.UUID,
    *,
    tenant: uuid.UUID,
    docente: uuid.UUID,
    estado: str,
    orden: int,
    hace: timedelta = timedelta(0),
) -> None:
    """Una fila de `correcciones_ia`. `orden` distinto por el UNIQUE de idempotencia."""
    # El CHECK `nota_solo_si_done` obliga: 'done' con nota, el resto sin.
    nota = "87.00" if estado == "done" else "NULL"
    await db.execute(
        text(
            "INSERT INTO correcciones_ia "
            "(id, tenant_id, entrega_id, orden, disparado_por, rubrica_id, estado, "
            f" artefacto_sha256, nota_100, created_at) VALUES "
            f"(gen_random_uuid(), :t, :e, :o, :u, 'r1', :es, :h, {nota}, :ts)"
        ),
        {
            "t": str(tenant),
            "e": str(entrega_id),
            "o": orden,
            "u": str(docente),
            "es": estado,
            "h": f"{orden:064d}",
            "ts": datetime.now(UTC) - hace,
        },
    )


class TestQueCuentaElContador:
    async def test_pending_y_running_cuentan_igual_que_done(self, db: AsyncSession) -> None:
        """La propiedad que la mutacion `in_(("done",))` rompe.

        Estan en vuelo y van a gastar. Si no contaran, un docente dispara N en
        paralelo, el contador lee 0 en las N, y la cuota no existe.
        """
        docente = uuid.uuid4()
        entrega = await _entrega(db, TENANT)
        for i, estado in enumerate(("pending", "running", "done")):
            await _correccion(
                db, entrega, tenant=TENANT, docente=docente, estado=estado, orden=i + 1
            )
        await db.flush()

        assert await consumidas_hoy(db, TENANT, docente) == 3

    async def test_un_fallo_de_infraestructura_NO_se_le_cobra_al_docente(
        self, db: AsyncSession
    ) -> None:
        """`error` es el unico estado que no cuenta.

        Un `GEMINI_OVERLOADED` no consumio una corrida de Gemini; cobrarsela es
        cobrarle por algo que no recibio. Si `error` entrara al `in_`, el
        docente pierde cuota cada vez que el motor se cae.
        """
        docente = uuid.uuid4()
        entrega = await _entrega(db, TENANT)
        await _correccion(db, entrega, tenant=TENANT, docente=docente, estado="done", orden=1)
        await _correccion(db, entrega, tenant=TENANT, docente=docente, estado="error", orden=2)
        await db.flush()

        assert await consumidas_hoy(db, TENANT, docente) == 1

    async def test_la_ventana_es_de_24h_y_no_del_catalogo_entero(self, db: AsyncSession) -> None:
        """Sin el `created_at >= desde` la cuota se agota para siempre.

        La de hace 25h esta fuera; la de hace 23 esta adentro. Los dos lados del
        borde, porque con uno solo cualquier ventana mas ancha pasa igual.
        """
        docente = uuid.uuid4()
        entrega = await _entrega(db, TENANT)
        await _correccion(
            db,
            entrega,
            tenant=TENANT,
            docente=docente,
            estado="done",
            orden=1,
            hace=timedelta(hours=25),
        )
        await _correccion(
            db,
            entrega,
            tenant=TENANT,
            docente=docente,
            estado="done",
            orden=2,
            hace=timedelta(hours=23),
        )
        await db.flush()

        assert await consumidas_hoy(db, TENANT, docente) == 1

    async def test_el_contador_es_por_docente_y_no_del_tenant(self, db: AsyncSession) -> None:
        """Sin el filtro por `disparado_por`, un docente activo le agota la
        cuota a todos sus companeros de tenant."""
        docente, colega = uuid.uuid4(), uuid.uuid4()
        entrega = await _entrega(db, TENANT)
        await _correccion(db, entrega, tenant=TENANT, docente=docente, estado="done", orden=1)
        await _correccion(db, entrega, tenant=TENANT, docente=colega, estado="done", orden=2)
        await db.flush()

        assert await consumidas_hoy(db, TENANT, docente) == 1

    async def test_el_contador_es_por_tenant(self, db: AsyncSession) -> None:
        """El mismo `user_id` en dos tenants no comparte cuota.

        La fila del otro tenant se inserta con la RLS bypasseada (el fixture
        entra como `postgres`), asi que lo que se prueba aca es el predicado
        explicito de la query, no la policy.
        """
        docente = uuid.uuid4()
        propia = await _entrega(db, TENANT)
        ajena = await _entrega(db, OTRO_TENANT)
        await _correccion(db, propia, tenant=TENANT, docente=docente, estado="done", orden=1)
        await _correccion(db, ajena, tenant=OTRO_TENANT, docente=docente, estado="done", orden=2)
        await db.flush()

        assert await consumidas_hoy(db, TENANT, docente) == 1
