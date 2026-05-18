"""Tests del análisis inter-rater Kappa."""

from __future__ import annotations

import pytest
from platform_ops.kappa_analysis import (
    KappaRating,
    compute_cohen_kappa,
    format_report,
)


def _make(ratings: list[tuple[str, str]]) -> list[KappaRating]:
    return [
        KappaRating(episode_id=f"ep_{i}", rater_a=a, rater_b=b) for i, (a, b) in enumerate(ratings)
    ]


# ── Edge cases ────────────────────────────────────────────────────────


def test_sin_ratings_falla() -> None:
    with pytest.raises(ValueError, match="al menos"):
        compute_cohen_kappa([])


def test_categoria_invalida_falla() -> None:
    with pytest.raises(ValueError, match="Categoría inválida"):
        compute_cohen_kappa(
            [
                KappaRating(episode_id="x", rater_a="foo", rater_b="apropiacion_reflexiva"),
            ]
        )


# ── Casos clásicos ────────────────────────────────────────────────────


def test_acuerdo_perfecto_kappa_1() -> None:
    """Si ambos raters coinciden en TODO, kappa = 1.0."""
    ratings = _make(
        [
            ("apropiacion_reflexiva", "apropiacion_reflexiva"),
            ("apropiacion_superficial", "apropiacion_superficial"),
            ("delegacion_pasiva", "delegacion_pasiva"),
            ("apropiacion_reflexiva", "apropiacion_reflexiva"),
        ]
    )
    result = compute_cohen_kappa(ratings)
    assert result.kappa == 1.0
    assert result.interpretation == "casi perfecto"


def test_desacuerdo_total_kappa_negativo() -> None:
    """Si los raters nunca coinciden, kappa < 0 (peor que azar)."""
    ratings = _make(
        [
            ("apropiacion_reflexiva", "delegacion_pasiva"),
            ("delegacion_pasiva", "apropiacion_reflexiva"),
            ("apropiacion_reflexiva", "delegacion_pasiva"),
            ("delegacion_pasiva", "apropiacion_reflexiva"),
        ]
    )
    result = compute_cohen_kappa(ratings)
    assert result.kappa < 0


def test_acuerdo_azar_kappa_0() -> None:
    """Si ambos raters asignan aleatoriamente con misma distribución uniforme,
    kappa debe ser cercano a 0. Usamos un caso específico perfectamente
    construido para dar κ = 0 exacto."""
    # rater_a: 3 de cada categoría
    # rater_b: también 3 de cada categoría
    # Sin correlación entre raters → p_o = p_e
    ratings = _make(
        [
            # rater_a=reflexiva
            ("apropiacion_reflexiva", "apropiacion_reflexiva"),
            ("apropiacion_reflexiva", "apropiacion_superficial"),
            ("apropiacion_reflexiva", "delegacion_pasiva"),
            # rater_a=superficial
            ("apropiacion_superficial", "apropiacion_reflexiva"),
            ("apropiacion_superficial", "apropiacion_superficial"),
            ("apropiacion_superficial", "delegacion_pasiva"),
            # rater_a=delegacion
            ("delegacion_pasiva", "apropiacion_reflexiva"),
            ("delegacion_pasiva", "apropiacion_superficial"),
            ("delegacion_pasiva", "delegacion_pasiva"),
        ]
    )
    result = compute_cohen_kappa(ratings)
    # p_o = 3/9 = 0.333, p_e = (3/9)^2 * 3 = 0.333 → kappa = 0
    assert abs(result.kappa) < 0.001


# ── Escenarios realistas ──────────────────────────────────────────────


def test_acuerdo_sustancial_clasificador_vs_humano() -> None:
    """Escenario típico del piloto: el clasificador acierta en ~80%."""
    ratings = _make(
        # 8 aciertos + 2 errores (uno en cada dirección)
        [("apropiacion_reflexiva", "apropiacion_reflexiva")] * 4
        + [("apropiacion_superficial", "apropiacion_superficial")] * 3
        + [("delegacion_pasiva", "delegacion_pasiva")] * 1
        + [("apropiacion_reflexiva", "apropiacion_superficial")] * 1  # error
        + [("apropiacion_superficial", "delegacion_pasiva")] * 1  # error
    )
    result = compute_cohen_kappa(ratings)
    assert result.kappa > 0.6
    assert result.interpretation in ("sustancial", "casi perfecto")


def test_per_class_agreement_identifica_clase_problemática() -> None:
    """Cuando el modelo falla sistemáticamente en una clase, per_class_agreement
    lo muestra."""
    # El clasificador acierta siempre en reflexiva y superficial, pero
    # SIEMPRE llama "delegacion" a cosas que son "superficial" y viceversa
    ratings = _make(
        [("apropiacion_reflexiva", "apropiacion_reflexiva")] * 5
        # 4 episodios donde rater_b dice delegacion pero rater_a dice superficial
        + [("apropiacion_superficial", "delegacion_pasiva")] * 4
        # 4 episodios donde rater_b dice superficial pero rater_a dice delegacion
        + [("delegacion_pasiva", "apropiacion_superficial")] * 4
    )
    result = compute_cohen_kappa(ratings)
    # El kappa global es bajo
    assert result.kappa < 0.5
    # Reflexiva tiene acuerdo perfecto (1.0)
    assert result.per_class_agreement["apropiacion_reflexiva"] > 0.9
    # Superficial y delegacion tienen acuerdo pésimo
    assert result.per_class_agreement["apropiacion_superficial"] < 0.3
    assert result.per_class_agreement["delegacion_pasiva"] < 0.3


def test_matriz_de_confusion_precisa() -> None:
    ratings = _make(
        [
            ("apropiacion_reflexiva", "apropiacion_reflexiva"),
            ("apropiacion_reflexiva", "apropiacion_superficial"),
            ("apropiacion_superficial", "apropiacion_reflexiva"),
            ("delegacion_pasiva", "delegacion_pasiva"),
        ]
    )
    result = compute_cohen_kappa(ratings)
    cm = result.confusion_matrix
    assert cm["apropiacion_reflexiva"]["apropiacion_reflexiva"] == 1
    assert cm["apropiacion_reflexiva"]["apropiacion_superficial"] == 1
    assert cm["apropiacion_superficial"]["apropiacion_reflexiva"] == 1
    assert cm["delegacion_pasiva"]["delegacion_pasiva"] == 1


def test_reporte_legible_incluye_interpretacion() -> None:
    ratings = _make(
        [
            ("apropiacion_reflexiva", "apropiacion_reflexiva"),
            ("apropiacion_superficial", "apropiacion_superficial"),
        ]
    )
    result = compute_cohen_kappa(ratings)
    report = format_report(result)
    assert "κ =" in report
    assert "Acuerdo" in report
    assert "Matriz de confusión" in report


# ── Interpretación de Landis & Koch ───────────────────────────────────


def test_interpretacion_por_rango() -> None:
    from platform_ops.kappa_analysis import KappaResult

    test_cases = [
        (0.10, "pobre"),
        (0.30, "justo"),
        (0.50, "moderado"),
        (0.70, "sustancial"),
        (0.90, "casi perfecto"),
    ]
    for kappa, expected in test_cases:
        r = KappaResult(
            kappa=kappa,
            n_episodes=10,
            observed_agreement=0.0,
            expected_agreement=0.0,
        )
        assert r.interpretation == expected, (
            f"kappa={kappa} → esperaba {expected}, got {r.interpretation}"
        )
