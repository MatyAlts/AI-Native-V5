"""Aceptacion HU-030 (orquestador, antes de construir; el constructor no la
modifica). Criterios acordados con Juani el 24/11/2026.

C09  Una ejecucion PSeInt en el navegador queda en el CTR con su propio
     runtime (`pseint-ts-X.Y.Z`), no como `pyodide-0.26`.
N01  Un cliente que no manda `runtime` (Python) sigue quedando `pyodide-0.26`.
     Un runtime inventado es 422: el valor va a una cadena append-only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from tutor_service.auth.dependencies import User
from tutor_service.routes import episodes as ruta


class _TutorEspia:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def emit_codigo_ejecutado(
        self, *, episode_id: UUID, user_id: UUID, payload: dict[str, Any]
    ) -> int:
        self.payloads.append(payload)
        return 7


@pytest.fixture
def tutor(monkeypatch) -> _TutorEspia:
    espia = _TutorEspia()

    async def _directo(episode_id, idempotency_key, user, emit):
        return await emit()

    monkeypatch.setattr(ruta, "_get_tutor", lambda: espia)
    monkeypatch.setattr(ruta, "_emitir_con_heal", _directo)
    return espia


def _usuario() -> User:
    return User(
        id=uuid4(),
        tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alumno@utn.edu.ar",
        roles=frozenset({"estudiante"}),
        realm="utn",
    )


async def _emitir(req: ruta.CodigoEjecutadoRequest) -> None:
    await ruta.emit_codigo_ejecutado(uuid4(), req, idempotency_key=None, user=_usuario())


@pytest.mark.asyncio
async def test_c09_pseint_queda_con_su_runtime(tutor) -> None:
    req = ruta.CodigoEjecutadoRequest(
        code="Algoritmo a\nFinAlgoritmo\n",
        stdout="",
        stderr="",
        duration_ms=3,
        runtime="pseint-ts-1.0.0",
    )
    await _emitir(req)
    assert tutor.payloads[-1]["runtime"] == "pseint-ts-1.0.0"


@pytest.mark.asyncio
async def test_n01_sin_runtime_sigue_pyodide(tutor) -> None:
    req = ruta.CodigoEjecutadoRequest(code="print(1)", stdout="1\n", stderr="", duration_ms=3)
    await _emitir(req)
    assert tutor.payloads[-1]["runtime"] == "pyodide-0.26"


@pytest.mark.parametrize("runtime", ["bash", "pseint-ts-", "pseint-ts-1", "pyodide-0.26; rm", ""])
def test_n01_runtime_inventado_es_rechazado(runtime: str) -> None:
    with pytest.raises(ValidationError):
        ruta.CodigoEjecutadoRequest(code="x", duration_ms=1, runtime=runtime)


def test_n01_pyodide_explicito_es_valido() -> None:
    req = ruta.CodigoEjecutadoRequest(code="x", duration_ms=1, runtime="pyodide-0.26")
    assert req.runtime == "pyodide-0.26"
