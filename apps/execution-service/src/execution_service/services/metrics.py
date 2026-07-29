"""Metricas del servicio de ejecucion (tareas 4.5 y 9.1).

Dos cosas hay que poder ver sin entrar a los logs:

1. **Cuanto se esta esperando.** Si la cola crece mas rapido de lo que drena, el
   alumno percibe el sistema colgado antes de que nada falle. Es el sintoma que
   la prueba de carga busca y el que aparece cuando una comision entera ejecuta
   junta.

2. **Cuanto se esta gastando.** Con Judge0 gestionado el costo era una factura;
   con contenedores propios es **capacidad**: CPU y memoria del host. No llega
   un mail a fin de mes — llega un servidor lento que degrada al resto de la
   plataforma. Por eso se mide desde el dia uno y no cuando se note.

REGLA DE CARDINALIDAD (la del package compartido): las labels son una lista
cerrada y de baja cardinalidad. **Nunca** `user_id` ni `ejercicio_id`: harian
explotar el numero de series temporales.
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter(__name__)

# Corridas pedidas, por resultado. `outcome` tiene 3 valores posibles.
executions_total = _meter.create_counter(
    "execution_requests_total",
    description="Ejecuciones solicitadas, por resultado de la corrida",
    unit="1",
)

# Rechazos por cuota. Separado del anterior a proposito: un pico acá significa
# que el limite quedo corto o que alguien esta abusando, y se lee distinto de un
# pico de ejecuciones normales.
quota_rejections_total = _meter.create_counter(
    "execution_quota_rejections_total",
    description="Ejecuciones rechazadas, por motivo (limite alcanzado o contador caido)",
    unit="1",
)

# Cuanto tardo la corrida completa, de pedido a resultado. Es la latencia que el
# alumno percibe, no la del contenedor.
execution_duration = _meter.create_histogram(
    "execution_duration_seconds",
    description="Duracion de una corrida completa, de pedido a resultado",
    unit="s",
)

# Corridas en vuelo. Es el indicador de saturacion: si sube y no baja, la cola
# esta creciendo mas rapido de lo que drena.
executions_in_flight = _meter.create_up_down_counter(
    "execution_in_flight",
    description="Ejecuciones en curso en este momento",
    unit="1",
)


def record_started() -> None:
    executions_in_flight.add(1)


def record_finished(*, outcome: str, duration_seconds: float) -> None:
    executions_in_flight.add(-1)
    executions_total.add(1, {"outcome": outcome})
    execution_duration.record(duration_seconds, {"outcome": outcome})


def record_quota_rejection(*, reason: str) -> None:
    """`reason`: `limit_reached` (el alumno se paso) o `counter_unavailable`
    (el contador no respondio y la cuota fallo cerrada). Se distinguen porque
    el segundo es un problema nuestro y el primero no."""
    quota_rejections_total.add(1, {"reason": reason})
