"""Tests del árbol de decisión N4.

Verifica que las 3 ramas se disparen correctamente según las 3
coherencias y el reference_profile.
"""

from __future__ import annotations

from classifier_service.services.tree import (
    classify,
)


def test_delegacion_pasiva_si_alta_orphan_y_baja_ct() -> None:
    """Muchas acciones sin verbalización + patrón temporal fragmentado."""
    ct = {"ct_summary": 0.2}
    ccd = {"ccd_mean": 0.1, "ccd_orphan_ratio": 0.8}
    cii = {"cii_stability": 0.3, "cii_evolution": 0.4}

    r = classify(ct, ccd, cii)
    assert r.appropriation == "delegacion_pasiva"
    assert "delegación" in r.reason.lower() or "delegacion" in r.reason.lower()


def test_apropiacion_reflexiva_si_buenos_valores_en_las_3() -> None:
    ct = {"ct_summary": 0.8}
    ccd = {"ccd_mean": 0.75, "ccd_orphan_ratio": 0.15}
    cii = {"cii_stability": 0.6, "cii_evolution": 0.7}

    r = classify(ct, ccd, cii)
    assert r.appropriation == "apropiacion_reflexiva"
    assert "sostenido" in r.reason.lower() or "profundización" in r.reason.lower()


def test_apropiacion_superficial_es_default() -> None:
    """Intermedios caen en superficial."""
    ct = {"ct_summary": 0.5}
    ccd = {"ccd_mean": 0.5, "ccd_orphan_ratio": 0.3}
    cii = {"cii_stability": 0.4, "cii_evolution": 0.5}

    r = classify(ct, ccd, cii)
    assert r.appropriation == "apropiacion_superficial"


def test_clasificacion_es_determinista() -> None:
    ct = {"ct_summary": 0.3}
    ccd = {"ccd_mean": 0.2, "ccd_orphan_ratio": 0.7}
    cii = {"cii_stability": 0.3, "cii_evolution": 0.3}

    r1 = classify(ct, ccd, cii)
    r2 = classify(ct, ccd, cii)
    assert r1.appropriation == r2.appropriation
    assert r1.reason == r2.reason
    assert r1.features == r2.features


def test_resultado_incluye_las_5_dimensiones() -> None:
    ct = {"ct_summary": 0.5}
    ccd = {"ccd_mean": 0.5, "ccd_orphan_ratio": 0.5}
    cii = {"cii_stability": 0.5, "cii_evolution": 0.5}

    r = classify(ct, ccd, cii)
    assert r.ct_summary == 0.5
    assert r.ccd_mean == 0.5
    assert r.ccd_orphan_ratio == 0.5
    assert r.cii_stability == 0.5
    assert r.cii_evolution == 0.5
    # Las dimensiones NO se colapsan en un solo score — se preservan las 5.


def test_reference_profile_custom_cambia_umbrales() -> None:
    """Con un profile más estricto, valores intermedios pueden bajar a superficial."""
    strict_profile = {
        "name": "prog2_hard",
        "version": "v1.0.0",
        "thresholds": {
            "ct_low": 0.25,
            "ct_high": 0.80,  # ← más exigente para reflexiva
            "ccd_orphan_high": 0.4,
            "ccd_mean_low": 0.25,
            "cii_stability_low": 0.3,
            "cii_evolution_low": 0.3,
        },
    }

    ct = {"ct_summary": 0.7}  # alto pero < 0.80
    ccd = {"ccd_mean": 0.7, "ccd_orphan_ratio": 0.2}
    cii = {"cii_stability": 0.5, "cii_evolution": 0.5}

    # Con profile default (ct_high=0.65) → reflexiva
    r_default = classify(ct, ccd, cii)
    assert r_default.appropriation == "apropiacion_reflexiva"

    # Con profile estricto (ct_high=0.80) → superficial
    r_strict = classify(ct, ccd, cii, reference_profile=strict_profile)
    assert r_strict.appropriation == "apropiacion_superficial"


def test_features_registra_la_rama_y_el_profile() -> None:
    r = classify(
        {"ct_summary": 0.1},
        {"ccd_mean": 0.1, "ccd_orphan_ratio": 0.9},
        {"cii_stability": 0.1, "cii_evolution": 0.1},
    )
    assert r.features["branch"] == "delegacion_pasiva"
    assert r.features["profile"] == "default"
    assert "profile_version" in r.features


def test_razon_explica_decision_con_valores_concretos() -> None:
    """La razón debe mencionar los valores que gatillaron la clasificación."""
    r = classify(
        {"ct_summary": 0.2},
        {"ccd_mean": 0.1, "ccd_orphan_ratio": 0.8},
        {"cii_stability": 0.1, "cii_evolution": 0.1},
    )
    # Valores deben aparecer en la razón (auditabilidad)
    assert "0.80" in r.reason or "0.8" in r.reason  # orphan_ratio
    assert "0.20" in r.reason or "0.2" in r.reason  # ct_summary
