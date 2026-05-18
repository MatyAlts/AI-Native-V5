"""Árbol de decisión N4 que produce la clasificación final.

Input: dict con las 3 coherencias (ct_summary, ccd_*, cii_*) + reference_profile.

Reference profile: umbrales específicos del curso/dificultad. Ej:
    {
        "name": "cs1_easy",
        "version": "v1.0.0",
        "thresholds": {
            "ct_low": 0.35, "ct_high": 0.65,
            "ccd_orphan_high": 0.5, "ccd_mean_low": 0.35,
            "cii_stability_low": 0.2, "cii_evolution_low": 0.3,
        },
    }

Clasificaciones posibles (ADR-010):
  - "delegacion_pasiva": patrones de preguntar→copiar sin reflexión.
  - "apropiacion_superficial": intento pero sin profundización.
  - "apropiacion_reflexiva": trabajo sostenido con coherencia en las 3 dims.

Decisión: árbol simple y EXPLICABLE. Nada de black boxes. Cada rama se
documenta con su razón para el `appropriation_reason` del CTR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_REFERENCE_PROFILE: dict[str, Any] = {
    "name": "default",
    "version": "v1.0.0",
    "thresholds": {
        "ct_low": 0.35,
        "ct_high": 0.65,
        "ccd_orphan_high": 0.5,
        "ccd_mean_low": 0.35,
        "cii_stability_low": 0.2,
        "cii_evolution_low": 0.3,
    },
}


@dataclass
class ClassificationResult:
    appropriation: str  # "delegacion_pasiva" | "apropiacion_superficial" | "apropiacion_reflexiva"
    reason: str
    ct_summary: float
    ccd_mean: float
    ccd_orphan_ratio: float
    cii_stability: float
    cii_evolution: float
    features: dict[str, Any]


def classify(
    ct: dict[str, Any],
    ccd: dict[str, Any],
    cii: dict[str, Any],
    reference_profile: dict[str, Any] | None = None,
) -> ClassificationResult:
    """Aplica el árbol N4 con los umbrales del reference_profile."""
    profile = reference_profile or DEFAULT_REFERENCE_PROFILE
    th = profile["thresholds"]

    ct_summary = float(ct.get("ct_summary", 0.5))
    ccd_mean = float(ccd.get("ccd_mean", 0.5))
    ccd_orphan = float(ccd.get("ccd_orphan_ratio", 0.0))
    cii_stab = float(cii.get("cii_stability", 0.5))
    cii_evo = float(cii.get("cii_evolution", 0.5))

    # ── Árbol de decisión ─────────────────────────────────────────────
    #
    # Rama 1: DELEGACIÓN PASIVA
    # Dos condiciones independientes cualquiera de las cuales gatilla:
    #   (a) orphan_ratio extremadamente alto (>0.8): el estudiante actúa
    #       casi siempre sin verbalizar, sin importar el ritmo temporal.
    #       Patrón clásico de "copy-paste del tutor".
    #   (b) orphan_ratio alto (>= th) combinado con coherencia temporal
    #       baja: patrón erratico + sin reflexión.
    EXTREME_ORPHAN_THRESHOLD = 0.8

    is_extreme_delegation = ccd_orphan >= EXTREME_ORPHAN_THRESHOLD
    is_classic_delegation = ccd_orphan >= th["ccd_orphan_high"] and ct_summary < th["ct_low"]
    if is_extreme_delegation or is_classic_delegation:
        trigger = "extrema (sin verbalizaciones)" if is_extreme_delegation else "clásica"
        return ClassificationResult(
            appropriation="delegacion_pasiva",
            reason=(
                f"Delegación {trigger}: "
                f"ccd_orphan_ratio={ccd_orphan:.2f}, "
                f"ct_summary={ct_summary:.2f}. "
                f"Evidencia de trabajo sin verbalización de comprensión."
            ),
            ct_summary=ct_summary,
            ccd_mean=ccd_mean,
            ccd_orphan_ratio=ccd_orphan,
            cii_stability=cii_stab,
            cii_evolution=cii_evo,
            features={
                "branch": "delegacion_pasiva",
                "sub_branch": "extreme" if is_extreme_delegation else "classic",
                "profile": profile["name"],
                "profile_version": profile["version"],
            },
        )

    # Rama 2: APROPIACIÓN REFLEXIVA
    # Condiciones fuertes en las 3 dimensiones.
    if (
        ct_summary >= th["ct_high"]
        and ccd_mean >= 1 - th["ccd_mean_low"]  # alto = bueno
        and ccd_orphan < th["ccd_orphan_high"]
        and cii_stab > th["cii_stability_low"]
    ):
        return ClassificationResult(
            appropriation="apropiacion_reflexiva",
            reason=(
                f"Coherencia temporal alta (ct={ct_summary:.2f}), "
                f"alineación código-discurso (ccd_mean={ccd_mean:.2f}, "
                f"orphans={ccd_orphan:.2f}), "
                f"estabilidad de enfoque (cii_stab={cii_stab:.2f}): "
                f"evidencia de trabajo sostenido con profundización."
            ),
            ct_summary=ct_summary,
            ccd_mean=ccd_mean,
            ccd_orphan_ratio=ccd_orphan,
            cii_stability=cii_stab,
            cii_evolution=cii_evo,
            features={
                "branch": "apropiacion_reflexiva",
                "profile": profile["name"],
                "profile_version": profile["version"],
            },
        )

    # Rama 3 (default): APROPIACIÓN SUPERFICIAL
    # Intenta pero no cumple los umbrales fuertes.
    return ClassificationResult(
        appropriation="apropiacion_superficial",
        reason=(
            f"Coherencias intermedias (ct={ct_summary:.2f}, "
            f"ccd_mean={ccd_mean:.2f}, ccd_orphan={ccd_orphan:.2f}, "
            f"cii_stab={cii_stab:.2f}): engagement presente pero sin "
            f"evidencia suficiente de profundización."
        ),
        ct_summary=ct_summary,
        ccd_mean=ccd_mean,
        ccd_orphan_ratio=ccd_orphan,
        cii_stability=cii_stab,
        cii_evolution=cii_evo,
        features={
            "branch": "apropiacion_superficial",
            "profile": profile["name"],
            "profile_version": profile["version"],
        },
    )
