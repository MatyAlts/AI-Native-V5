"""Los bordes del emisor que ningun test tocaba, encontrados por mutacion.

Tres mutantes sobrevivian a la suite entera (117 tests en verde con el defecto
inyectado). Los tres estan aca:

  1. `should_emit`: borrar la rama `INFRASTRUCTURE_FAILURE -> False`.
  2. `RunResult.failed`: borrar la rama `INFRASTRUCTURE_FAILURE -> 0`.
  3. `build_payload`: contar los ocultos sobre TODOS los casos en vez de solo
     los corridos.

Los dos primeros sobreviven por el mismo motivo, y no es que los guards esten
mal: `infrastructure_failure()` devuelve `cases=[]`, asi que `total` ya da 0 y
`failed` tambien: las dos ramas explicitas de D4 quedan **subsumidas** por el
guard general de la corrida vacia y por el `sum` sobre una lista vacia. Hoy son
defensa en profundidad, y por eso ningun test que use `infrastructure_failure()`
—los tres que hay— puede distinguir si estan puestas o no.

Lo que las vuelve load-bearing es un cambio realista: `run_cases` descarta la
corrida parcial *a proposito* ("media corrida no es un resultado"), pero es una
decision, no una ley. El dia que alguien decida conservar los casos que si
llegaron a correr antes de que el sandbox se cayera, `cases` deja de estar
vacia y las dos ramas pasan a ser lo unico que separa una caida del servidor de
"el alumno paso todo". Estos tests construyen ese `RunResult` a mano para
fijarlo ahora, mientras es barato.

El tercero es independiente y es un conteo: `tests_hidden` tiene que contar
ocultos **ejecutados**, no ocultos declarados.
"""

from __future__ import annotations

from execution_service.services.ctr_emitter import build_payload, should_emit
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
    map_case,
)
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus


def _corrido(case_id: str, status: SandboxStatus) -> CaseResult:
    return map_case(
        case_id=case_id,
        name=f"caso {case_id}",
        case_type="stdin_stdout",
        stdin="",
        expected="ok",
        weight=1.0,
        result=SandboxResult(
            status=status,
            stdout="ok",
            stderr="",
            compile_output="",
            time_seconds=0.2,
            memory_kb=1000,
        ),
    )


def _saltado(case_id: str) -> CaseResult:
    return CaseResult(
        id=case_id,
        name=f"caso {case_id}",
        type="stdin_stdout",
        status=CaseStatus.SKIPPED,
        input="",
        expected=None,
        got="",
        error="No hay entorno de ejecucion para este lenguaje.",
        weight=1.0,
    )


def _caida_parcial(*statuses: SandboxStatus) -> RunResult:
    """El `RunResult` que hoy nadie construye: infra caida CON casos.

    No sale de `infrastructure_failure()` —que devuelve `cases=[]`— sino de la
    variante que conserva lo parcial. Se arma a mano justamente porque es el
    unico input que distingue las ramas de D4 de sus subsumidoras.

    Los status van por parametro porque las dos ramas de D4 se ven con corridas
    parciales DISTINTAS: la de `should_emit` con todo en verde (la direccion
    que infla), la de `failed` con algo en rojo (la que degrada).
    """
    return RunResult(
        outcome=RunOutcome.INFRASTRUCTURE_FAILURE,
        cases=[_corrido(f"t{i}", s) for i, s in enumerate(statuses)],
        compile_output="el sandbox se cayo antes de terminar",
    )


# ── D4, con la corrida parcial que hace load-bearing a los dos guards ───────


def test_una_caida_con_casos_parciales_tampoco_emite() -> None:
    """Es el peor input posible: infra caida y todos los casos que corrieron, en verde.

    Sin la rama `INFRASTRUCTURE_FAILURE -> False` de `should_emit`, esto emite
    con `passed=2, failed=0` y el labeler v1.2.0 —con el tutor a >=60s— lo lee
    como apropiacion reflexiva. El episodio entra al corpus de la tesis en el
    nivel mas alto del modelo porque el servidor se rompio a mitad de camino.

    Ningun test podia ver esta rama mientras `infrastructure_failure()` fuera
    la unica fabrica de `RunResult` caidos: con `cases=[]` el guard general de
    la corrida vacia contesta lo mismo.
    """
    assert should_emit(_caida_parcial(SandboxStatus.ACCEPTED, SandboxStatus.ACCEPTED)) is False


def test_una_caida_con_casos_parciales_reporta_cero_fallidos() -> None:
    """La otra mitad de D4: la caida NO se registra como "fallo todo".

    Es la direccion opuesta a la del test de arriba y por eso las dos ramas
    existen: `should_emit` evita inflar hacia N4, y este `failed = 0` evita
    degradar hacia N3 si alguna vez el payload llegara a construirse igual
    (por ejemplo desde un consumidor que no pase por `should_emit`).

    La corrida parcial de este test tiene un caso EN ROJO a proposito: con
    todo en verde, `failed` da 0 por el `sum` y no por la rama de D4, y el
    test no distinguiria si la rama esta puesta.
    """
    caida = _caida_parcial(SandboxStatus.ACCEPTED, SandboxStatus.WRONG_ANSWER)

    assert caida.failed == 0, (
        "un caso que fallo ANTES de que se cayera el sandbox se esta contando "
        "como desempeno del alumno: D4 dice que una caida no produce fallidos"
    )


# ── El conteo de ocultos: ejecutados, no declarados ─────────────────────────


def test_un_caso_oculto_saltado_no_cuenta_como_oculto_ejecutado() -> None:
    """`tests_hidden` cuenta los ocultos que CORRIERON.

    El contrato del campo es "por primera vez el conteo de ocultos ejecutados
    es real". Contarlos sobre `run.cases` en vez de sobre los corridos infla
    `tests_hidden` con casos que nunca se ejecutaron y, como
    `tests_publicos = total - ocultos`, le roba la cuenta a los publicos: aca
    daria `publicos=0, hidden=1` para una corrida donde lo unico que se
    ejecuto fue un caso publico.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_corrido("publico", SandboxStatus.ACCEPTED), _saltado("oculto-sin-correr")],
    )

    payload = build_payload(
        run,
        hidden_case_ids={"oculto-sin-correr"},
        ejecucion_ms=900,
        engine="docker-java",
    )

    assert payload["test_count_total"] == 1
    assert payload["tests_hidden"] == 0, "se conto como oculto ejecutado un caso saltado"
    assert payload["tests_publicos"] == 1


def test_los_conteos_de_visibilidad_suman_el_total() -> None:
    """`publicos + hidden == total`, siempre.

    `tests_publicos` se calcula por resta (`total - ocultos`), asi que un
    `ocultos` mal contado no rompe la suma: la desbalancea hacia el lado
    equivocado o —con mas ocultos saltados que casos corridos— la manda a
    negativo sin que nada avise.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _corrido("publico", SandboxStatus.ACCEPTED),
            _corrido("oculto-corrido", SandboxStatus.WRONG_ANSWER),
            _saltado("oculto-saltado"),
        ],
    )

    payload = build_payload(
        run,
        hidden_case_ids={"oculto-corrido", "oculto-saltado"},
        ejecucion_ms=900,
        engine="docker-java",
    )

    assert payload["tests_hidden"] == 1
    assert payload["tests_publicos"] == 1
    assert payload["tests_publicos"] + payload["tests_hidden"] == payload["test_count_total"]
    assert payload["tests_publicos"] >= 0
