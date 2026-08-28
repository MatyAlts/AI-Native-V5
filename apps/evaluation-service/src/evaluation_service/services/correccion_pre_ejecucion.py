"""Corre los test cases del ejercicio contra el artefacto entregado (3.5, 3.6).

**Por qué re-ejecutar en vez de leer la corrida del alumno**: el detalle de
aquélla vive en Redis con `_TTL_SECONDS = 600`, así que a los diez minutos ya
no existe — y el payload que llega al CTR sólo lleva `total/passed/failed`,
sin el detalle por caso. Re-ejecutar además hace la corrección **reproducible**:
el resultado que se le manda a Active-IA se puede volver a producir.

**Por qué antes de contactar a Active-IA** (y no porque corte — desde el 19/08
ya no corta): el resultado viaja CON el envío, así que hay que tenerlo antes. Si el código no compila, la
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
            # Defensivo: `ExecutionState` sólo tiene `queued|running|done`, así
            # que hoy esto no se alcanza. Un fallo del sandbox llega como
            # `state=done` con `outcome=infrastructure_failure`, y lo corta
            # `_mapear`. Se conserva por si el contrato del otro lado crece.
            raise PreEjecucionError("El sandbox terminó con error.", error_code="SANDBOX_ERROR")

    raise PreEjecucionError(
        "El sandbox no devolvió resultado a tiempo.", error_code="SANDBOX_TIMEOUT"
    )


def _mapear(result: dict[str, Any]) -> ResultadoTests:
    """Traduce el resultado del sandbox a lo que viaja en la corrección.

    **Las claves son las que el `execution-service` produce de verdad**, y eso
    hay que decirlo porque hasta el 2026-08-27 no lo eran. Esta función leía
    `compile_error`, `test_results`, `passed` por caso y `actual` — ninguna de
    las cuatro existe. El productor es `execution_service.services.executor`
    (`to_client_payload`) y emite `outcome`, `cases`, `status` y `got`.

    Ni una clave coincidía, así que `casos_raw` salía SIEMPRE vacío y, al no
    encontrar `compile_error`, la función salía por el camino feliz. **Toda
    corrección de producción mandaba a Active-IA el mismo objeto:**
    `{"compila": true, "error_compilacion": null, "total": 0, "pasados": 0,
    "casos": []}`. Un alumno cuyo Java no compilaba viajaba como `compila: true`.

    Y rompía la regla de oro del epic por la puerta de atrás: un
    `infrastructure_failure` del sandbox se guarda con `state=done` (ver
    `executions.py`), así que llegaba acá, no matcheaba ninguna clave, y volvía
    como `compila=True` con cero tests. **Un fallo de infraestructura entraba
    como evidencia positiva sobre la que el motor calcula una nota.** El CHECK
    de la base protege el ESTADO; no protegía la EVIDENCIA.

    Por eso ahora el `outcome` gobierna, y el default es cerrado: un `outcome`
    que no reconocemos levanta en vez de devolver un resultado optimista. Es la
    misma postura que el resto del epic — sin dato, no hay nota.
    """
    outcome = str(result.get("outcome") or "").lower()

    # El sandbox no pudo correr. NO es información sobre el código del alumno,
    # así que no puede viajar como resultado: se levanta y la corrección cierra
    # en `error` sin nota.
    if outcome == "infrastructure_failure":
        raise PreEjecucionError(
            "El sandbox no pudo ejecutar los tests. No se envió nada a corregir.",
            error_code="SANDBOX_ERROR",
        )

    # Un fallo de COMPILACIÓN sí es información sobre el código del alumno, y de
    # las más accionables. Vuelve como resultado, no como excepción — y desde el
    # 19/08 tampoco corta: se manda igual, con el estado explícito.
    if outcome == "compilation_error":
        return ResultadoTests(
            compila=False,
            error_compilacion=str(result.get("compile_output") or "")[:4000] or None,
        )

    if outcome != "completed":
        # Un contrato que no reconocemos es exactamente el bug que esto viene a
        # cerrar. Falla cerrado y deja rastro con el valor crudo.
        raise PreEjecucionError(
            f"El sandbox devolvió un resultado que no se entiende (outcome={outcome!r}).",
            error_code="SANDBOX_ERROR",
        )

    casos = [
        {
            "id": c.get("id"),
            "nombre": c.get("name"),
            "paso": str(c.get("status") or "").lower() == "pass",
            # La salida REAL del alumno sí va: es su código, no el enunciado.
            # Lo que no va es la esperada de un caso oculto.
            "salida_obtenida": str(c.get("got") or "")[:2000],
            "es_publico": c.get("is_public", True) is not False,
        }
        for c in result.get("cases") or []
        if isinstance(c, dict)
    ]

    # Los conteos salen del sandbox, no se recalculan desde `casos`: él sabe de
    # casos que no emitió detalle (un `skipped` sin runtime, por ejemplo), y dos
    # números que pueden contradecirse le dan al motor la chance de creerle al
    # equivocado.
    total = int(result.get("total") or 0)
    passed = int(result.get("passed") or 0)
    failed = int(result.get("failed") or max(total - passed, 0))
    return ResultadoTests(
        compila=True,
        total=total,
        passed=passed,
        failed=failed,
        casos=casos,
    )
