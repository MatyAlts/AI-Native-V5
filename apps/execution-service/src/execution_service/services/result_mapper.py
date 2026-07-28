"""Traduccion del resultado del sandbox al formato de casos del sistema (D3).

Existe separado del cliente a proposito: el dia que se cambie de sandbox, se
reescribe `judge0_client` y esto queda igual.

**Por que importa que la forma sea identica a la de Pyodide**: la vista de
resultados del editor se reusa sin cambios, y —mas importante— el evento de
trazabilidad tiene la MISMA forma para los dos lenguajes. Un investigador
analizando el corpus de la tesis no deberia necesitar saber que motor ejecuto.

**La distincion que sostiene la integridad del corpus** (D4): un fallo de
infraestructura NO produce casos fallidos. El clasificador usa el conteo de
fallidos para separar dos niveles de apropiacion, asi que registrar una caida
del sandbox como "el alumno fallo todos los tests" degradaria la clasificacion
pedagogica de un episodio real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from execution_service.services.judge0_client import Judge0Result, Judge0Status


class CaseStatus(StrEnum):
    """Mismos valores que produce el runner de Pyodide, mas `skipped`.

    `skipped` ya existe en el frontend desde `java-authoring-experience`: es lo
    que muestra el panel del docente para un caso sin runtime disponible.
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class RunOutcome(StrEnum):
    """Resultado de la CORRIDA, que no es lo mismo que el de los casos.

    `INFRASTRUCTURE_FAILURE` es el estado propio de D4. Sin el, una caida del
    sandbox se colapsa a "todos los casos fallaron".
    """

    COMPLETED = "completed"
    COMPILATION_ERROR = "compilation_error"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


@dataclass(frozen=True)
class CaseResult:
    id: str
    name: str
    type: str
    status: CaseStatus
    input: str
    expected: str | None
    got: str
    error: str | None
    weight: float


@dataclass(frozen=True)
class RunResult:
    outcome: RunOutcome
    cases: list[CaseResult] = field(default_factory=list)
    compile_output: str = ""

    @property
    def total(self) -> int:
        """Solo los casos que efectivamente corrieron."""
        return sum(1 for c in self.cases if c.status is not CaseStatus.SKIPPED)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.status is CaseStatus.PASS)

    @property
    def failed(self) -> int:
        """Casos que corrieron y no pasaron.

        NO incluye `skipped` ni cuenta nada cuando la corrida fallo por
        infraestructura: es el numero que el clasificador consume.
        """
        if self.outcome is RunOutcome.INFRASTRUCTURE_FAILURE:
            return 0
        return sum(1 for c in self.cases if c.status is CaseStatus.FAIL)


_STATUS_MAP: dict[Judge0Status, CaseStatus] = {
    Judge0Status.ACCEPTED: CaseStatus.PASS,
    Judge0Status.WRONG_ANSWER: CaseStatus.FAIL,
    Judge0Status.TIME_LIMIT_EXCEEDED: CaseStatus.ERROR,
    Judge0Status.COMPILATION_ERROR: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_SIGSEGV: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_SIGXFSZ: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_SIGFPE: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_SIGABRT: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_NZEC: CaseStatus.ERROR,
    Judge0Status.RUNTIME_ERROR_OTHER: CaseStatus.ERROR,
}

_ERROR_MESSAGE: dict[Judge0Status, str] = {
    Judge0Status.TIME_LIMIT_EXCEEDED: (
        "La ejecucion supero el tiempo limite y fue interrumpida (posible bucle infinito)."
    ),
    Judge0Status.RUNTIME_ERROR_SIGSEGV: "Violacion de segmento durante la ejecucion.",
    Judge0Status.RUNTIME_ERROR_SIGXFSZ: "El programa intento escribir un archivo demasiado grande.",
    Judge0Status.RUNTIME_ERROR_SIGFPE: "Error aritmetico (por ejemplo, division por cero).",
    Judge0Status.RUNTIME_ERROR_SIGABRT: "El programa aborto durante la ejecucion.",
    Judge0Status.RUNTIME_ERROR_NZEC: "El programa termino con codigo de salida distinto de cero.",
    Judge0Status.RUNTIME_ERROR_OTHER: "Error durante la ejecucion.",
}


def map_case(
    *,
    case_id: str,
    name: str,
    case_type: str,
    stdin: str,
    expected: str | None,
    weight: float,
    result: Judge0Result,
) -> CaseResult:
    """Traduce UN caso ejecutado al formato del sistema."""
    status = _STATUS_MAP.get(result.status, CaseStatus.ERROR)

    error: str | None = None
    if result.status is Judge0Status.COMPILATION_ERROR:
        error = result.compile_output.strip() or "Error de compilacion."
    elif status is CaseStatus.ERROR:
        error = _ERROR_MESSAGE.get(result.status, "Error durante la ejecucion.")
        if result.stderr.strip():
            error = f"{error}\n{result.stderr.strip()}"

    return CaseResult(
        id=case_id,
        name=name,
        type=case_type,
        status=status,
        input=stdin,
        expected=expected,
        got=result.stdout,
        error=error,
        weight=weight,
    )


def infrastructure_failure(reason: str) -> RunResult:
    """La corrida no pudo hacerse. NO produce casos fallidos (D4).

    `cases` queda vacio a proposito: el evento de trazabilidad va a registrar
    cero casos corridos y el outcome, en vez de N casos fallidos que el
    clasificador leeria como desempeño del alumno.
    """
    return RunResult(
        outcome=RunOutcome.INFRASTRUCTURE_FAILURE,
        cases=[],
        compile_output=reason,
    )
