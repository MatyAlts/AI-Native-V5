"""El guard anti-inflacion N4, verificado DONDE se aplica: la ruta.

`test_ctr_emitter.py` y `test_error_no_infla_n4.py` prueban `should_emit()`
llamandolo directo. Eso verifica la funcion, no el cableado. Si alguien saca
`and should_emit(run)` del `if` de `_run_and_store`, los dos archivos siguen en
verde y el evento se emite igual: la propiedad que protege el corpus vive en la
ruta, no en el predicado.

Verificado con un mutante: sacar `and should_emit(run)` de
`routes/executions.py` no mataba NINGUN test del servicio (117 en verde).
Estos tests son los que lo matan.

Lo que se afirma es siempre lo mismo, del lado de la ruta:

  - corrida SIN un solo caso ejecutado  -> NO se llama a `emit_tests_ejecutados`
  - corrida CON al menos un caso        -> SI se llama, con los conteos reales
  - en los dos casos                    -> el alumno ve el resultado igual

Esa ultima linea no es decoracion. La forma barata de pasar los dos primeros
tests es cortar antes, y ahi el alumno se queda sin resultado en pantalla por
un ejercicio mal autorado. El guard tiene que sacar el EVENTO, no la corrida.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from execution_service.auth import User
from execution_service.routes import executions as ruta
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
    infrastructure_failure,
    map_case,
)
from execution_service.services.sandbox_types import SandboxResult, SandboxStatus

EPISODIO = UUID("e9150d10-0000-0000-0000-000000000001")


def _usuario() -> User:
    return User(
        id=uuid4(),
        tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="alumno@utn.edu.ar",
        roles=frozenset({"estudiante"}),
    )


def _test_case(case_id: str, *, publico: bool = True) -> TestCase:
    return TestCase(
        id=case_id,
        name=f"caso {case_id}",
        type="stdin_stdout",
        code="",
        expected="ok",
        is_public=publico,
        weight=1.0,
    )


def _ejercicio(*, language: str = "java", casos: list[TestCase] | None = None) -> Ejercicio:
    return Ejercicio(
        id=uuid4(),
        language=language,
        inicial_codigo="public class Main {}",
        test_cases=[] if casos is None else casos,
    )


def _caso_corrido(case_id: str, status: SandboxStatus) -> CaseResult:
    return map_case(
        case_id=case_id,
        name=f"caso {case_id}",
        case_type="stdin_stdout",
        stdin="",
        expected="ok",
        weight=1.0,
        result=SandboxResult(
            status=status,
            stdout="ok" if status is SandboxStatus.ACCEPTED else "mal",
            stderr="",
            compile_output="",
            time_seconds=0.2,
            memory_kb=1000,
        ),
    )


def _caso_saltado(case_id: str) -> CaseResult:
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


class _Espia:
    """Registra lo que la ruta emitio y lo que guardo para el alumno."""

    def __init__(self) -> None:
        self.emitidos: list[dict[str, Any]] = []
        self.guardado: dict[str, Any] | None = None


@pytest.fixture
def espia(monkeypatch: pytest.MonkeyPatch) -> _Espia:
    """Aisla la ruta de Redis, del academic-service y del tutor-service.

    Lo unico que NO se reemplaza es el guard: `should_emit` y `build_payload`
    corren de verdad, que es el punto del archivo.
    """
    s = _Espia()

    class _Tutor:
        async def emit_tests_ejecutados(self, **kwargs: Any) -> bool:
            s.emitidos.append(kwargs)
            return True

    async def _put(execution_id: UUID, **kwargs: Any) -> None:
        if kwargs.get("result") is not None:
            s.guardado = kwargs["result"]

    monkeypatch.setattr(ruta, "TutorClient", _Tutor)
    monkeypatch.setattr(ruta.execution_store, "put", _put)
    return s


def _academic(ejercicio: Ejercicio):
    class _Client:
        async def get_ejercicio(self, ejercicio_id: UUID, tenant_id: UUID) -> Ejercicio:
            return ejercicio

    return _Client


async def _correr(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ejercicio: Ejercicio,
    run: RunResult | None = None,
    episode_id: UUID | None = EPISODIO,
) -> None:
    """Ejecuta `_run_and_store` con el ejercicio dado.

    Con `run=None` corre el `run_cases` REAL: para un ejercicio sin casos o de
    un lenguaje sin runtime no toca el sandbox, y es justo el camino que
    produce la corrida vacia en produccion.
    """
    monkeypatch.setattr(ruta, "AcademicClient", _academic(ejercicio))
    if run is not None:

        async def _run_cases(*, source_code: str, ejercicio: Ejercicio) -> RunResult:
            return run

        monkeypatch.setattr(ruta, "run_cases", _run_cases)

    req = ruta.ExecutionRequest(
        ejercicio_id=ejercicio.id,
        source_code="public class Main {}",
        episode_id=episode_id,
    )
    await ruta._run_and_store(uuid4(), req=req, user=_usuario())


# ── Las dos formas de que no corra nada, desde la ruta ──────────────────────


async def test_un_ejercicio_sin_casos_no_emite_evento(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """`test_cases = []` — el ejercicio mal autorado, sin nada roto.

    `run_cases` devuelve `cases=[]` con outcome COMPLETED, el payload sale
    `failed=0` y el labeler v1.2.0 lo lee como "paso todo" -> N4.
    """
    await _correr(monkeypatch, ejercicio=_ejercicio(casos=[]))

    # Precondicion, y no adorno: `_run_and_store` traga TODA excepcion y la
    # guarda como fallo de infraestructura, que tampoco emite. Sin esto un
    # error del andamiaje (un fake mal cableado) dejaria el test verde sin
    # haber pasado nunca por el guard.
    assert espia.guardado is not None and espia.guardado["outcome"] == "completed", (
        "la corrida no llego a completarse: el test no esta midiendo el guard"
    )
    assert espia.emitidos == [], (
        "se emitio `tests_ejecutados` por una corrida donde no se ejecuto un "
        "solo caso: el labeler lee failed==0 como 'paso todo' y etiqueta N4"
    )


async def test_un_lenguaje_sin_runtime_no_emite_evento(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """Todos los casos `skipped`, que `RunResult.total` excluye por definicion."""
    ejercicio = _ejercicio(language="python", casos=[_test_case("t1"), _test_case("t2")])
    await _correr(monkeypatch, ejercicio=ejercicio)

    assert espia.guardado is not None and espia.guardado["outcome"] == "completed", (
        "la corrida no llego a completarse: el test no esta midiendo el guard"
    )
    assert espia.emitidos == []


async def test_el_fallo_de_infraestructura_no_emite_desde_la_ruta(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """La propiedad original de D4, verificada en el cableado y no en el predicado."""
    await _correr(
        monkeypatch,
        ejercicio=_ejercicio(casos=[_test_case("t1")]),
        run=infrastructure_failure("sandbox no alcanzable"),
    )

    assert espia.guardado is not None and espia.guardado["outcome"] == "infrastructure_failure"
    assert espia.emitidos == []


# ── El alumno ve el resultado igual ────────────────────────────────────────


async def test_no_emitir_no_le_saca_el_resultado_al_alumno(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """El guard saca el EVENTO, no la corrida.

    Cortar antes —no ejecutar, o no guardar— pasaria los tests de arriba y
    dejaria al alumno mirando una pantalla vacia por un ejercicio que alguien
    autoro sin casos.
    """
    ejercicio = _ejercicio(language="python", casos=[_test_case("t1"), _test_case("t2")])
    await _correr(monkeypatch, ejercicio=ejercicio)

    assert espia.guardado is not None, "no se guardo resultado para el alumno"
    assert espia.guardado["outcome"] == "completed"
    assert len(espia.guardado["cases"]) == 2, "el alumno tiene que ver los casos saltados"


# ── El control: una corrida real SI emite, con los conteos reales ──────────


async def test_una_corrida_con_al_menos_un_caso_si_emite(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """Sin esto, "no emitir nunca" pasaria todos los tests de arriba.

    El borde exacto del guard: un caso corrido y otro saltado. Se corta por
    "no corrio nada", NO por "hay skipped" — un `total > 0` cambiado a
    "ningun caso skipped" tiraria evidencia pedagogica legitima.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso_corrido("t1", SandboxStatus.ACCEPTED), _caso_saltado("t2")],
    )
    await _correr(monkeypatch, ejercicio=_ejercicio(casos=[_test_case("t1")]), run=run)

    assert len(espia.emitidos) == 1, "una corrida con casos reales dejo de emitirse"
    payload = espia.emitidos[0]["payload"]
    assert payload["test_count_total"] == 1
    assert payload["test_count_passed"] == 1
    assert payload["test_count_failed"] == 0
    assert espia.emitidos[0]["episode_id"] == EPISODIO


async def test_un_unico_caso_en_error_con_el_resto_saltado_emite_y_cuenta_como_fallo(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """El borde peligroso: la corrida MINIMA que todavia es evidencia real.

    Un solo caso que corrio y reviento, mas dos saltados. `total == 1`, asi
    que emite; y ese caso en ERROR tiene que contar como fallo, o el payload
    sale `failed=0` y vuelve la inflacion a N4 por el otro lado.
    """
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _caso_corrido("t1", SandboxStatus.COMPILATION_ERROR),
            _caso_saltado("t2"),
            _caso_saltado("t3"),
        ],
    )
    await _correr(monkeypatch, ejercicio=_ejercicio(casos=[_test_case("t1")]), run=run)

    assert len(espia.emitidos) == 1
    payload = espia.emitidos[0]["payload"]
    assert payload["test_count_total"] == 1
    assert payload["test_count_passed"] == 0
    assert payload["test_count_failed"] == 1, (
        "el unico caso que corrio dio ERROR y no cuenta como fallo: el payload "
        "sale failed=0 y el labeler lo lee como 'paso todo'"
    )


async def test_una_corrida_sin_episodio_no_emite(
    monkeypatch: pytest.MonkeyPatch, espia: _Espia
) -> None:
    """El panel del docente corre FUERA de un episodio: no es actividad de nadie."""
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso_corrido("t1", SandboxStatus.ACCEPTED)],
    )
    await _correr(
        monkeypatch,
        ejercicio=_ejercicio(casos=[_test_case("t1")]),
        run=run,
        episode_id=None,
    )

    assert espia.guardado is not None and espia.guardado["outcome"] == "completed"
    assert espia.emitidos == []
