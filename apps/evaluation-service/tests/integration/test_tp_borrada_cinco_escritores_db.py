"""Los CINCO escritores sobre un TP borrado, y las lecturas que deben seguir abiertas.

`test_tp_borrada_db.py` cubre tres de los cinco: `submit`,
`mark_ejercicio_completado` y `calificar`. Faltan `recalificar` y `return`, que
son los que quedan del lado del docente DESPUES de la nota — y son justo los
que un `# DEFERRED` en `TareaPracticaService.soft_delete` deja llegar.

Verificado con mutantes: sacar `para_escritura=True` de la llamada a
`_get_or_404` en `recalificar_entrega` o en `return_entrega` no mataba NINGUN
test del repo. Estos son los que lo matan.

El archivo agrega tres cosas al vecino:

1. **Los dos escritores que faltaban**, con su control de TP viva al lado. Un
   guard que rechace siempre pasaria los tests de rechazo y romperia el piloto.

2. **El motivo del 409, no solo el numero.** `return_entrega` contesta 409 por
   dos causas distintas —"la TP no existe" y "la entrega no esta en graded"— y
   un test que solo mire el status no distingue una de la otra: pasaria con el
   guard sacado, por el estado. Se asserta el `detail`.

3. **Las lecturas.** El fix es de escritura A PROPOSITO: el docente tiene que
   poder ver el trabajo historico del alumno sobre una TP borrada, que es
   evidencia legitima. `_get_or_404` tiene `para_escritura=False` por default
   y hay cuatro lectores que dependen de eso (`get_entrega`,
   `get_entrega_artefacto`, `get_calificacion`, `list_entregas`). El vecino
   cubre uno; los otros tres estan aca. Cerrarlos seria una regresion de
   producto, no un endurecimiento.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \\
        uv run pytest \\
        apps/evaluation-service/tests/integration/test_tp_borrada_cinco_escritores_db.py -v

Sin esa env var se SKIPEAN. Cada test revierte lo que crea.
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
from evaluation_service.routes.entregas import (
    get_calificacion,
    get_entrega_artefacto,
    list_entregas,
    recalificar_entrega,
    return_entrega,
)
from evaluation_service.schemas.entrega import CalificacionUpdate
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN,
    reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real",
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# El literal que produce `_assert_tp_viva`. Se compara contra esto y no contra
# el status a secas: `return_entrega` contesta 409 tambien por estado, y los
# dos 409 son indistinguibles si el test solo mira el numero.
TP_MUERTA = "El trabajo practico ya no esta disponible. Consulta con tu docente antes de seguir."

COMISION: UUID


def _alumno(uid: UUID) -> User:
    return User(
        id=uid,
        tenant_id=TENANT,
        email="a@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


def _docente() -> User:
    """`docente_admin` entra en `_OVERSIGHT_ROLES`: pasa `_assert_comision_visible`
    sin necesitar fila en `usuarios_comision`. Lo que se mide aca es el guard de
    la TP borrada, no el de comision."""
    return User(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        email="d@utn.edu.ar",
        roles=frozenset({"docente_admin"}),
        realm="utn",
    )


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    global COMISION
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(TENANT)},
        )
        com = (
            await session.execute(
                text("SELECT id FROM comisiones WHERE tenant_id = :t ORDER BY id LIMIT 1"),
                {"t": str(TENANT)},
            )
        ).scalar_one_or_none()
        if com is None:
            pytest.skip("la base necesita al menos una comision sembrada")
        COMISION = com
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _tp(db: AsyncSession) -> UUID:
    """Siembra una TP monolitica viva.

    `language` va omitida a proposito —igual que en los archivos vecinos—: la
    columna tiene `server_default` y nombrarla rompe contra una base sin la
    migracion `20260723_0001`.
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
            "t": str(TENANT),
            "c": str(COMISION),
            "cod": f"DEL5-{tp_id.hex[:8]}",
            "u": str(uuid.uuid4()),
        },
    )
    return tp_id


async def _borrar(db: AsyncSession, tp: UUID) -> None:
    """El soft-delete tal cual lo hace `TareaPracticaService.soft_delete`."""
    await db.execute(
        text("UPDATE tareas_practicas SET deleted_at = now() WHERE id = :tp"),
        {"tp": str(tp)},
    )


async def _entrega(db: AsyncSession, *, tp: UUID, alumno: UUID, estado: str) -> Entrega:
    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp,
        student_pseudonym=alumno,
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    db.add(entrega)
    await db.flush()
    return entrega


async def _calificar_a_mano(db: AsyncSession, entrega_id: UUID, nota: str = "5.00") -> UUID:
    """Inserta la calificacion por SQL: `recalificar` necesita una previa.

    Va por SQL y no llamando a `calificar_entrega` para que el arranque del
    test no dependa del endpoint que el mismo archivo esta atacando.
    """
    cal_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO calificaciones (id, tenant_id, entrega_id, graded_by, "
            "nota_final, detalle_criterios) VALUES (:id, :t, :e, :g, :n, '[]'::jsonb)"
        ),
        {
            "id": str(cal_id),
            "t": str(TENANT),
            "e": str(entrega_id),
            "g": str(uuid.uuid4()),
            "n": Decimal(nota),
        },
    )
    return cal_id


# ── Los dos escritores que el archivo vecino no cubre ──────────────────────


class TestLosDosEscritoresQueFaltaban:
    """`recalificar` y `return`: el ciclo DESPUES de la nota.

    Los dos arrancan en `_get_or_404(..., para_escritura=True)` igual que los
    otros tres, pero ningun test los ejercia. Sacarles el argumento no ponia
    rojo nada.
    """

    async def test_recalificar_sobre_tp_borrada_es_409(self, db: AsyncSession) -> None:
        """Corregirle la nota a un TP que ya no existe.

        Es el escritor menos obvio y el mas facil de olvidar: llega despues de
        que el ciclo "termino". `recalificar` no tiene ningun otro 409 propio
        (sus rechazos son 404 y 422), asi que el status ya identifica la causa
        — igual se asserta el detalle, que es lo que sostiene la propiedad si
        manana aparece otro 409 en el endpoint.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")
        await _calificar_a_mano(db, entrega.id)
        await _borrar(db, tp)

        with pytest.raises(HTTPException) as e:
            await recalificar_entrega(
                entrega.id,
                CalificacionUpdate(nota_final=Decimal("9.00")),
                user=_docente(),
                db=db,
            )
        assert e.value.status_code == 409
        assert e.value.detail == TP_MUERTA

        nota = (
            await db.execute(
                text("SELECT nota_final FROM calificaciones WHERE entrega_id = :e"),
                {"e": str(entrega.id)},
            )
        ).scalar_one()
        assert float(nota) == 5.0, "la nota se re-escribio sobre un TP borrado"

    async def test_return_sobre_tp_borrada_es_409_por_la_tp_y_no_por_el_estado(
        self, db: AsyncSession
    ) -> None:
        """El caso donde el status solo no alcanza.

        `return_entrega` ya contesta 409 cuando la entrega no esta en `graded`.
        Un test que asserte `status_code == 409` sobre una entrega en otro
        estado pasa con el guard SACADO, porque el 409 lo produce la otra
        rama. Por eso la entrega entra en `graded` —el unico estado que
        `return` acepta— y se compara el detalle: el unico 409 posible acá es
        el de la TP muerta.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")
        await _borrar(db, tp)

        with pytest.raises(HTTPException) as e:
            await return_entrega(entrega.id, user=_docente(), db=db)
        assert e.value.status_code == 409
        assert e.value.detail == TP_MUERTA, (
            "el 409 salio por el estado de la entrega, no por la TP borrada: "
            "el test pasaria con el guard sacado"
        )

        estado = (
            await db.execute(
                text("SELECT estado FROM entregas WHERE id = :e"), {"e": str(entrega.id)}
            )
        ).scalar_one()
        assert estado == "graded", "la entrega paso a 'returned' igual"


class TestLosDosEscritoresSobreTPVivaSiguenFuncionando:
    """El control. Un guard que rechace siempre pasa los dos tests de arriba."""

    async def test_recalificar_sobre_tp_viva_actualiza_la_nota(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")
        await _calificar_a_mano(db, entrega.id)

        cal = await recalificar_entrega(
            entrega.id,
            CalificacionUpdate(nota_final=Decimal("9.00")),
            user=_docente(),
            db=db,
        )
        assert float(cal.nota_final) == 9.0

    async def test_return_sobre_tp_viva_devuelve_la_entrega(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")

        devuelta = await return_entrega(entrega.id, user=_docente(), db=db)
        assert devuelta.estado == "returned"


# ── Las lecturas siguen abiertas: es el diseño, no un olvido ───────────────


class TestElTrabajoHistoricoSeSigueViendo:
    """`para_escritura` es `False` por default A PROPOSITO.

    El docente tiene que poder ver el trabajo del alumno sobre una TP que él
    mismo borró: la entrega existió y la TP existía cuando se hizo. Un
    "endurecimiento" que ponga el guard en `_get_or_404` sin distinguir
    lectura de escritura le borra esa evidencia de la vista, y es una
    regresión de producto — no la version estricta del mismo fix.

    El vecino cubre `get_entrega`. Estos son los otros tres lectores.
    """

    async def test_el_codigo_entregado_se_sigue_pudiendo_leer(self, db: AsyncSession) -> None:
        """`get_entrega_artefacto` — lo que el alumno efectivamente escribio.

        Es la lectura que mas duele perder: sin ella el docente ve que hubo una
        entrega y no puede abrir el codigo.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="submitted")
        await _borrar(db, tp)

        artefacto = await get_entrega_artefacto(entrega.id, user=_docente(), db=db)
        assert artefacto.entrega_id == entrega.id
        assert artefacto.tarea_practica_id == tp

    async def test_la_nota_puesta_se_sigue_pudiendo_leer(self, db: AsyncSession) -> None:
        """`get_calificacion` — la nota sobrevive al borrado de la TP.

        Se puso cuando la TP estaba viva y es parte del legajo del alumno.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")
        await _calificar_a_mano(db, entrega.id, nota="7.00")
        await _borrar(db, tp)

        cal = await get_calificacion(entrega.id, user=_docente(), db=db)
        assert float(cal.nota_final) == 7.0

    async def test_la_entrega_sigue_apareciendo_en_el_listado(self, db: AsyncSession) -> None:
        """`list_entregas` no pasa por `_get_or_404`, asi que no se rompe por
        este fix — pero es la lectura de la que cuelga toda la vista del
        docente, y el filtro por `tarea_practica_id` es lo que un
        "endurecimiento" del listado atacaria primero.

        Deja anotado un matiz de producto, no un defecto: como el listado
        sigue mostrando la entrega y `list_entregas` filtra `estado != 'draft'`,
        una entrega `submitted` sobre una TP borrada **sigue apareciendo en la
        cola de correccion**. Lo que cambio es que ahora, al intentar
        calificarla, el docente recibe un 409 explicito en vez de una nota
        persistida sobre un TP inexistente.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="submitted")
        await _borrar(db, tp)

        listado = await list_entregas(
            tarea_practica_id=tp,
            comision_id=None,
            estado=None,
            student_pseudonym=None,
            cursor=None,
            limit=50,
            user=_docente(),
            db=db,
        )
        assert [e.id for e in listado.data] == [entrega.id]


# ── Que el guard mire `deleted_at` y no cualquier otra cosa ────────────────


class TestElGuardMiraElBorrado:
    async def test_una_tp_borrada_ayer_tambien_corta(self, db: AsyncSession) -> None:
        """`deleted_at` con fecha pasada, no solo `now()`.

        Un filtro escrito como `deleted_at > now()` —o cualquier comparacion
        temporal en vez de `IS NULL`— pasaria el resto de los tests, que borran
        con `now()`.
        """
        alumno = uuid.uuid4()
        tp = await _tp(db)
        entrega = await _entrega(db, tp=tp, alumno=alumno, estado="graded")
        await db.execute(
            text("UPDATE tareas_practicas SET deleted_at = :d WHERE id = :tp"),
            {"tp": str(tp), "d": datetime(2020, 1, 1, tzinfo=UTC)},
        )

        with pytest.raises(HTTPException) as e:
            await return_entrega(entrega.id, user=_docente(), db=db)
        assert e.value.detail == TP_MUERTA
