"""Tests unit para los 3 instrumentos del diseño cuasi-experimental.

Cubren:
- Validacion de schemas Pydantic (Create/Out) — type safety contractual.
- Validacion de contenido (instrumentos_content) — items obligatorios,
  rangos Likert, opciones validas.
- Calculo de scores del pretest — total + sub-escalas.
- Catalogo del test de transferencia — no filtrar soluciones canonicas.

NO cubren:
- Endpoints REST (necesita app + DB) — eso es integration test.
- RLS policies — eso es test_rls.py (test contra Postgres real).

ADR de respaldo: ADR-053 (marcos interpretativos + 7 principios).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from academic_service.schemas.instrumentos import (
    CuestionarioIACreate,
    PretestAutoeficaciaCreate,
    TestTransferenciaCreate,
)
from academic_service.services.instrumentos_content import (
    CUESTIONARIO_IA_ITEMS,
    PRETEST_AUTOEFICACIA_ITEMS,
    TEST_TRANSFERENCIA_PROBLEMS,
    compute_pretest_autoeficacia_scores,
    evaluate_test_transferencia_answer,
    get_test_by_id,
    validate_cuestionario_ia_responses,
    validate_pretest_autoeficacia_responses,
)


# ============================================================================
# CUESTIONARIO IA (P2-2)
# ============================================================================


class TestCuestionarioIASchema:
    def test_create_minimal_valido(self) -> None:
        c = CuestionarioIACreate(
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            responses={"uso_general_meses": "1-6 meses"},
        )
        assert c.instrument_version == "cuestionario-ia-v0.1.0-draft"
        assert "uso_general_meses" in c.responses

    def test_create_acepta_version_custom(self) -> None:
        c = CuestionarioIACreate(
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            instrument_version="cuestionario-ia-v0.2.0-rev-garis",
            responses={"uso_general_meses": "Nunca"},
        )
        assert c.instrument_version == "cuestionario-ia-v0.2.0-rev-garis"


class TestCuestionarioIAValidacion:
    def _valid_responses(self) -> dict:
        """Helper: respuestas que satisfacen TODOS los items required."""
        return {
            "uso_general_meses": "1-6 meses",
            "frecuencia_uso": "Semanal",
            "tipos_tarea": ["Generar codigo desde cero", "Depurar errores"],
            "autopercepcion_dependencia": 3,
            "episodios_delegacion_previos": "A veces",
            "verificacion_critica": 4,
        }

    def test_responses_completas_pasan(self) -> None:
        errors = validate_cuestionario_ia_responses(self._valid_responses())
        assert errors == []

    def test_falta_item_obligatorio(self) -> None:
        resp = self._valid_responses()
        del resp["uso_general_meses"]
        errors = validate_cuestionario_ia_responses(resp)
        assert any("uso_general_meses" in e for e in errors)

    def test_likert_fuera_de_rango_falla(self) -> None:
        resp = self._valid_responses()
        resp["autopercepcion_dependencia"] = 99
        errors = validate_cuestionario_ia_responses(resp)
        assert any("autopercepcion_dependencia" in e for e in errors)

    def test_single_choice_valor_invalido_falla(self) -> None:
        resp = self._valid_responses()
        resp["frecuencia_uso"] = "Vez al ano"  # no esta en options
        errors = validate_cuestionario_ia_responses(resp)
        assert any("frecuencia_uso" in e for e in errors)

    def test_multiple_choice_no_lista_falla(self) -> None:
        resp = self._valid_responses()
        resp["tipos_tarea"] = "Generar codigo desde cero"  # string en vez de lista
        errors = validate_cuestionario_ia_responses(resp)
        assert any("tipos_tarea" in e for e in errors)

    def test_item_desconocido_falla(self) -> None:
        resp = self._valid_responses()
        resp["item_inventado"] = "X"
        errors = validate_cuestionario_ia_responses(resp)
        assert any("item_inventado" in e for e in errors)

    def test_catalogo_tiene_marcadores_placeholder(self) -> None:
        """Sanity check: items son placeholders para validacion coautoral."""
        for item in CUESTIONARIO_IA_ITEMS:
            assert "PLACEHOLDER GARIS" in item["text"], (
                f"Item {item['id']} debe tener marcador PLACEHOLDER para que Garis lo identifique"
            )


# ============================================================================
# PRETEST AUTOEFICACIA (P2-1)
# ============================================================================


class TestPretestAutoeficaciaSchema:
    def test_create_default_version_lishinski(self) -> None:
        p = PretestAutoeficaciaCreate(
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            responses={"ind_01": 5},
        )
        assert "lishinski-2016" in p.instrument_version


class TestPretestAutoeficaciaValidacion:
    def _valid_responses(self) -> dict:
        """Respuestas validas para los 12 items required del esqueleto."""
        return {item["id"]: 5 for item in PRETEST_AUTOEFICACIA_ITEMS}

    def test_responses_completas_pasan(self) -> None:
        errors = validate_pretest_autoeficacia_responses(self._valid_responses())
        assert errors == []

    def test_likert_fuera_de_rango_1_7_falla(self) -> None:
        resp = self._valid_responses()
        resp["ind_01"] = 8
        errors = validate_pretest_autoeficacia_responses(resp)
        assert any("ind_01" in e for e in errors)

    def test_falta_item_obligatorio(self) -> None:
        resp = self._valid_responses()
        del resp["per_03"]
        errors = validate_pretest_autoeficacia_responses(resp)
        assert any("per_03" in e for e in errors)


class TestPretestAutoeficaciaScoring:
    def test_score_total_es_suma_de_respuestas(self) -> None:
        responses = {item["id"]: 5 for item in PRETEST_AUTOEFICACIA_ITEMS}
        total, _ = compute_pretest_autoeficacia_scores(responses)
        assert total == 5 * len(PRETEST_AUTOEFICACIA_ITEMS)

    def test_subscale_scores_promedio_por_subescala(self) -> None:
        """Items con valores constantes producen promedio = ese valor."""
        responses = {item["id"]: 7 for item in PRETEST_AUTOEFICACIA_ITEMS}
        _, subscales = compute_pretest_autoeficacia_scores(responses)
        # Las 4 subescalas del draft: independencia, complejidad, aprendizaje, persistencia
        assert "independencia" in subscales
        assert "complejidad" in subscales
        assert "aprendizaje" in subscales
        assert "persistencia" in subscales
        for subscale, score in subscales.items():
            assert score == 7.0, f"subescala {subscale} debe ser 7.0 con todos los items=7"

    def test_subscale_scores_promedio_mixto(self) -> None:
        """Items con valores variables producen promedio aritmetico."""
        # Items de subescala "independencia" con valores 1, 3, 5 -> promedio 3
        responses = {"ind_01": 1, "ind_02": 3, "ind_03": 5}
        _, subscales = compute_pretest_autoeficacia_scores(responses)
        assert subscales["independencia"] == 3.0


# ============================================================================
# TEST DE TRANSFERENCIA (P2-3)
# ============================================================================


class TestTransferenciaSchema:
    def test_group_assignment_experimental_valido(self) -> None:
        t = TestTransferenciaCreate(
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            group_assignment="experimental",
            test_id="transfer-01",
            time_taken_seconds=120,
            response_detail={"code": "def f(): pass"},
        )
        assert t.group_assignment == "experimental"

    def test_group_assignment_comparison_valido(self) -> None:
        t = TestTransferenciaCreate(
            comision_id=uuid4(),
            student_pseudonym=uuid4(),
            group_assignment="comparison",
            test_id="transfer-02",
            time_taken_seconds=200,
            response_detail={"code": "def g(): pass"},
        )
        assert t.group_assignment == "comparison"

    def test_group_assignment_invalido_falla(self) -> None:
        with pytest.raises(ValueError):
            TestTransferenciaCreate(
                comision_id=uuid4(),
                student_pseudonym=uuid4(),
                group_assignment="control",  # no permitido
                test_id="transfer-01",
                time_taken_seconds=120,
                response_detail={},
            )

    def test_time_taken_negativo_falla(self) -> None:
        with pytest.raises(ValueError):
            TestTransferenciaCreate(
                comision_id=uuid4(),
                student_pseudonym=uuid4(),
                group_assignment="experimental",
                test_id="transfer-01",
                time_taken_seconds=-1,
                response_detail={},
            )


class TestTransferenciaCatalogo:
    def test_get_test_by_id_existente(self) -> None:
        t = get_test_by_id("transfer-01")
        assert t is not None
        assert t["test_id"] == "transfer-01"

    def test_get_test_by_id_no_existente(self) -> None:
        assert get_test_by_id("transfer-99") is None

    def test_catalogo_tiene_marcadores_placeholder(self) -> None:
        for problem in TEST_TRANSFERENCIA_PROBLEMS:
            assert "PLACEHOLDER" in problem["title"], (
                f"Problem {problem['test_id']} debe estar marcado como placeholder"
            )

    def test_evaluacion_default_devuelve_false(self) -> None:
        """[PLACEHOLDER CATEDRA UTN] hasta validacion, no inflar metricas."""
        assert evaluate_test_transferencia_answer("transfer-01", {"code": "x"}) is False
