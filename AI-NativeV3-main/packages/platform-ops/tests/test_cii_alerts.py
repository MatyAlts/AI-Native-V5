"""Tests de cii_alerts: cuartiles + alertas vs cohorte (función pura)."""

from __future__ import annotations

from platform_ops.cii_alerts import (
    ALERTS_VERSION,
    MIN_STUDENTS_FOR_QUARTILES,
    compute_alerts_payload,
    compute_cohort_quartiles_payload,
    compute_cohort_slopes_stats,
    compute_student_alerts,
    position_in_quartiles,
)

# ---------------------------------------------------------------------------
# Cuartiles de cohorte
# ---------------------------------------------------------------------------


def test_cohort_con_pocos_estudiantes_marca_insufficient_data() -> None:
    """Cohortes con < MIN_STUDENTS_FOR_QUARTILES estudiantes NO publican
    cuartiles (privacidad: con cohortes muy chicas, los cuartiles podrían
    des-anonimizar)."""
    stats = compute_cohort_slopes_stats([0.5, -0.3, 1.0])
    assert stats["insufficient_data"] is True
    assert stats["q1"] is None
    assert stats["median"] is None


def test_cohort_con_5_estudiantes_calcula_cuartiles() -> None:
    """Con N>=5 reporta cuartiles + media + std."""
    stats = compute_cohort_slopes_stats([-1.0, -0.5, 0.0, 0.5, 1.0])
    assert stats["insufficient_data"] is False
    assert stats["n_students_evaluated"] == 5
    assert stats["min"] == -1.0
    assert stats["max"] == 1.0
    assert stats["median"] == 0.0  # mediana de la lista
    assert stats["mean"] == 0.0


def test_cohort_grande_cuartiles_son_correctos() -> None:
    """Con 11 estudiantes equiespaciados de 0 a 1, cuartiles esperados
    aproximadamente Q1=0.25, median=0.5, Q3=0.75."""
    slopes = [i / 10 for i in range(11)]  # [0.0, 0.1, ..., 1.0]
    stats = compute_cohort_slopes_stats(slopes)
    assert stats["median"] == 0.5
    assert 0.2 <= stats["q1"] <= 0.3
    assert 0.7 <= stats["q3"] <= 0.8


def test_cohort_lista_vacia_es_insufficient() -> None:
    stats = compute_cohort_slopes_stats([])
    assert stats["insufficient_data"] is True
    assert stats["n_students_evaluated"] == 0


# ---------------------------------------------------------------------------
# Position in quartiles
# ---------------------------------------------------------------------------


def test_position_in_quartiles_cubre_los_4_buckets() -> None:
    slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(slopes)
    # Q1 contiene los slopes más bajos
    assert position_in_quartiles(-1.0, stats) == "Q1"
    # Q4 contiene los slopes más altos
    assert position_in_quartiles(1.0, stats) == "Q4"


def test_position_in_quartiles_devuelve_none_si_insufficient() -> None:
    stats = compute_cohort_slopes_stats([0.5, -0.3])  # < 5 estudiantes
    assert position_in_quartiles(0.0, stats) is None


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------


def test_estudiante_a_la_par_de_cohorte_no_tiene_alertas() -> None:
    """Estudiante en la mediana → cero alertas."""
    cohort_slopes = [-0.5, 0.0, 0.0, 0.0, 0.5]  # media 0, std bajo
    stats = compute_cohort_slopes_stats(cohort_slopes)
    alerts = compute_student_alerts(0.0, stats)
    assert alerts == []


def test_estudiante_2_sigmas_debajo_dispara_alerta_high() -> None:
    """Audit G7: >2σ debajo es severity high."""
    # Cohorte simétrica con std conocido
    cohort_slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(cohort_slopes)
    # std de [-1,-0.5,0,0.5,1] es ~0.79; 2σ debajo de 0 es ~-1.58
    alerts = compute_student_alerts(-2.0, stats)
    codes = [a["code"] for a in alerts]
    assert "regresion_vs_cohorte" in codes
    regresion = next(a for a in alerts if a["code"] == "regresion_vs_cohorte")
    assert regresion["severity"] == "high"
    assert regresion["z_score"] < -2


def test_estudiante_1_sigma_debajo_dispara_alerta_medium() -> None:
    cohort_slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(cohort_slopes)
    # std ~0.79; 1σ debajo de mean=0 es ~-0.79; un slope de -1 dispara la alerta
    alerts = compute_student_alerts(-1.0, stats)
    regresion = next(a for a in alerts if a["code"] == "regresion_vs_cohorte")
    assert regresion["severity"] == "medium"
    assert -2 < regresion["z_score"] < -1


def test_estudiante_en_q1_dispara_alerta_low_informativa() -> None:
    """Cualquier estudiante en Q1 dispara alerta `bottom_quartile` (low)."""
    cohort_slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(cohort_slopes)
    # Slope de -0.9 está cerca de Q1 (= -0.75 aprox con stats.quantiles exclusive)
    alerts = compute_student_alerts(-0.9, stats)
    assert any(a["code"] == "bottom_quartile" for a in alerts)


def test_slope_muy_negativo_dispara_alerta_independiente_de_cohorte() -> None:
    """slope < -0.3 dispara `slope_negativo_significativo` (independiente de cohorte)."""
    cohort_slopes = [-2.0, -1.5, -1.0, -0.5, 0.0]  # cohorte mala
    stats = compute_cohort_slopes_stats(cohort_slopes)
    # Estudiante con slope -0.4: NO está debajo de cohorte (cohorte peor),
    # pero el slope negativo SÍ es significativo
    alerts = compute_student_alerts(-0.4, stats)
    codes = [a["code"] for a in alerts]
    assert "slope_negativo_significativo" in codes


def test_alertas_con_cohort_insufficient_son_lista_vacia() -> None:
    """Sin cuartiles confiables, no podemos comparar — no alertamos."""
    stats = compute_cohort_slopes_stats([0.0, -0.5])  # solo 2 estudiantes
    alerts = compute_student_alerts(-2.0, stats)
    assert alerts == []


def test_alertas_con_student_slope_none_son_lista_vacia() -> None:
    cohort_slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(cohort_slopes)
    alerts = compute_student_alerts(None, stats)
    assert alerts == []


# ---------------------------------------------------------------------------
# Helpers de alto nivel (payload del endpoint)
# ---------------------------------------------------------------------------


def test_cohort_quartiles_payload_incluye_metadata() -> None:
    payload = compute_cohort_quartiles_payload([-1.0, -0.5, 0.0, 0.5, 1.0])
    assert payload["labeler_version"] == ALERTS_VERSION
    assert payload["min_students_for_quartiles"] == MIN_STUDENTS_FOR_QUARTILES
    assert payload["n_students_evaluated"] == 5


def test_alerts_payload_incluye_quartile_y_severity() -> None:
    cohort_slopes = [-1.0, -0.5, 0.0, 0.5, 1.0]
    stats = compute_cohort_slopes_stats(cohort_slopes)
    payload = compute_alerts_payload(-2.0, stats)
    assert payload["student_slope"] == -2.0
    assert payload["quartile"] == "Q1"
    assert payload["highest_severity"] == "high"
    assert payload["n_alerts"] >= 1
    assert payload["labeler_version"] == ALERTS_VERSION


def test_alerts_payload_sin_alertas_devuelve_highest_severity_none() -> None:
    cohort_slopes = [-0.5, 0.0, 0.0, 0.0, 0.5]  # media 0
    stats = compute_cohort_slopes_stats(cohort_slopes)
    payload = compute_alerts_payload(0.0, stats)
    assert payload["n_alerts"] == 0
    assert payload["highest_severity"] is None
