"""HU-051: el bucle del barrido sobrevive a una pasada que falla.

La aceptación (`tests/aceptacion_hu051`) prueba el bucle contra la base; acá
solo la propiedad que esa no cubre: una excepción de `barrer` no lo mata, y
un tenant que falla no le saca la pasada a los demás.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from classifier_service.services import barrido


@pytest.mark.asyncio
async def test_una_pasada_que_falla_no_mata_el_bucle() -> None:
    roto, sano = uuid4(), uuid4()
    llamadas: list[UUID] = []

    async def barrer_doble(tenant_id: UUID) -> dict[str, int]:
        llamadas.append(tenant_id)
        if tenant_id == roto:
            raise RuntimeError("CTR caido")
        return {}

    with patch.object(barrido, "barrer", barrer_doble):
        tarea = asyncio.create_task(barrido.bucle(0.01, [roto, sano]))
        try:
            for _ in range(100):
                await asyncio.sleep(0.01)
                if llamadas.count(sano) >= 2:
                    break
            assert not tarea.done(), "el bucle murio por una pasada fallida"
        finally:
            tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarea

    assert llamadas.count(roto) >= 2, "despues de fallar, el tenant se vuelve a barrer"
    assert llamadas.count(sano) >= 2, "el tenant que falla no le saca la pasada al otro"


@pytest.mark.asyncio
async def test_toma_los_tenants_registrados_despues_de_arrancar() -> None:
    tenants: list[UUID] = []
    llamadas: list[UUID] = []

    async def barrer_doble(tenant_id: UUID) -> dict[str, int]:
        llamadas.append(tenant_id)
        return {}

    with patch.object(barrido, "barrer", barrer_doble):
        tarea = asyncio.create_task(barrido.bucle(0.01, tenants))
        try:
            await asyncio.sleep(0.03)
            nuevo = uuid4()
            tenants.append(nuevo)
            for _ in range(100):
                await asyncio.sleep(0.01)
                if nuevo in llamadas:
                    break
        finally:
            tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarea

    assert nuevo in llamadas
