"""Tope de stdout/stderr del evento `codigo_ejecutado` (fix sobre HU-030).

El 24/11/2026 un ciclo infinito con `Escribir` en PSeInt mandaba 11 MB en un
solo `codigo_ejecutado`: el nginx acepta hasta 50 MB y nada lo frenaba antes
de la cadena append-only. El navegador ya corta antes (tope del interprete);
esto es la red del servidor para cualquier cliente.

T01  Una salida dentro del tope llega intacta.
T02  Una salida mas larga se RECORTA (no se rechaza: un 422 perderia el
     evento entero de la cadena) y dice cuanto se omitio.
T03  El evento que se emite al CTR lleva la salida ya recortada.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from tutor_service.auth.dependencies import User
from tutor_service.routes import episodes as ruta

TOPE = ruta.SALIDA_CTR_MAX_CHARS


def _req(stdout: str = "", stderr: str = "") -> ruta.CodigoEjecutadoRequest:
    return ruta.CodigoEjecutadoRequest(
        code="Algoritmo a\nFinAlgoritmo\n",
        stdout=stdout,
        stderr=stderr,
        duration_ms=3,
        runtime="pseint-ts-1.2.0",
    )


def test_t01_dentro_del_tope_llega_intacta() -> None:
    texto = "x" * TOPE
    req = _req(stdout=texto, stderr="Linea 3: error")
    assert req.stdout == texto
    assert req.stderr == "Linea 3: error"


def test_t02_salida_larga_se_recorta_y_avisa() -> None:
    texto = "hola mundo\n" * 1_000_000  # los 11 MB medidos
    req = _req(stdout=texto, stderr="e" * (TOPE + 5))
    assert req.stdout.startswith(texto[:TOPE])
    assert f"{len(texto) - TOPE} caracteres omitidos" in req.stdout
    assert len(req.stdout) < TOPE + 100
    assert "5 caracteres omitidos" in req.stderr


class _TutorEspia:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def emit_codigo_ejecutado(
        self, *, episode_id: UUID, user_id: UUID, payload: dict[str, Any]
    ) -> int:
        self.payloads.append(payload)
        return 7


@pytest.mark.asyncio
async def test_t03_el_evento_al_ctr_lleva_la_salida_recortada(monkeypatch) -> None:
    espia = _TutorEspia()

    async def _directo(episode_id, idempotency_key, user, emit):
        return await emit()

    monkeypatch.setattr(ruta, "_get_tutor", lambda: espia)
    monkeypatch.setattr(ruta, "_emitir_con_heal", _directo)
    usuario = User(
        id=uuid4(),
        tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alumno@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )
    await ruta.emit_codigo_ejecutado(
        uuid4(), _req(stdout="y" * (TOPE * 3)), idempotency_key=None, user=usuario
    )
    stdout = espia.payloads[-1]["stdout"]
    assert len(stdout) < TOPE + 100
    assert "caracteres omitidos" in stdout
