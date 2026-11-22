"""Aceptacion HU-015, tramo 1 (orquestador, antes de construir; el constructor
no la modifica). Criterios aprobados por Juani el 22/11/2026 ("sisi apruebo").

Hallazgo F11 de HU-014 en produccion: la correccion con IA de un ejercicio de
Python le mandaba al motor cada caso como `paso: false, salida_obtenida: ""`
con `compila: true` y `total: 0`. El sandbox no ejecuta Python, marca los casos
`skipped`, y `_mapear` traduce `status != "pass"` a "no paso". La IA leia "fallo
todo" y le bajaba puntos a codigo correcto (44 de 45 correcciones del semestre).

Contrato que fija esta prueba:
  - `ResultadoTests.ejecutado: bool` (default True) y `as_dict()["ejecutado"]`.
  - Un caso `skipped` no entra en `casos` (ni como pasado ni como fallado).

C01  Todos saltados: casos vacios, total 0, ejecutado False, y lo que viaja al
     motor tampoco trae casos.
C03  Java que compila y falla sigue llegando con sus casos reales.
N01  Saltados mezclados con ejecutados: los saltados no cuentan como fallados.
N02  Una falla del sandbox sigue cortando sin nota.

Se usa el productor REAL (`to_client_payload` del execution-service) para no
repetir el modo de falla de `test_forma_real_de_los_casos.py`. El lenguaje sin
runtime es "cobol": el tramo 2 agrega Python, y esta prueba no puede depender
de que Python siga sin runtime.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from evaluation_service.services.correccion_ejecutor import _resultado_tests_para_activeia
from evaluation_service.services.correccion_pre_ejecucion import (
    PreEjecucionError,
    ResultadoTests,
    _mapear,
)
from execution_service.services.academic_client import Ejercicio, TestCase
from execution_service.services.executor import run_cases, to_client_payload
from execution_service.services.result_mapper import (
    CaseResult,
    CaseStatus,
    RunOutcome,
    RunResult,
)


def _tc(i: int, publico: bool = True) -> TestCase:
    return TestCase(
        id=f"t{i}",
        name=f"caso {i}",
        type="stdin_stdout",
        code="3",
        expected="6",
        is_public=publico,
        weight=1.0,
    )


def _ejercicio(language: str, n: int = 2) -> Ejercicio:
    return Ejercicio(
        id=uuid4(),
        language=language,
        inicial_codigo=None,
        test_cases=[_tc(i, publico=(i == 0)) for i in range(n)],
    )


async def _payload_sin_runtime() -> dict:
    ej = _ejercicio("cobol")
    run = await run_cases(source_code="x", ejercicio=ej)
    return to_client_payload(run, ej)


def _caso(i: int, status: CaseStatus, got: str = "") -> CaseResult:
    return CaseResult(
        id=f"t{i}",
        name=f"caso {i}",
        type="stdin_stdout",
        status=status,
        input="3",
        expected="6",
        got=got,
        error=None,
        weight=1.0,
    )


# ── C01 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_c01_todos_saltados_no_viajan_como_fallados() -> None:
    r = _mapear(await _payload_sin_runtime())
    assert r.casos == []
    assert r.total == 0
    assert getattr(r, "ejecutado", None) is False
    assert r.compila is True


@pytest.mark.asyncio
async def test_c01_el_snapshot_guarda_ejecutado_false() -> None:
    d = _mapear(await _payload_sin_runtime()).as_dict()
    assert d.get("ejecutado") is False
    assert d["casos"] == []


@pytest.mark.asyncio
async def test_c01_al_motor_no_le_llega_ningun_caso_fallado() -> None:
    enviado = _resultado_tests_para_activeia(_mapear(await _payload_sin_runtime()).as_dict())
    assert enviado["casos"] == []
    assert enviado["total"] == 0
    assert not any(c.get("paso") is False for c in enviado["casos"])


def test_c01_un_resultado_normal_es_ejecutado_por_defecto() -> None:
    assert getattr(ResultadoTests(compila=True), "ejecutado", None) is True
    assert ResultadoTests(compila=True).as_dict().get("ejecutado") is True


# ── C03 ────────────────────────────────────────────────────────────────


def test_c03_java_que_falla_sigue_llegando_con_sus_casos() -> None:
    ej = _ejercicio("java")
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[_caso(0, CaseStatus.PASS, "6\n"), _caso(1, CaseStatus.FAIL, "7\n")],
    )
    r = _mapear(to_client_payload(run, ej))
    assert getattr(r, "ejecutado", None) is True
    assert (r.total, r.passed, r.failed) == (2, 1, 1)
    assert [c["paso"] for c in r.casos] == [True, False]
    assert r.casos[0]["salida_obtenida"] == "6\n"


# ── N01 ────────────────────────────────────────────────────────────────


def test_n01_saltados_mezclados_no_cuentan_como_fallados() -> None:
    ej = _ejercicio("java", n=3)
    run = RunResult(
        outcome=RunOutcome.COMPLETED,
        cases=[
            _caso(0, CaseStatus.PASS, "6\n"),
            _caso(1, CaseStatus.SKIPPED),
            _caso(2, CaseStatus.FAIL, "7\n"),
        ],
    )
    r = _mapear(to_client_payload(run, ej))
    assert getattr(r, "ejecutado", None) is True
    assert len(r.casos) == 2
    assert [c["paso"] for c in r.casos] == [True, False]
    assert r.failed == 1


# ── N02 ────────────────────────────────────────────────────────────────


def test_n02_una_falla_del_sandbox_sigue_cortando() -> None:
    with pytest.raises(PreEjecucionError) as exc:
        _mapear({"outcome": "infrastructure_failure", "cases": [], "total": 0})
    assert exc.value.error_code == "SANDBOX_ERROR"
