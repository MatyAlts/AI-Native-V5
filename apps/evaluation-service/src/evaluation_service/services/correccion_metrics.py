"""Métricas de la corrección asistida por Active-IA (tarea 6.2).

Molde: `execution-service/services/metrics.py`. Mismo criterio, distinto
recurso escaso: allá lo que se agota es CPU del host, acá es **cuota y dinero
de un tercero** — cada corrección paga una corrida de Gemini.

Tres cosas hay que poder ver sin entrar a los logs:

1. **Cuántas terminaron sin nota, y por qué.** La invariante del epic es que un
   fallo de infraestructura NUNCA se convierte en nota. Eso está en el código y
   en los tests, pero sin métrica nadie sabe con qué frecuencia pasa. Un pico de
   `infra_failure` es Active-IA caído; uno de `rejected` es una rúbrica mal
   configurada. Se leen distinto y hoy se ven igual.

2. **Cuánto se está esperando.** El poll tiene 150s de presupuesto. Si la
   duración se pega al techo, el docente ve la corrección colgada y vuelve a
   dispararla — que es exactamente lo que hace que se pague dos veces.

3. **Cuántas se rechazaron por cuota.** La cuota falla CERRADA (503 si no se
   puede leer el contador). Un pico acá puede ser el límite corto, o Redis
   caído: sin la etiqueta de motivo no se distingue, y son dos incidentes con
   respuestas opuestas.

REGLA DE CARDINALIDAD (la del package compartido): labels de lista cerrada y
baja cardinalidad. **Nunca** `user_id`, `entrega_id` ni `ejercicio_id` — harían
explotar el número de series temporales.
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter(__name__)

# Correcciones disparadas. Es el numerador del gasto: cada una que arranca ya
# comprometió una corrida del motor.
correcciones_disparadas_total = _meter.create_counter(
    "activeia_correcciones_disparadas_total",
    description="Correcciones que arrancaron, por si son primer intento o reintento",
    unit="1",
)

# Correcciones terminadas, por desenlace. `outcome` es la etiqueta que separa
# "hay nota" de "no hay nota, y por qué".
correcciones_completadas_total = _meter.create_counter(
    "activeia_correcciones_completadas_total",
    description="Correcciones terminadas, por desenlace (con nota, rechazo, fallo de infra)",
    unit="1",
)

# Fallos de infraestructura desagregados por causa. Separado del anterior a
# propósito: el de arriba responde "cuántas no dieron nota", éste responde "de
# quién es el problema". `GEMINI_OVERLOADED` es del motor; `HTTP_5xx` es de la
# API; `TIMEOUT_POLL` somos nosotros esperando poco.
correcciones_infra_failure_total = _meter.create_counter(
    "activeia_correcciones_infra_failure_total",
    description="Correcciones que murieron por infraestructura, por causa",
    unit="1",
)

# De disparo a desenlace, incluyendo el poll. Es lo que el docente percibe.
correccion_duracion = _meter.create_histogram(
    "activeia_correccion_duration_seconds",
    description="Duracion de una correccion completa, de disparo a desenlace",
    unit="s",
)

# Correcciones en vuelo. Indicador de saturación: si sube y no baja, el
# semáforo de concurrencia está reteniendo más de lo que drena.
correcciones_in_flight = _meter.create_up_down_counter(
    "activeia_correcciones_in_flight",
    description="Correcciones en curso en este momento",
    unit="1",
)

# Rechazos por cuota diaria. Un pico significa que el límite quedó corto, que
# alguien está disparando de más, o que el contador no se pudo leer (la cuota
# falla cerrada). El motivo lo distingue.
cuota_rechazos_total = _meter.create_counter(
    "activeia_cuota_rechazos_total",
    description="Disparos rechazados por cuota, por motivo",
    unit="1",
)


def record_disparada(*, es_reintento: bool) -> None:
    correcciones_in_flight.add(1)
    correcciones_disparadas_total.add(1, {"tipo": "reintento" if es_reintento else "primero"})


def record_completada(*, outcome: str, duration_seconds: float) -> None:
    """`outcome`: `con_nota`, `rechazada`, `infra_failure`.

    Se llama SIEMPRE que una corrección deja de estar en vuelo, incluidos los
    caminos de error — si sólo se llamara en el camino feliz, `in_flight`
    subiría para siempre y el indicador de saturación mentiría justo cuando
    más se lo necesita.
    """
    correcciones_in_flight.add(-1)
    correcciones_completadas_total.add(1, {"outcome": outcome})
    correccion_duracion.record(duration_seconds, {"outcome": outcome})


def record_infra_failure(*, causa: str) -> None:
    """`causa`: el `error_code` ya normalizado (`GEMINI_OVERLOADED`,
    `HTTP_502`, `TIMEOUT_POLL`, `CONFLICTO_SIN_SALIDA`, …).

    Es de lista acotada porque los `error_code` los emite nuestro código, no
    el texto libre de la API de terceros.
    """
    correcciones_infra_failure_total.add(1, {"causa": causa})


def record_cuota_rechazo(*, motivo: str) -> None:
    """`motivo`: `limite_alcanzado` o `contador_caido`."""
    cuota_rechazos_total.add(1, {"motivo": motivo})
