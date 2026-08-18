"""El Epic 3 contra Postgres REAL.

Existe por un bloqueante que ningun mock podia ver: `asyncio.wait_for` cancela
la corrutina, la cancelacion llega como `CancelledError` —que hereda de
`BaseException`, no de `Exception`— y el `except Exception` del ejecutor no la
agarraba. La correccion quedaba `running` para siempre, girando en la pantalla
del docente, y el reconciliador no la levantaba porque corre una sola vez al
arrancar y solo sobre filas viejas.

El segundo: reintentar una correccion fallida chocaba contra el UNIQUE y
devolvia 500. Un mock no tiene indice, asi que nunca lo iba a ver — la misma
leccion de la vuelta 2, en una tabla nueva.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration -v
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.config import settings
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services.correccion_ia import reabrir_para_reintento
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    # `tenant_session` usa `settings.academic_db_url`; el fixture apunta a la
    # misma base para que lo que escribe el test lo vea el reconciliador.
    settings.academic_db_url = _DSN or ""
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
    # El engine global de `db.session` se cachea a nivel modulo y queda atado
    # al event loop del test que lo creo primero. Sin esto, el segundo test que
    # use `tenant_session` (el reconciliador) revienta con "Event loop is
    # closed". Es un artefacto del arnes, no del codigo.
    import evaluation_service.db.session as _sess

    if _sess._engine is not None:
        await _sess._engine.dispose()
    _sess._engine = None
    _sess._session_factory = None


async def _una_entrega(db: AsyncSession) -> UUID:
    row = await db.execute(text("SELECT id FROM entregas LIMIT 1"))
    eid = row.scalar_one_or_none()
    if eid is None:
        pytest.skip("la base no tiene entregas")
    return eid


def _correccion(entrega_id: UUID, **over) -> CorreccionIA:
    base = {
        "tenant_id": TENANT,
        "entrega_id": entrega_id,
        "orden": 1,
        "disparado_por": uuid.uuid4(),
        "rubrica_id": "r1",
        "estado": "pending",
        "artefacto_sha256": "sha-de-prueba",
    }
    base.update(over)
    return CorreccionIA(**base)


class TestElCheckDeLaBase:
    """La propiedad central del epic, hecha constraint."""

    async def test_una_correccion_fallida_NO_puede_llevar_nota(self, db: AsyncSession) -> None:
        """Un cero que en realidad significa "el servicio no respondio"
        termina en el legajo de una persona."""
        db.add(_correccion(await _una_entrega(db), estado="error", nota_100=Decimal("0.00")))
        with pytest.raises(IntegrityError):
            await db.flush()

    async def test_una_correccion_done_TIENE_que_llevar_nota(self, db: AsyncSession) -> None:
        """El control positivo: el CHECK rechaza las dos direcciones, asi que
        el de arriba no pasa por rechazar todo."""
        db.add(_correccion(await _una_entrega(db), estado="done", nota_100=None))
        with pytest.raises(IntegrityError):
            await db.flush()

    async def test_una_correccion_done_con_nota_entra(self, db: AsyncSession) -> None:
        db.add(_correccion(await _una_entrega(db), estado="done", nota_100=Decimal("87.00")))
        await db.flush()


class TestReintentar:
    async def test_insertar_una_segunda_correccion_igual_choca(self, db: AsyncSession) -> None:
        """El UNIQUE no excluye las fallidas: por eso el reintento NO puede
        ser un INSERT nuevo, y tiene que reusar la fila."""
        entrega_id = await _una_entrega(db)
        db.add(_correccion(entrega_id, estado="error", error_code="GEMINI_OVERLOADED"))
        await db.flush()

        db.add(_correccion(entrega_id, estado="pending"))
        with pytest.raises(IntegrityError):
            await db.flush()

    async def test_reabrir_deja_la_fila_lista_y_sin_nota(self, db: AsyncSession) -> None:
        entrega_id = await _una_entrega(db)
        c = _correccion(
            entrega_id,
            estado="error",
            error_code="GEMINI_OVERLOADED",
            error_detail="saturado",
            finished_at=datetime.now(UTC),
        )
        db.add(c)
        await db.flush()

        assert await reabrir_para_reintento(db, c) is True

        # Se lee la FILA, no el objeto: `reabrir` ahora hace un UPDATE con la
        # guarda `estado='error'` en el WHERE, asi que lo que importa es lo que
        # quedo en la base, no lo que tiene la sesion en memoria.
        fila = (
            await db.execute(
                text(
                    "SELECT estado, nota_100, error_code, finished_at, started_at "
                    "FROM correcciones_ia WHERE id = :i"
                ),
                {"i": str(c.id)},
            )
        ).one()
        assert fila[0] == "pending"
        assert fila[1] is None
        assert fila[2] is None
        assert fila[3] is None
        assert fila[4] is None

    async def test_no_reabre_una_que_esta_en_vuelo(self, db: AsyncSession) -> None:
        """Reiniciar una `running` perderia el trabajo que se esta pagando
        ahora mismo."""
        c = _correccion(await _una_entrega(db), estado="running")
        assert await reabrir_para_reintento(db, c) is False

    async def test_no_reabre_una_que_salio_bien(self, db: AsyncSession) -> None:
        c = _correccion(await _una_entrega(db), estado="done", nota_100=Decimal("90.00"))
        assert await reabrir_para_reintento(db, c) is False


class TestElPresupuestoCierraLaFila:
    async def test_agotar_el_presupuesto_NO_deja_la_correccion_running(
        self, db: AsyncSession
    ) -> None:
        """EL BLOQUEANTE.

        `wait_for` cancela, la cancelacion es `BaseException`, el
        `except Exception` del ejecutor no la ve. Antes de este arreglo la
        fila quedaba `running` para siempre.
        """
        from evaluation_service.services import correccion_worker as worker

        entrega_id = await _una_entrega(db)
        c = _correccion(entrega_id, estado="running", started_at=datetime.now(UTC))
        db.add(c)
        await db.flush()
        # `cerrar_por_timeout` abre su propia sesion: la fila tiene que estar
        # visible fuera de esta transaccion.
        await db.commit()

        try:

            async def _nunca_termina() -> None:
                await asyncio.sleep(30)

            with patch.object(worker, "PRESUPUESTO_TOTAL_S", 0.3):
                await worker.con_semaforo_y_presupuesto(
                    _nunca_termina, tenant_id=TENANT, correccion_id=c.id
                )

            await db.refresh(c)
            assert c.estado == "error", "quedo 'running' para siempre"
            assert c.nota_100 is None
            assert c.error_code == "TIMEOUT"
            assert c.finished_at is not None
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()

    async def test_el_semaforo_se_libera_tras_el_timeout(self) -> None:
        """Si no se liberara, la primera correccion colgada dejaria el servicio
        sin poder correr ninguna otra."""
        from evaluation_service.services import correccion_worker as worker

        antes = worker._semaforo._value

        async def _nunca_termina() -> None:
            await asyncio.sleep(30)

        with (
            patch.object(worker, "PRESUPUESTO_TOTAL_S", 0.2),
            patch.object(worker, "cerrar_por_timeout", _noop),
        ):
            await worker.con_semaforo_y_presupuesto(
                _nunca_termina, tenant_id=TENANT, correccion_id=uuid.uuid4()
            )
        assert worker._semaforo._value == antes


async def _noop(*_a, **_k) -> None:
    return None


class TestReconciliador:
    async def test_cierra_una_running_vieja_sin_nota(self, db: AsyncSession) -> None:
        """Un deploy a mitad deja filas `running`. Se cierran como error de
        infraestructura: el proceso se murio, que no dice nada del codigo del
        alumno."""
        from evaluation_service.services.correccion_worker import reconciliar_running

        c = _correccion(
            await _una_entrega(db),
            estado="running",
            started_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db.add(c)
        await db.flush()
        await db.commit()

        try:
            assert await reconciliar_running(TENANT) >= 1
            await db.refresh(c)
            assert c.estado == "error"
            assert c.nota_100 is None
            assert c.error_code == "PROCESO_INTERRUMPIDO"
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()

    async def test_no_toca_una_running_reciente(self, db: AsyncSession) -> None:
        """Una correccion que arranco hace un minuto esta corriendo de verdad."""
        from evaluation_service.services.correccion_worker import reconciliar_running

        c = _correccion(await _una_entrega(db), estado="running", started_at=datetime.now(UTC))
        db.add(c)
        await db.flush()
        await db.commit()

        try:
            await reconciliar_running(TENANT)
            await db.refresh(c)
            assert c.estado == "running"
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()


class TestReintentoConcurrente:
    async def test_dos_reintentos_a_la_vez_reabren_UNA_sola_vez(self, db: AsyncSession) -> None:
        """Chequear en memoria y despues escribir deja una ventana: dos
        requests que leen la fila antes de que cualquiera commitee la ven las
        dos en `error`, las dos devuelven True, y las dos mandan un trabajo
        sobre la MISMA fila — dos corridas del sandbox y **dos subidas a
        Active-IA**, que se pagan las dos.

        Con la condicion `estado='error'` en el WHERE, la segunda actualiza
        cero filas y se va.
        """
        entrega_id = await _una_entrega(db)
        c = _correccion(entrega_id, estado="error", error_code="GEMINI_OVERLOADED")
        db.add(c)
        await db.flush()
        await db.commit()

        engine = create_async_engine(_DSN or "")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:

            async def _un_reintento() -> bool:
                async with factory() as s2:
                    await s2.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"),
                        {"t": str(TENANT)},
                    )
                    fila = await s2.get(CorreccionIA, c.id)
                    assert fila is not None
                    ok = await reabrir_para_reintento(s2, fila)
                    await s2.commit()
                    return ok

            r1, r2 = await asyncio.gather(_un_reintento(), _un_reintento())
            assert [r1, r2].count(True) == 1, (
                f"reabrieron {[r1, r2].count(True)} de 2: se dispararian dos trabajos "
                "sobre la misma fila, y dos subidas a Active-IA"
            )
        finally:
            await engine.dispose()
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()


class TestElBloqueanteNoVuelvePorNingunaPuerta:
    """Cuatro piezas del mismo arreglo. Cada una sola alcanza para que la
    correccion vuelva a quedar colgada."""

    async def test_una_correccion_ya_done_no_se_pisa_con_TIMEOUT(self, db: AsyncSession) -> None:
        """Si el timeout cae justo despues de que la correccion termino bien,
        pisarla convertiria un resultado bueno en un TIMEOUT sin nota. Perder
        un resultado bueno es peor que no cerrar uno malo."""
        from evaluation_service.services.correccion_worker import cerrar_por_timeout

        c = _correccion(await _una_entrega(db), estado="done", nota_100=Decimal("91.00"))
        db.add(c)
        await db.flush()
        await db.commit()

        try:
            await cerrar_por_timeout(TENANT, c.id)
            await db.refresh(c)
            assert c.estado == "done"
            assert c.nota_100 == Decimal("91.00")
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()

    async def test_cerrar_por_timeout_limpia_la_nota(self, db: AsyncSession) -> None:
        """Si no la limpiara, el CHECK dispararia un IntegrityError, el
        rollback dejaria la fila en `running` y **el bloqueante volveria por
        esa puerta**. El test lo prueba al derecho: la fila termina cerrada."""
        from evaluation_service.services.correccion_worker import cerrar_por_timeout

        c = _correccion(await _una_entrega(db), estado="running", started_at=datetime.now(UTC))
        db.add(c)
        await db.flush()
        await db.commit()

        try:
            # Se ensucia la nota en memoria: en la base no puede estar puesta
            # sobre una `running` (el CHECK), pero `cerrar_por_timeout` la
            # limpia explicitamente y esto verifica que el UPDATE resultante
            # entre sin chocar.
            await cerrar_por_timeout(TENANT, c.id)
            await db.refresh(c)
            assert c.estado == "error"
            assert c.nota_100 is None
            assert c.error_code == "TIMEOUT"
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()

    async def test_el_ejecutor_re_lanza_la_cancelacion(self) -> None:
        """`CancelledError` es lo unico que nunca hay que tragarse: si el
        ejecutor la tragara, `wait_for` no veria el timeout, no habria
        `TimeoutError`, y nadie cerraria la fila. Es el mecanismo exacto del
        bloqueante original."""
        from evaluation_service.services import correccion_ejecutor as mod

        # La cancelacion tiene que venir de DENTRO del `try`, que arranca
        # despues del primer `tenant_session`. Hacerla salir de ese primer
        # bloque probaria que Python propaga una excepcion, no que el
        # `except asyncio.CancelledError` re-lanza.
        correccion = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=uuid.uuid4(),
            orden=1,
            disparado_por=uuid.uuid4(),
            rubrica_id="r1",
            artefacto_sha256="s",
        )
        correccion.id = uuid.uuid4()
        correccion.nota_100 = None
        sesion = MagicMock()
        sesion.get = AsyncMock(return_value=correccion)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=sesion)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=ctx)),
            patch.object(mod, "correr_tests", AsyncMock(side_effect=asyncio.CancelledError())),
            pytest.raises(asyncio.CancelledError),
        ):
            await mod.ejecutar_correccion(
                correccion_id=uuid.uuid4(),
                tenant_id=TENANT,
                user_id=uuid.uuid4(),
                comision_id=uuid.uuid4(),
                ejercicio_id=uuid.uuid4(),
                codigo="x",
                language="java",
                alumno_nombre="a",
                activeia_comision_id="1",
                headers_sandbox={},
            )

    async def test_el_poll_corta_solo_sin_depender_del_envoltorio(self) -> None:
        """Un `while True` que solo corta por cancelacion externa depende de
        que el envoltorio este puesto. Y salir por cancelacion es peor que
        salir por decision propia: la primera no puede cerrar la fila."""
        from evaluation_service.services import correccion_ejecutor as mod

        cliente = MagicMock()
        cliente.request = AsyncMock(return_value=MagicMock(status_code=404))

        with (
            patch.object(mod, "_POLL_INTERVAL_S", 0.01),
            patch.object(mod, "_POLL_PRESUPUESTO_S", 0.05),
        ):
            r = await mod._poletear(cliente, "7")

        assert r["error_code"] == "TIMEOUT"
        assert "nota_100" not in r


class TestPendingHuerfana:
    async def test_una_pending_vieja_tambien_se_reconcilia(self, db: AsyncSession) -> None:
        """`background.add_task` corre DESPUES del 202. Si el proceso muere en
        esa ventana la fila queda `pending`, con `started_at` en NULL — y para
        el docente es indistinguible de una `running` colgada, porque el panel
        poletea con los dos estados. Ademas consume una correccion de su cuota
        que nunca se libera."""
        from evaluation_service.services.correccion_worker import reconciliar_running

        c = _correccion(await _una_entrega(db), estado="pending", started_at=None)
        db.add(c)
        await db.flush()
        # `created_at` lo pone el server default; se retrasa a mano para que
        # califique como huerfana.
        await db.execute(
            text(
                "UPDATE correcciones_ia SET created_at = now() - interval '2 hours' WHERE id = :i"
            ),
            {"i": str(c.id)},
        )
        await db.commit()

        try:
            assert await reconciliar_running(TENANT) >= 1
            await db.refresh(c)
            assert c.estado == "error"
            assert c.nota_100 is None
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()

    async def test_una_pending_recien_creada_no_se_toca(self, db: AsyncSession) -> None:
        """Una correccion creada hace un segundo esta esperando el semaforo,
        no huerfana."""
        from evaluation_service.services.correccion_worker import reconciliar_running

        c = _correccion(await _una_entrega(db), estado="pending", started_at=None)
        db.add(c)
        await db.flush()
        await db.commit()

        try:
            await reconciliar_running(TENANT)
            await db.refresh(c)
            assert c.estado == "pending"
        finally:
            await db.execute(text("DELETE FROM correcciones_ia WHERE id = :i"), {"i": str(c.id)})
            await db.commit()
