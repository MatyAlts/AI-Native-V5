"""Corre los test cases del ejercicio contra el artefacto entregado (3.5, 3.6).

**Por qué re-ejecutar en vez de leer la corrida del alumno**: el detalle de
aquélla vive en Redis con `_TTL_SECONDS = 600`, así que a los diez minutos ya
no existe — y el payload que llega al CTR sólo lleva `total/passed/failed`,
sin el detalle por caso. Re-ejecutar además hace la corrección **reproducible**:
el resultado que se le manda a Active-IA se puede volver a producir.

**Por qué antes de contactar a Active-IA**: si el código no compila, la
corrección no puede decir nada útil, y pagarla igual es tirar plata. Se corta
con el error de compilación, que además es la devolución más accionable que
puede recibir el alumno.

El resultado va a `correcciones_ia.tests_snapshot` y viaja en el payload: el
motor cuenta presencia, no vínculo, así que un criterio del tipo "el programa
funciona" necesita algo objetivo detrás.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
import structlog

from evaluation_service.config import settings

log = structlog.get_logger()

# Cuánto esperamos a que el sandbox termine. El wall time por corrida es de
# 10s (ADR-060); con N casos y la cola, 120s es holgado sin ser eterno.
_POLL_TIMEOUT_S = 120.0
_POLL_INTERVAL_S = 1.5


class PreEjecucionError(Exception):
    """No se pudo correr los tests. NUNCA se traduce a una nota."""

    def __init__(self, mensaje: str, *, error_code: str = "SANDBOX_ERROR") -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.error_code = error_code


@dataclass
class ResultadoTests:
    """Lo que se le manda a Active-IA además del código."""

    compila: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    # Detalle por caso, SIN la salida esperada de los ocultos: lo mismo que
    # aplica al enunciado aplica acá.
    casos: list[dict[str, Any]] = field(default_factory=list)
    error_compilacion: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "compila": self.compila,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "casos": self.casos,
            "error_compilacion": self.error_compilacion,
        }


async def correr_tests(
    *,
    ejercicio_id: UUID,
    codigo: str,
    comision_id: UUID,
    headers: dict[str, str],
) -> ResultadoTests:
    """Dispara la ejecución en el sandbox y espera el resultado.

    `headers` lleva la identidad que el execution-service exige. NO se manda
    el `episode_id`: esta corrida no es actividad del alumno —la disparó un
    docente al corregir— y emitir `tests_ejecutados` por ella contaminaría la
    traza cognitiva con un evento que el alumno no produjo.
    """
    base = settings.execution_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{base}/api/v1/executions",
                headers=headers,
                json={
                    "ejercicio_id": str(ejercicio_id),
                    "source_code": codigo,
                    "comision_id": str(comision_id),
                },
            )
    except httpx.HTTPError as e:
        raise PreEjecucionError(
            f"No se pudo contactar al sandbox: {type(e).__name__}", error_code="SANDBOX_UNREACHABLE"
        ) from e

    if resp.status_code == 429:
        raise PreEjecucionError(
            "El sandbox está sin cuota para ejecutar los tests.", error_code="SANDBOX_QUOTA"
        )
    if resp.status_code == 503:
        raise PreEjecucionError(
            "La ejecución de código está desactivada.", error_code="SANDBOX_DISABLED"
        )
    if resp.status_code != 202:
        raise PreEjecucionError(
            f"El sandbox respondió {resp.status_code}.", error_code="SANDBOX_ERROR"
        )

    execution_id = resp.json()["execution_id"]
    return await _esperar_resultado(base, execution_id, headers)


async def _esperar_resultado(
    base: str, execution_id: str, headers: dict[str, str]
) -> ResultadoTests:
    """Poletea hasta que el sandbox termine, con un presupuesto TOTAL.

    Total y no por intento: N intentos de 30s son 30s o son diez minutos según
    cuántos hagan falta, y un docente esperando no puede depender de eso.
    """
    restante = _POLL_TIMEOUT_S
    while restante > 0:
        await asyncio.sleep(_POLL_INTERVAL_S)
        restante -= _POLL_INTERVAL_S
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                r = await http.get(f"{base}/api/v1/executions/{execution_id}", headers=headers)
        except httpx.HTTPError:
            continue  # un fallo de red suelto no cancela; el presupuesto manda
        if r.status_code != 200:
            continue
        cuerpo = r.json()
        if cuerpo.get("state") in ("done", "DONE"):
            return _mapear(cuerpo.get("result") or {})
        if cuerpo.get("state") in ("error", "ERROR"):
            raise PreEjecucionError("El sandbox terminó con error.", error_code="SANDBOX_ERROR")

    raise PreEjecucionError(
        "El sandbox no devolvió resultado a tiempo.", error_code="SANDBOX_TIMEOUT"
    )


def _mapear(result: dict[str, Any]) -> ResultadoTests:
    """Traduce el resultado del sandbox a lo que viaja en la corrección.

    Un fallo de COMPILACIÓN no es un fallo de infraestructura: es información
    sobre el código del alumno, y de las más accionables. Por eso vuelve como
    resultado y no como excepción.
    """
    if result.get("compile_error") or result.get("compilation_error"):
        return ResultadoTests(
            compila=False,
            error_compilacion=str(result.get("compile_error") or result.get("compilation_error"))[
                :4000
            ],
        )

    casos_raw = result.get("test_results") or result.get("results") or []
    casos = [
        {
            "id": c.get("id") or c.get("test_id"),
            "nombre": c.get("name") or c.get("nombre"),
            "paso": bool(c.get("passed")),
            # La salida REAL del alumno sí va: es su código, no el enunciado.
            # Lo que no va es la esperada de un caso oculto.
            "salida_obtenida": (c.get("actual") or c.get("stdout") or "")[:2000],
            "es_publico": c.get("is_public", True) is not False,
        }
        for c in casos_raw
        if isinstance(c, dict)
    ]
    passed = sum(1 for c in casos if c["paso"])
    return ResultadoTests(
        compila=True,
        total=len(casos),
        passed=passed,
        failed=len(casos) - passed,
        casos=casos,
    )
