"""La entrega va a la comisión de la TP, no a la que declara el alumno.

`POST /api/v1/entregas` recibe `comision_id` del body. El FK
`fk_entregas_comision_id_comisiones` garantiza que esa comisión EXISTE — no que
sea la de la tarea práctica. Sin `_assert_comision_de_la_tp` el alumno elegía a
qué cola de corrección entraba su trabajo: `list_entregas` filtra por
`Entrega.comision_id`, así que declarar una comisión ajena mandaba la entrega a
los docentes equivocados, y declarar una comisión sin docentes la escondía de
la propia.

**Por qué contra Postgres real y no con la sesión mockeada.** El guard resuelve
la comisión de la TP con SQL crudo (`tareas_practicas` es de academic-service y
vive en la misma DB). Con una sesión mockeada `db.execute` devuelve lo que le
digamos, y el test pasaría con el guard puesto Y con el guard sacado: es
exactamente la clase de test vacuo que ya mordió siete veces en este epic. Acá
la fila existe o no existe.

Segunda razón, la del 422 vs 500: sin el guard, una TP o una comisión
inexistente reventaban recién en el `IntegrityError` del FK, que cae en la rama
de recuperación del race del UNIQUE, no encuentra nada y devuelve
"Error inesperado al crear entrega" (500). Ese camino sólo existe contra una DB
de verdad — con la sesión mockeada no hay FK que violar.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest \
        apps/evaluation-service/tests/integration/test_entrega_comision_de_la_tp_db.py -v

Sin esa env var se SKIPEAN. Cada test revierte lo que crea (el fixture cierra
con rollback y el endpoint sólo hace `flush`).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import (
    _comision_de_la_tp,
    create_entrega,
)
from evaluation_service.schemas.entrega import EntregaCreate
from fastapi import HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTRO_TENANT = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

# Se descubren de la base: `tareas_practicas` y `entregas` tienen FK a
# `comisiones`, no se pueden inventar UUIDs.
COMISION: UUID
OTRA_COMISION: UUID
# `True` cuando el rol de la conexión bypassa RLS (superuser). Ver
# `TestLaTPDeOtroTenantNoSeVe`.
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
    global COMISION, OTRA_COMISION, BYPASSA_RLS
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
        coms = (
            (
                await session.execute(
                    text("SELECT id FROM comisiones WHERE tenant_id = :t ORDER BY id LIMIT 2"),
                    {"t": str(TENANT)},
                )
            )
            .scalars()
            .all()
        )
        if len(coms) < 2:
            pytest.skip("la base necesita dos comisiones sembradas para distinguirlas")
        COMISION, OTRA_COMISION = coms[0], coms[1]
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _tp(db: AsyncSession, *, comision: UUID, tenant: UUID = TENANT) -> UUID:
    """Siembra una TP mínima.

    `language` va omitida a propósito, aunque los otros tests de esta carpeta
    la escriban: la columna la agregó `20260723_0001_ejercicio_tp_language` con
    `server_default='python'`, así que omitirla funciona igual contra una base
    migrada y contra una que todavía no lo esté. Nombrarla hace que estos tests
    fallen con `UndefinedColumnError` en vez de correr, que es cómo están hoy
    los dos tests vecinos en una base sin esa migración.
    """
    tp_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tareas_practicas "
            "(id, tenant_id, comision_id, codigo, titulo, enunciado, created_by) "
            "VALUES (:id, :t, :c, :cod, 'Test', 'Test', :u)"
        ),
        {
            "id": str(tp_id),
            "t": str(tenant),
            "c": str(comision),
            "cod": f"COM-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    return tp_id


async def _crear(db: AsyncSession, *, tp: UUID, comision: UUID, alumno: UUID) -> tuple:
    """Llama al endpoint como lo llama FastAPI y devuelve `(salida, response)`.

    El `status_code = None` no es cosmético: es lo que hace
    `solve_dependencies` antes de inyectar el `Response` (fastapi
    `dependencies/utils.py`), justamente para poder distinguir "el handler NO
    tocó el status" (y entonces vale el 201 del decorator) de "lo pisó con
    200". Un `Response()` pelado arranca en 200 y borra esa distinción: el
    camino feliz y el idempotente se volverían indistinguibles.
    """
    response = Response()
    response.status_code = None  # type: ignore[assignment]
    salida = await create_entrega(
        EntregaCreate(tarea_practica_id=tp, comision_id=comision),
        response,
        user=_alumno(alumno),
        db=db,
    )
    return salida, response


class TestElLectorDeLaComision:
    """`_comision_de_la_tp` es la mitad de abajo del guard."""

    async def test_devuelve_la_comision_de_la_tp(self, db: AsyncSession) -> None:
        tp = await _tp(db, comision=OTRA_COMISION)
        assert await _comision_de_la_tp(db, tp) == OTRA_COMISION

    async def test_la_tp_inexistente_da_none_y_no_revienta(self, db: AsyncSession) -> None:
        """`None` y no una excepción: el caller lo traduce a 422, y un
        `NoResultFound` acá saldría como 500."""
        assert await _comision_de_la_tp(db, uuid.uuid4()) is None


class TestLaComisionDeclaradaTieneQueSerLaDeLaTP:
    async def test_otra_comision_del_mismo_tenant_es_422(self, db: AsyncSession) -> None:
        """El bug tal cual: la comisión existe (el FK pasa), pero no es la de
        la TP. Sin el guard esto devolvía 201 y la entrega quedaba en la cola
        de corrección de los docentes de `OTRA_COMISION`."""
        tp = await _tp(db, comision=COMISION)
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=tp, comision=OTRA_COMISION, alumno=uuid.uuid4())
        assert e.value.status_code == 422
        assert "no es la del trabajo practico" in str(e.value.detail)

    async def test_no_deja_la_entrega_escrita(self, db: AsyncSession) -> None:
        """Que el 422 salga no alcanza: tiene que salir ANTES del insert. Un
        guard puesto después del `flush` daría el mismo código de estado con
        la fila mal ruteada ya en la tabla."""
        alumno = uuid.uuid4()
        tp = await _tp(db, comision=COMISION)
        with pytest.raises(HTTPException):
            await _crear(db, tp=tp, comision=OTRA_COMISION, alumno=alumno)
        cuantas = (
            await db.execute(
                text(
                    "SELECT count(*) FROM entregas "
                    "WHERE tarea_practica_id = :tp AND student_pseudonym = :s"
                ),
                {"tp": str(tp), "s": str(alumno)},
            )
        ).scalar_one()
        assert cuantas == 0

    async def test_comision_inexistente_es_422_y_no_500(self, db: AsyncSession) -> None:
        """El caso que reventaba feo. Sin el guard, el `comision_id` inventado
        pasa el SELECT de idempotencia, muere en el FK con `IntegrityError`, y
        la rama de recuperación del race del UNIQUE —que no está para esto—
        no encuentra la entrega y devuelve 500 "Error inesperado al crear
        entrega". El cliente mandó un body mal armado: eso es 422."""
        tp = await _tp(db, comision=COMISION)
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=tp, comision=uuid.uuid4(), alumno=uuid.uuid4())
        assert e.value.status_code == 422

    async def test_tp_inexistente_es_422(self, db: AsyncSession) -> None:
        """Mismo camino: el FK de `tarea_practica_id` también reventaba en el
        insert. Y el mensaje no confirma nada más que "no existe"."""
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=uuid.uuid4(), comision=COMISION, alumno=uuid.uuid4())
        assert e.value.status_code == 422
        assert e.value.detail == "Trabajo practico no existe"


class TestLaTPDeOtroTenantNoSeVe:
    """RLS: `tareas_practicas` filtra por `app.current_tenant`.

    La TP se siembra con `tenant_id` de otro tenant y la comisión del propio:
    el FK apunta a `comisiones(id)` sin mirar el tenant, así que la fila entra
    y el único motivo por el que el guard no la ve es la policy
    `tenant_isolation`.
    """

    async def test_declarando_la_comision_propia_es_422(self, db: AsyncSession) -> None:
        """Este corre siempre. Bajo RLS la TP no existe; sin RLS existe pero su
        comisión no es la declarada. Los dos caminos son 422 — y sin el guard
        son 201 con la entrega de un tenant colgada de la TP de otro."""
        ajena = await _tp(db, comision=OTRA_COMISION, tenant=OTRO_TENANT)
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=ajena, comision=COMISION, alumno=uuid.uuid4())
        assert e.value.status_code == 422

    async def test_ni_declarando_la_comision_correcta_hay_fuga(self, db: AsyncSession) -> None:
        """La forma fuerte: el alumno acierta la comisión de la TP ajena, así
        que lo único que puede rechazarlo es que la TP no sea visible. El
        mensaje además tiene que ser "no existe" y no "no es la del trabajo
        practico" — el segundo le confirmaría al atacante que la TP existe.

        Se SKIPEA cuando el rol de la conexión bypassa RLS: como `postgres` la
        TP ajena SÍ se ve, la respuesta pasa a ser 201 y el test fallaría por
        la config de la corrida, no por el código. Es la misma advertencia que
        tiene `make test-rls` ("NO usar `postgres` acá"). Para correrlo de
        verdad hace falta un rol NOBYPASSRLS con grants sobre `academic_main`.
        """
        if BYPASSA_RLS:
            pytest.skip(
                "el rol de EVAL_TEST_DB_URL bypassa RLS (superuser): la TP ajena se ve "
                "y el test no probaría el aislamiento. Usar un rol NOBYPASSRLS."
            )
        ajena = await _tp(db, comision=OTRA_COMISION, tenant=OTRO_TENANT)
        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=ajena, comision=OTRA_COMISION, alumno=uuid.uuid4())
        assert e.value.status_code == 422
        assert e.value.detail == "Trabajo practico no existe"


class TestElCaminoFeliz:
    async def test_la_entrega_nace_en_la_comision_de_la_tp(self, db: AsyncSession) -> None:
        tp = await _tp(db, comision=OTRA_COMISION)
        salida, response = await _crear(db, tp=tp, comision=OTRA_COMISION, alumno=uuid.uuid4())
        # El 201 lo pone el decorator; el endpoint sólo pisa el status para el
        # 200 idempotente, así que "no lo pisó" es "creó".
        assert response.status_code is None
        assert salida.comision_id == OTRA_COMISION
        assert await _comision_de_la_tp(db, tp) == salida.comision_id

    async def test_repetir_el_mismo_body_sigue_siendo_idempotente(self, db: AsyncSession) -> None:
        """El guard va ANTES del SELECT de idempotencia: hay que verificar que
        no rompió el 200 que ese camino ya daba."""
        alumno = uuid.uuid4()
        tp = await _tp(db, comision=COMISION)
        primera, _ = await _crear(db, tp=tp, comision=COMISION, alumno=alumno)
        segunda, response = await _crear(db, tp=tp, comision=COMISION, alumno=alumno)
        assert response.status_code == 200
        assert segunda.id == primera.id


class TestLaEntregaExistenteNoTapaElBodyMalo:
    async def test_body_con_comision_mala_sobre_entrega_existente_es_422(
        self, db: AsyncSession
    ) -> None:
        """Cambio deliberado del camino idempotente: antes el SELECT corría
        primero y devolvía 200 con la entrega buena, tragándose un body que
        estaba mal armado. Un cliente que manda la comisión equivocada tiene
        un bug, y el 200 se lo escondía hasta la primera entrega de un alumno
        nuevo — donde sí llegaba al insert y explotaba con 500.

        Sin el guard (o con el guard después del SELECT) esto devuelve 200.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db, comision=COMISION)
        entrega = Entrega(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            tarea_practica_id=tp,
            student_pseudonym=alumno,
            comision_id=COMISION,
            estado="draft",
            ejercicio_estados=[],
        )
        db.add(entrega)
        await db.flush()

        with pytest.raises(HTTPException) as e:
            await _crear(db, tp=tp, comision=OTRA_COMISION, alumno=alumno)
        assert e.value.status_code == 422

    async def test_la_entrega_existente_no_se_toca(self, db: AsyncSession) -> None:
        """El 422 no puede llevarse puesta la comisión que ya estaba bien."""
        alumno = uuid.uuid4()
        tp = await _tp(db, comision=COMISION)
        entrega = Entrega(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            tarea_practica_id=tp,
            student_pseudonym=alumno,
            comision_id=COMISION,
            estado="draft",
            ejercicio_estados=[],
        )
        db.add(entrega)
        await db.flush()

        with pytest.raises(HTTPException):
            await _crear(db, tp=tp, comision=OTRA_COMISION, alumno=alumno)
        quedo = (
            await db.execute(
                text("SELECT comision_id FROM entregas WHERE id = :i"), {"i": str(entrega.id)}
            )
        ).scalar_one()
        assert quedo == COMISION
