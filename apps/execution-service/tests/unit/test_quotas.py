"""Tests de las cuotas de ejecucion (tareas 4.3 y 4.4).

El test central es `test_falla_cerrado_si_el_contador_no_responde`: verifica que
esta capa se comporta al REVES que el resto de los limites del sistema, y que
esa diferencia es deliberada.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from execution_service.config import settings
from execution_service.services.quotas import (
    QuotaUnavailableError,
    check_and_consume,
)


class _FakeRedis:
    """Contador en memoria con el shape de pipeline que usa `check_and_consume`."""

    def __init__(self, *, falla: bool = False, inicial: int = 0) -> None:
        self.falla = falla
        self.valor = inicial

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, store: _FakeRedis) -> None:
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def incr(self, key: str) -> None:
        if not self._store.falla:
            self._store.valor += 1

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        return None

    async def execute(self):
        if self._store.falla:
            raise ConnectionError("redis caido")
        return [self._store.valor, True]


async def test_permite_mientras_haya_cuota() -> None:
    decision = await check_and_consume(
        tenant_id=uuid4(), user_id=uuid4(), client=_FakeRedis(inicial=0)
    )
    assert decision.allowed is True
    assert decision.remaining == settings.execution_quota_max_per_window - 1


async def test_rechaza_al_pasarse_del_limite() -> None:
    gastado = settings.execution_quota_max_per_window
    decision = await check_and_consume(
        tenant_id=uuid4(), user_id=uuid4(), client=_FakeRedis(inicial=gastado)
    )
    assert decision.allowed is False
    assert decision.remaining == 0


async def test_el_mensaje_de_limite_le_dice_al_alumno_que_puede_seguir() -> None:
    """Tarea 4.4 — quedarse sin cuota NO bloquea el episodio.

    El alumno sigue escribiendo codigo y conversando con el tutor. Ejecutar es
    un agregado, no un bloqueante.
    """
    decision = await check_and_consume(
        tenant_id=uuid4(),
        user_id=uuid4(),
        client=_FakeRedis(inicial=settings.execution_quota_max_per_window),
    )
    assert "tutor" in decision.reason.lower()
    assert "limite" in decision.reason.lower()


async def test_falla_cerrado_si_el_contador_no_responde() -> None:
    """Tarea 4.3. **No cambiar a "permitir" por consistencia con el resto.**

    El rate-limit del chat degrada ABIERTO a proposito: bloquear al tutor por un
    Redis caido es peor que servir mensajes de mas. Acá la consecuencia es otra:
    cada ejecucion cuesta CPU y dinero en el sandbox, y sin contador un alumno
    lo satura sin techo.

    La consistencia no es un valor cuando los dos casos tienen consecuencias
    distintas.
    """
    with pytest.raises(QuotaUnavailableError):
        await check_and_consume(tenant_id=uuid4(), user_id=uuid4(), client=_FakeRedis(falla=True))
