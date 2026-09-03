"""Dos estados que se veían idénticos y no lo son.

Los dos cambios que cubre este archivo salen del mismo incidente (2026-09-03) y
del mismo problema de fondo: **el sistema se veía igual cuando trabajaba que
cuando estaba trabado.**

1. Un trabajo que no consigue cupo del semáforo era COMPLETAMENTE invisible: el
   `async with` iba antes del `try`, antes del reloj y antes de cualquier log,
   así que no arrancaba, no fallaba y no avisaba. Su fila quedaba en `pending`,
   que en el panel del docente se ve igual que "está trabajando".

2. El presupuesto del poll del sandbox decía ser total y no lo era: descontaba
   sólo el `sleep` (1,5s) y no lo que tardaba el request (hasta 15s). Con las
   consultas lentas el bucle corría veintidós minutos de reloj creyendo haber
   gastado 120 segundos, y el que terminaba cortando era el presupuesto de
   afuera — que cancela **sin logear el motivo**.

Los dos se verificaron por reversión degradando el código, no borrándolo.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services import correccion_worker as worker
from evaluation_service.services.correccion_ia import mapear_error_activeia
from evaluation_service.services.correccion_pre_ejecucion import (
    PreEjecucionError,
    _esperar_resultado,
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _fila() -> CorreccionIA:
    c = CorreccionIA(
        tenant_id=TENANT,
        entrega_id=uuid4(),
        orden=1,
        disparado_por=uuid4(),
        rubrica_id="nativa:abc",
        artefacto_sha256="s",
    )
    c.id = uuid4()
    c.estado = "pending"
    c.nota_100 = None
    return c


def _sesion_con(fila: CorreccionIA) -> MagicMock:
    ctx = MagicMock()
    s = MagicMock()
    s.get = AsyncMock(return_value=fila)
    ctx.__aenter__ = AsyncMock(return_value=s)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSinCupoNoEsInvisible:
    async def test_el_que_no_consigue_turno_cierra_con_SIN_CUPO(self) -> None:
        """Antes esperaba para siempre, en `pending`, sin una sola línea de log.

        El docente veía "Corrigiendo..." indefinidamente sobre un trabajo que
        no había arrancado — y encima la cuota del día quedaba consumida por
        una fila que nunca se cerraba.
        """
        fila = _fila()
        # Los 3 cupos tomados y nadie los suelta.
        for _ in range(worker._MAX_CONCURRENTES):
            await worker._semaforo.acquire()

        try:
            with (
                patch.object(worker, "tenant_session", MagicMock(return_value=_sesion_con(fila))),
                patch.object(worker, "ESPERA_MAX_CUPO_S", 0.05),
            ):
                r = await worker.con_semaforo_y_presupuesto(
                    lambda: asyncio.sleep(0),
                    tenant_id=TENANT,
                    correccion_id=fila.id,
                )
        finally:
            for _ in range(worker._MAX_CONCURRENTES):
                worker._semaforo.release()

        assert r is None
        assert fila.estado == "error"
        assert fila.nota_100 is None, "un fallo de infraestructura NUNCA es una nota"
        assert fila.error_code == "SIN_CUPO"

    def test_SIN_CUPO_ofrece_reintentar(self) -> None:
        """`es_infraestructura` es lo ÚNICO que decide si la UI muestra el botón,
        y el flag NO se persiste: la pantalla lo re-deriva del código guardado.
        Un código que el flujo emite y no está en el set pinta rojo y esconde el
        botón — que es lo que le pasó a `PROCESO_INTERRUMPIDO`, cuyo propio
        mensaje decía "podés volver a dispararla"."""
        _, infra = mapear_error_activeia("SIN_CUPO", "")

        assert infra, "SIN_CUPO esconde el boton sobre algo que se destraba solo"

    async def test_el_cupo_se_devuelve_siempre(self) -> None:
        """El `release` pasó a ser MANUAL al sacarle el `async with`. Si se
        escapa un camino, el semáforo se agota y no vuelve nunca."""
        libres = worker._semaforo._value

        async def _revienta():
            raise RuntimeError("boom")

        with patch.object(worker, "_cerrar_sin_escapar", AsyncMock()):
            await worker.con_semaforo_y_presupuesto(
                _revienta, tenant_id=TENANT, correccion_id=uuid4()
            )

        assert worker._semaforo._value == libres, "el cupo no se devolvio tras una excepcion"


class TestElPresupuestoDelPollEsDeReloj:
    async def test_una_consulta_lenta_consume_presupuesto(self) -> None:
        """La propiedad entera, en una línea: si cada consulta tarda, el
        presupuesto se agota igual.

        Antes el contador sólo descontaba el `sleep`, así que consultas de 15s
        no gastaban NADA del presupuesto: el bucle podía correr veintidós
        minutos de reloj creyendo llevar 120 segundos.
        """
        consultas = 0

        async def _lenta(*a, **k):
            nonlocal consultas
            consultas += 1
            await asyncio.sleep(0.05)  # "lenta" a escala del test
            raise httpx.ConnectError("sin contacto")

        cliente = MagicMock()
        cliente.__aenter__ = AsyncMock(return_value=MagicMock(get=_lenta))
        cliente.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("evaluation_service.services.correccion_pre_ejecucion._POLL_TIMEOUT_S", 0.2),
            patch("evaluation_service.services.correccion_pre_ejecucion._POLL_INTERVAL_S", 0.01),
            patch("httpx.AsyncClient", MagicMock(return_value=cliente)),
            pytest.raises(PreEjecucionError) as e,
        ):
            await _esperar_resultado("http://sandbox", "exec-1", {})

        assert e.value.error_code == "SANDBOX_TIMEOUT"
        # Con el presupuesto de reloj: 0,2s / (0,01 sleep + 0,05 request) ≈ 3-4.
        # Descontando sólo el sleep serían ~20 vueltas y 1,2s de reloj.
        assert consultas <= 6, (
            f"el presupuesto no cuenta el tiempo de los requests: {consultas} consultas"
        )
