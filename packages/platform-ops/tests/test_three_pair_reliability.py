"""Tests del orquestador de fiabilidad inter-rater de 3 fuentes (paper §VII-A).

Protocolo dual del paper: para CADA protocolo de etiquetado (A: 4 niveles
N1–N4; B: 3 categorías de apropiación) se reportan los 3 pares posibles entre
Clasificador, Anotador 1 y Anotador 2, y un veredicto H3 TRANSPARENTE (sin
pass/fail opaco).

Las fixtures son deterministas y los valores esperados están calculados a mano
(ver docstring de cada test).
"""

from __future__ import annotations

import pytest
from platform_ops.kappa_analysis import (
    KappaResult,
    PairVerdict,
    ThreePairReliability,
    compute_three_pair_reliability,
    format_three_pair_report,
)

# Categorías del Protocolo B (3 categorías de apropiación).
R = "apropiacion_reflexiva"
S = "apropiacion_superficial"
D = "delegacion_pasiva"


def _split(units: list[tuple[str, str, str]]) -> tuple[list[str], list[str], list[str]]:
    """Desarma una lista de triples (clf, a1, a2) en 3 listas alineadas."""
    clf = [u[0] for u in units]
    a1 = [u[1] for u in units]
    a2 = [u[2] for u in units]
    return clf, a1, a2


# ── Edge cases ────────────────────────────────────────────────────────


def test_largos_distintos_falla() -> None:
    with pytest.raises(ValueError, match="mismas unidades"):
        compute_three_pair_reliability([R, S], [R], [R, S])


def test_sin_unidades_falla() -> None:
    with pytest.raises(ValueError, match="al menos 1 unidad"):
        compute_three_pair_reliability([], [], [])


def test_categoria_invalida_falla_con_categories_explicito() -> None:
    """Con un conjunto `categories` explícito, una etiqueta fuera de él falla.

    (Sin `categories`, las etiquetas se INFIEREN de los datos y no hay
    "inválidas" — por eso el set explícito es necesario para gatear esto.)
    """
    with pytest.raises(ValueError, match="Categoría inválida"):
        compute_three_pair_reliability([R], ["foo"], [R], categories=[R, S, D])


# ── Escenario: exactamente 2 de 3 pares alcanzan κ ≥ 0.70 ──────────────


def test_exactamente_dos_de_tres_pares_cumplen_tabla_v() -> None:
    """Construcción donde SOLO los 2 pares con el clasificador alcanzan
    κ ≥ 0.70 y el par anotador–anotador queda por debajo.

    30 unidades:
      - 22 unánimes (8 R, 7 S, 7 D).
      - 4 donde SOLO a1 yerra (clf==a2): (R,S,R)×2, (S,D,S)×2.
      - 4 donde SOLO a2 yerra (clf==a1): (D,D,R)×2, (R,R,S)×2.

    Resultado (verificado a mano y con la implementación):
      clf_a1: κ = 0.80   (≥ 0.70)
      clf_a2: κ = 0.798  (≥ 0.70)
      a1_a2:  κ = 0.6026 (< 0.70)  — a1 y a2 yerran en unidades distintas.
    → pairs_kappa_above_threshold = 2, h3_table_v_met = True ("≥ 2 de 3").
    """
    units = (
        [(R, R, R)] * 8
        + [(S, S, S)] * 7
        + [(D, D, D)] * 7
        + [(R, S, R)] * 2
        + [(S, D, S)] * 2
        + [(D, D, R)] * 2
        + [(R, R, S)] * 2
    )
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)

    assert res.n_units == 30
    assert res.threshold == 0.70

    # Los 3 reportes son KappaResult completos, nombrados.
    assert res.classifier_vs_annotator1.kappa == 0.80
    assert res.classifier_vs_annotator2.kappa == 0.798
    assert res.annotator1_vs_annotator2.kappa == 0.6026

    # (a) Criterio Tabla V transparente: 2/3 pares con κ ≥ 0.70 → cumple "≥2".
    assert res.pairs_kappa_above_threshold == 2
    assert res.h3_table_v_met is True

    # El número crudo está expuesto al lado del booleano (auditable).
    above = sum(1 for r in res.pairs.values() if r.kappa >= 0.70)
    assert above == res.pairs_kappa_above_threshold


def test_acceso_por_nombre_y_categorias_inferidas() -> None:
    """`pairs` da acceso por nombre; las categorías se infieren ordenadas."""
    units = [(R, R, R)] * 5 + [(S, S, S)] * 5 + [(D, D, D)] * 5
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)
    # Inferidas alfabéticamente (determinismo).
    assert res.categories == (R, S, D)
    assert set(res.pairs.keys()) == {
        "classifier_vs_annotator1",
        "classifier_vs_annotator2",
        "annotator1_vs_annotator2",
    }


# ── Escenario: unánime sustancial (3 fuentes idénticas) ────────────────


def test_unanime_sustancial_todos_los_pares_perfectos() -> None:
    """Las 3 fuentes coinciden en TODO → κ = AC1 = Po = 1.0 en los 3 pares.

    Veredicto H3 máximamente sólido: 3/3 pares con κ ≥ 0.70 (Tabla V) y 3/3
    pares con los 3 estadísticos sustanciales (criterio combinado §VII-A).
    """
    units = [(R, R, R)] * 6 + [(S, S, S)] * 6 + [(D, D, D)] * 6
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)

    for r in res.pairs.values():
        assert r.kappa == 1.0
        assert r.ac1 == 1.0
        assert r.observed_agreement == 1.0

    # Tabla V: 3/3 ≥ 0.70.
    assert res.pairs_kappa_above_threshold == 3
    assert res.h3_table_v_met is True
    # Combinado §VII-A: los 3 pares con 3/3 estadísticos.
    assert res.pairs_combined_substantial == 3
    for v in res.pair_verdicts:
        assert v.n_statistics_reaching == 3
        assert v.combined_substantial is True


# ── Escenario: NO cumple H3 (solo 1 par alcanza κ ≥ 0.70) ──────────────


def test_falla_h3_solo_un_par_supera_umbral() -> None:
    """Solo el par clf–a1 alcanza κ ≥ 0.70; los otros dos quedan en κ = 0.60.

    30 unidades:
      - 22 unánimes (8 R, 7 S, 7 D).
      - 8 donde clf == a1 pero a2 yerra: (R,R,S)×3, (S,S,D)×3, (D,D,R)×2.

    Resultado (verificado):
      clf_a1: κ = 1.00  (clf y a1 coinciden SIEMPRE)        → ≥ 0.70 ✓
      clf_a2: κ = 0.60  (Po = 0.7333, AC1 = 0.6002)         → < 0.70 ✗
      a1_a2:  κ = 0.60  (idéntico a clf_a2 por construcción) → < 0.70 ✗
    → pairs_kappa_above_threshold = 1 → h3_table_v_met = False ("< 2 de 3").
    """
    units = (
        [(R, R, R)] * 8
        + [(S, S, S)] * 7
        + [(D, D, D)] * 7
        + [(R, R, S)] * 3
        + [(S, S, D)] * 3
        + [(D, D, R)] * 2
    )
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)

    assert res.classifier_vs_annotator1.kappa == 1.0
    assert res.classifier_vs_annotator2.kappa == 0.60
    assert res.annotator1_vs_annotator2.kappa == 0.60

    # (a) Tabla V: solo 1/3 → NO cumple "≥ 2 de 3".
    assert res.pairs_kappa_above_threshold == 1
    assert res.h3_table_v_met is False

    # (b) §VII-A combinado transparente: el par clf–a1 es sustancial (3/3); los
    # otros dos NO (solo Po llega → 1/3). Los componentes quedan expuestos.
    by_name = {v.pair_name: v for v in res.pair_verdicts}
    assert by_name["classifier_vs_annotator1"].combined_substantial is True
    assert by_name["classifier_vs_annotator1"].n_statistics_reaching == 3

    weak = by_name["classifier_vs_annotator2"]
    assert weak.combined_substantial is False
    assert weak.kappa_reaches is False
    assert weak.ac1_reaches is False
    assert weak.po_reaches is True  # Po = 0.7333 ≥ 0.70 — único que llega.
    assert weak.n_statistics_reaching == 1


# ── Cada par carga AC1 + IC95% (no se pierden al orquestar) ────────────


def test_cada_par_carga_ac1_y_ci() -> None:
    """Cada uno de los 3 reportes pareados es un KappaResult completo: lleva
    AC1, su interpretación, la SE y el IC 95% — no solo κ."""
    units = (
        [(R, R, R)] * 8
        + [(S, S, S)] * 7
        + [(D, D, D)] * 7
        + [(R, S, R)] * 2
        + [(S, D, S)] * 2
        + [(D, D, R)] * 2
        + [(R, R, S)] * 2
    )
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)

    for r in res.pairs.values():
        assert isinstance(r, KappaResult)
        # AC1 presente y consistente con su interpretación.
        assert 0.0 <= r.ac1 <= 1.0
        assert r.ac1_interpretation in (
            "pobre",
            "justo",
            "moderado",
            "sustancial",
            "casi perfecto",
        )
        # IC 95% envuelve a κ y la SE es no-negativa.
        low, high = r.kappa_ci_95
        assert low <= r.kappa <= high
        assert r.kappa_se >= 0.0

    # Caso concreto: clf_a1 (κ=0.80) trae SE > 0 e IC estricto.
    clf_a1 = res.classifier_vs_annotator1
    assert clf_a1.ac1 == 0.8003
    assert clf_a1.kappa_se > 0.0
    assert clf_a1.kappa_ci_95 == (0.6196, 0.9804)


# ── Genericidad sobre el conjunto de categorías (Protocolo A: N1–N4) ───


def test_generico_protocolo_a_cuatro_categorias_n1_n4() -> None:
    """El orquestador es genérico sobre el conjunto de categorías: con las 4
    categorías N1–N4 del Protocolo A funciona idéntico.

    Acuerdo perfecto sobre 4 niveles → κ = 1.0 en los 3 pares y H3 cumplido.
    """
    cats = ["N1", "N2", "N3", "N4"]
    base = ["N1", "N2", "N3", "N4"] * 5  # 20 unidades, las 4 categorías presentes.
    res = compute_three_pair_reliability(base, base, base, categories=cats)

    assert res.categories == ("N1", "N2", "N3", "N4")
    assert res.n_units == 20
    for r in res.pairs.values():
        assert r.kappa == 1.0
        # La matriz de confusión es 4×4 (genérica, no las 3 de apropiación).
        assert set(r.confusion_matrix.keys()) == {"N1", "N2", "N3", "N4"}
    assert res.h3_table_v_met is True


def test_protocolo_a_categorias_inferidas_de_los_datos() -> None:
    """Sin pasar `categories`, el conjunto se infiere de los datos (Protocolo A
    con etiquetas N1–N4 presentes en las fuentes)."""
    clf = ["N1", "N2", "N3", "N4", "N1", "N4"]
    a1 = ["N1", "N2", "N3", "N4", "N2", "N4"]
    a2 = ["N1", "N3", "N3", "N4", "N1", "N4"]
    res = compute_three_pair_reliability(clf, a1, a2)
    assert res.categories == ("N1", "N2", "N3", "N4")


# ── Umbral configurable ────────────────────────────────────────────────


def test_umbral_configurable() -> None:
    """El umbral sustancial es configurable; bajarlo cambia el veredicto.

    Reusa la fixture donde a1_a2 = κ 0.6026. Con umbral 0.60, los 3 pares lo
    superan → h3_table_v_met sigue True pero ahora son 3/3 (no 2/3).
    """
    units = (
        [(R, R, R)] * 8
        + [(S, S, S)] * 7
        + [(D, D, D)] * 7
        + [(R, S, R)] * 2
        + [(S, D, S)] * 2
        + [(D, D, R)] * 2
        + [(R, R, S)] * 2
    )
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2, threshold=0.60)
    assert res.threshold == 0.60
    assert res.pairs_kappa_above_threshold == 3  # 0.80, 0.798, 0.6026 todos ≥ 0.60
    assert res.h3_table_v_met is True


# ── Reporte legible ────────────────────────────────────────────────────


def test_reporte_legible_expone_componentes() -> None:
    units = [(R, R, R)] * 6 + [(S, S, S)] * 6 + [(D, D, D)] * 6
    clf, a1, a2 = _split(units)
    res = compute_three_pair_reliability(clf, a1, a2)
    report = format_three_pair_report(res)
    assert "Veredicto H3" in report
    assert "Tabla V" in report
    assert "classifier_vs_annotator1" in report
    # Los 3 estadísticos aparecen por par (transparencia).
    assert "κ=" in report and "AC1=" in report and "Po=" in report


def test_dataclasses_exportadas() -> None:
    """Los tipos del resultado son importables (API pública)."""
    assert ThreePairReliability is not None
    assert PairVerdict is not None
