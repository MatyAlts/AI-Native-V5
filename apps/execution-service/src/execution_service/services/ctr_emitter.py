"""Emision del evento de trazabilidad de una corrida (tareas 5.1, 5.2 y 5.4).

**La regla central de este modulo: una corrida donde no se ejecuto NINGUN caso
NO emite evento.** El fallo de infraestructura es un caso particular de eso; la
corrida vacia es el otro.

Suena obvio y no lo es. D4 resuelve que una caida del sandbox no se registre
como "el alumno fallo todos los tests", y para eso `RunResult.failed` devuelve 0
ante `INFRASTRUCTURE_FAILURE`. Pero eso solo, emitiendo igual, crea el problema
inverso — y peor.

El etiquetador N1-N4 (`classifier-service/services/event_labeler.py`, regla de
`tests_ejecutados` en v1.2.0) hace:

    failed > 0                          -> N3  (validacion funcional)
    failed == 0 y tutor lejano (>=60s)  -> N4  (apropiacion reflexiva)

Con `failed = 0` por fallo de infraestructura, un sandbox caido caeria en la
segunda rama: el episodio quedaria etiquetado como **apropiacion reflexiva**, el
nivel mas alto del modelo de la tesis, porque el servidor se rompio. Es peor que
el problema que D4 evita: no degrada la clasificacion, la infla.

Por eso, ante `INFRASTRUCTURE_FAILURE` no se emite nada. El evento se llama
`tests_ejecutados`; si no se ejecutaron, no hay evento. Pedagogicamente no paso
nada, y el alumno ve el error en pantalla.

Esa ultima frase es el enunciado general, y durante un tiempo se aplico solo a
la mitad. La otra mitad es la **corrida vacia**: `run.total == 0` con outcome
`COMPLETED`, que sale de un ejercicio sin casos de prueba (`test_cases` admite
`[]`) o de un lenguaje sin runtime (todos los casos `skipped`, que `total`
excluye). Mismo payload `failed=0`, misma lectura N4 del labeler, y sin
necesidad de que nada se rompa: alcanza con un ejercicio mal autorado, y el
alumno ni se entera. Ver `should_emit`.

Arreglarlo del otro lado —que el labeler mire un campo nuevo— obligaria a
bumpear `LABELER_VERSION`, re-etiquetar los historicos y escribir un ADR. No
vale para un caso que se resuelve no emitiendo.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid5

from execution_service.services.result_mapper import RunOutcome, RunResult

logger = logging.getLogger(__name__)

# Namespace fijo para derivar la Idempotency-Key de una ejecucion (tarea 5.4).
# UUID v5 = determinista: el mismo execution_id produce siempre la misma clave,
# asi que un reintento del emisor no agrega un segundo evento a la cadena.
_IDEMPOTENCY_NAMESPACE = UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")


def idempotency_key(execution_id: UUID) -> str:
    """Clave estable derivada del id de la ejecucion.

    El endpoint de registro de casos NO usaba clave de idempotencia, a diferencia
    de otros eventos del tutor. Con ejecucion en el navegador perder un evento
    era gratis; con ejecucion server-side la corrida ya se pago en computo,
    dinero y cuota del alumno, y si el evento se pierde, para el clasificador esa
    ejecucion nunca existio.
    """
    return str(uuid5(_IDEMPOTENCY_NAMESPACE, str(execution_id)))


def should_emit(run: RunResult) -> bool:
    """False cuando NO SE EJECUTO NINGUN CASO. Ver el docstring del modulo.

    Dos formas de que no se haya ejecutado nada, y las dos terminan en el mismo
    payload —`total = passed = failed = 0`— que el labeler lee como N4:

    1. **Fallo de infraestructura.** El caso original de D4: el sandbox se cayo.
       `RunResult.failed` devuelve 0 por diseno para no registrar la caida como
       "el alumno fallo todos los tests", y emitir igual invertia el problema
       hacia el lado peor.

    2. **Corrida vacia** (`run.total == 0` con outcome `COMPLETED`). Es la
       tercera puerta a `failed == 0`, y la unica que no necesita que nada se
       rompa: alcanza un ejercicio mal autorado. `test_cases` admite `[]`, con
       lo cual `run_cases` devuelve `cases=[]`; y un lenguaje sin runtime deja
       todos los casos `skipped`, que `total` excluye por definicion ("solo los
       casos que efectivamente corrieron"). En los dos el alumno apreta
       "Ejecutar", no ve nada raro, y su episodio queda en el corpus de la
       tesis etiquetado N4 —apropiacion reflexiva, el nivel mas alto del
       modelo— por una corrida donde no se ejecuto una sola linea de test.

    La regla es UNA y ya estaba escrita en el docstring del modulo: *"El evento
    se llama `tests_ejecutados`; si no se ejecutaron, no hay evento."* El fallo
    de infraestructura era el caso particular; esto es el enunciado general. Se
    expresa por `total == 0` y no enumerando los dos motivos por el mismo
    criterio con que `RunResult.failed` se define por negacion: un tercer
    camino a la corrida vacia cae del lado conservador solo, en vez de colarse
    inflando hacia N4.

    Lo que NO corta: una corrida con al menos un caso corrido, aunque el resto
    esten `skipped` o hayan dado `error`. Eso SI es evidencia pedagogica
    legitima y sigue emitiendose (los `error` cuentan como fallo, que es lo que
    lo manda a N3).

    Arreglarlo del otro lado —que el labeler distinga `total == 0`— obligaria a
    bumpear `LABELER_VERSION`, re-etiquetar los historicos y escribir un ADR.
    No vale para un caso que se resuelve no emitiendo.
    """
    if run.outcome is RunOutcome.INFRASTRUCTURE_FAILURE:
        return False
    return run.total > 0


def build_payload(
    run: RunResult,
    *,
    hidden_case_ids: set[str],
    ejecucion_ms: int,
    engine: str,
) -> dict[str, object]:
    """Payload de `tests_ejecutados` para una corrida server-side.

    La visibilidad la sabe el ejercicio, no el resultado: `hidden_case_ids` sale
    de `Ejercicio.hidden_cases`, igual que en `to_client_payload`.

    `tests_hidden` deja de ser 0. El contrato lo declaraba "siempre 0 en
    piloto-1 — los tests hidden NO se ejecutan client-side. Reservado para
    piloto-2 cuando se implemente sandbox-service". Este es ese servicio: por
    primera vez el conteo de ocultos ejecutados es real.

    `execution_engine` es informativo y el classifier NO lo consulta. Agregar un
    campo opcional que el labeler ignora es inerte para la clasificacion y no
    requiere bumpear `LABELER_VERSION` (regla verificada del repo sobre
    `TutorRespondioPayload.tokens_input`).
    """
    corridos = [c for c in run.cases if c.status.value != "skipped"]
    ocultos = sum(1 for c in corridos if c.id in hidden_case_ids)
    return {
        "test_count_total": run.total,
        "test_count_passed": run.passed,
        "test_count_failed": run.failed,
        "tests_publicos": run.total - ocultos,
        "tests_hidden": ocultos,
        "ejecucion_ms": ejecucion_ms,
        "execution_engine": engine,
    }
