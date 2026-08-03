"""Tipos del resultado crudo de una corrida, independientes del motor.

Antes vivian en `judge0_client.py` y se llamaban `Judge0Status` / `Judge0Result`.
El ADR-060 cambio el motor de Judge0 a un contenedor Docker plano, y un tipo que
lleva el nombre del proveedor en un modulo que ya no lo usa es una mentira que
se paga leyendo.

Los valores del enum SON los status ids de Judge0. Se conservan a proposito: son
una taxonomia razonable de "como puede terminar una corrida" y ya estaban
mapeados en `result_mapper`. Si el dia de manana se vuelve a Judge0 (sigue
siendo el plan B del ADR-060), el mapeo es directo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SandboxStatus(IntEnum):
    """Como termino una corrida. Los numeros vienen de la taxonomia de Judge0."""

    IN_QUEUE = 1
    PROCESSING = 2
    ACCEPTED = 3
    WRONG_ANSWER = 4
    TIME_LIMIT_EXCEEDED = 5
    COMPILATION_ERROR = 6
    RUNTIME_ERROR_SIGSEGV = 7
    RUNTIME_ERROR_SIGXFSZ = 8
    RUNTIME_ERROR_SIGFPE = 9
    RUNTIME_ERROR_SIGABRT = 10
    RUNTIME_ERROR_NZEC = 11
    RUNTIME_ERROR_OTHER = 12
    INTERNAL_ERROR = 13
    EXEC_FORMAT_ERROR = 14

    @property
    def is_terminal(self) -> bool:
        return self >= SandboxStatus.ACCEPTED

    @property
    def is_infra_failure(self) -> bool:
        """Fallo NUESTRO, no del alumno.

        Distinguirlo es el punto de D4 del design: sin esto, una caida del
        sandbox se registra como el alumno fallando todos los casos, y el
        clasificador usa ese conteo para separar dos niveles de apropiacion.
        """
        return self in (SandboxStatus.INTERNAL_ERROR, SandboxStatus.EXEC_FORMAT_ERROR)


@dataclass(frozen=True)
class SandboxResult:
    status: SandboxStatus
    stdout: str
    stderr: str
    compile_output: str
    time_seconds: float | None
    memory_kb: int | None


class SandboxUnavailableError(RuntimeError):
    """El sandbox no pudo correr. NO es un fallo del codigo del alumno.

    El caller la traduce a un estado de infraestructura, nunca a casos fallidos.
    """
