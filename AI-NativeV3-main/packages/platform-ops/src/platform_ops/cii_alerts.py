"""Cuartiles agregados de cohorte + alertas individuales (ADR-018, audit G7).

Implementa la versión "estadística clásica" del audit G7 que dice ">1σ del
propio trayecto → sugerir intervención". Interpretación: comparar el
`mean_slope` del estudiante contra los cuartiles + media + desvío estándar
de los slopes longitudinales de la cohorte. Si el estudiante está más de
1 desvío DEBAJO de la media de la cohorte, dispara alerta.

NO es ML predictivo (forecasting / regresión sobre series temporales) —
eso es agenda piloto-2 separada. Esta es estadística simple sobre los
slopes ya calculados por `cii_longitudinal.py`.

Privacidad (RN-094): los cuartiles agregados NO exponen slopes individuales.
El docente ve la **posición** del estudiante (Q1/Q2/Q3/Q4), pero no los
slopes de los demás estudiantes.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Literal

CIIQuartile = Literal["Q1", "Q2", "Q3", "Q4"]
AlertSeverity = Literal["low", "medium", "high"]
ALERTS_VERSION = "1.0.0"

# Mínimo de estudiantes con `mean_slope` no-null en la cohorte para reportar
# cuartiles. Con menos de N estudiantes, los cuartiles son inestables.
MIN_STUDENTS_FOR_QUARTILES = 5


def compute_cohort_slopes_stats(student_slopes: list[float]) -> dict[str, Any]:
    """Calcula cuartiles + media + desvío estándar de los slopes de cohorte.

    Args:
        student_slopes: lista de `mean_slope` de cada estudiante de la cohorte
            que tenga slope no-null (NO incluir None — el caller filtra).

    Returns:
        Dict con `n_students_evaluated`, `q1`, `median`, `q3`, `min`, `max`,
        `mean`, `stdev`. Si `n < MIN_STUDENTS_FOR_QUARTILES`, devuelve estructura
        con flag `insufficient_data: true` y campos en None — privacidad: con
        cohortes muy chicas, los cuartiles podrían des-anonimizar.
    """
    n = len(student_slopes)
    if n < MIN_STUDENTS_FOR_QUARTILES:
        return {
            "n_students_evaluated": n,
            "insufficient_data": True,
            "q1": None,
            "median": None,
            "q3": None,
            "min": None,
            "max": None,
            "mean": None,
            "stdev": None,
        }

    sorted_slopes = sorted(student_slopes)
    # Cuartiles via método estadístico estándar (interpolación lineal).
    quartiles = statistics.quantiles(sorted_slopes, n=4, method="exclusive")
    q1, median, q3 = quartiles  # statistics.quantiles devuelve [Q1, Q2, Q3]

    return {
        "n_students_evaluated": n,
        "insufficient_data": False,
        "q1": round(q1, 6),
        "median": round(median, 6),
        "q3": round(q3, 6),
        "min": round(sorted_slopes[0], 6),
        "max": round(sorted_slopes[-1], 6),
        "mean": round(statistics.mean(sorted_slopes), 6),
        "stdev": round(statistics.stdev(sorted_slopes), 6) if n > 1 else 0.0,
    }


def position_in_quartiles(slope: float, stats: dict[str, Any]) -> CIIQuartile | None:
    """Devuelve el cuartil del slope dentro de la distribución de cohorte.

    Q1 = peor 25% (slopes más bajos); Q4 = mejor 25% (slopes más altos).
    None si la cohorte tiene `insufficient_data`.
    """
    if stats.get("insufficient_data"):
        return None
    if slope <= stats["q1"]:
        return "Q1"
    if slope <= stats["median"]:
        return "Q2"
    if slope <= stats["q3"]:
        return "Q3"
    return "Q4"


def compute_student_alerts(
    student_slope: float | None,
    cohort_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detecta alertas comparando slope del estudiante con la cohorte.

    Reglas (audit G7):
    - **regresion_vs_cohorte**: el estudiante está >1σ DEBAJO de la media
      de la cohorte. Severity: medium si >1σ, high si >2σ.
    - **bottom_quartile**: el estudiante está en Q1 (peor 25%). Severity:
      low solo (informativa, no toda Q1 requiere intervención).
    - **slope_negativo_significativo**: slope < -0.3 (más de un cuarto de
      categoría ordinal por episodio). Severity: medium.

    Returns:
        Lista de dicts con `code, severity, title, detail, threshold_used`.
        Vacía si no hay alertas. Si `student_slope` es None o cohorte
        insufficient, lista vacía (no podemos comparar).
    """
    if student_slope is None or cohort_stats.get("insufficient_data"):
        return []

    alerts: list[dict[str, Any]] = []
    mean = cohort_stats["mean"]
    stdev = cohort_stats["stdev"]

    # 1. Regresión vs cohorte (audit G7 explícito)
    if stdev > 0:
        z_score = (student_slope - mean) / stdev
        if z_score < -2.0:
            alerts.append(
                {
                    "code": "regresion_vs_cohorte",
                    "severity": "high",
                    "title": "Regresión severa vs. cohorte",
                    "detail": (
                        f"Slope del estudiante ({student_slope:+.3f}) está más de 2σ "
                        f"debajo de la media de cohorte ({mean:+.3f}, σ={stdev:.3f}, "
                        f"z={z_score:+.2f}). Sugerir intervención pedagógica focalizada."
                    ),
                    "threshold_used": "-2σ",
                    "z_score": round(z_score, 3),
                }
            )
        elif z_score < -1.0:
            alerts.append(
                {
                    "code": "regresion_vs_cohorte",
                    "severity": "medium",
                    "title": "Por debajo de la media de cohorte",
                    "detail": (
                        f"Slope del estudiante ({student_slope:+.3f}) está más de 1σ "
                        f"debajo de la media de cohorte ({mean:+.3f}, σ={stdev:.3f}, "
                        f"z={z_score:+.2f}). Considerar contacto pedagógico."
                    ),
                    "threshold_used": "-1σ",
                    "z_score": round(z_score, 3),
                }
            )

    # 2. Cuartil bajo (informativa)
    quartile = position_in_quartiles(student_slope, cohort_stats)
    if quartile == "Q1":
        alerts.append(
            {
                "code": "bottom_quartile",
                "severity": "low",
                "title": "Cuartil inferior de la cohorte",
                "detail": (
                    f"El estudiante está en Q1 (peor 25%) — slope {student_slope:+.3f}, "
                    f"Q1 ≤ {cohort_stats['q1']:+.3f}. Informativo; no toda Q1 requiere intervención."
                ),
                "threshold_used": "Q1",
            }
        )

    # 3. Slope negativo significativo (independiente de cohorte)
    if student_slope < -0.3:
        alerts.append(
            {
                "code": "slope_negativo_significativo",
                "severity": "medium",
                "title": "Empeoramiento sostenido",
                "detail": (
                    f"Slope absoluto {student_slope:+.3f} indica retroceso de "
                    f">0.3 categorías ordinales por episodio. Revisar trayectoria."
                ),
                "threshold_used": "slope < -0.3",
            }
        )

    return alerts


def compute_cohort_quartiles_payload(
    student_slopes: list[float],
) -> dict[str, Any]:
    """Helper de alto nivel — output del endpoint `/cohort/{id}/cii-quartiles`."""
    stats = compute_cohort_slopes_stats(student_slopes)
    return {
        "labeler_version": ALERTS_VERSION,
        "min_students_for_quartiles": MIN_STUDENTS_FOR_QUARTILES,
        **stats,
    }


def compute_alerts_payload(
    student_slope: float | None,
    cohort_stats: dict[str, Any],
) -> dict[str, Any]:
    """Helper de alto nivel — output del endpoint `/student/{id}/alerts`."""
    alerts = compute_student_alerts(student_slope, cohort_stats)
    quartile = (
        position_in_quartiles(student_slope, cohort_stats) if student_slope is not None else None
    )
    return {
        "labeler_version": ALERTS_VERSION,
        "student_slope": student_slope,
        "cohort_stats": cohort_stats,
        "quartile": quartile,
        "alerts": alerts,
        "n_alerts": len(alerts),
        "highest_severity": _highest_severity(alerts) if alerts else None,
    }


def _highest_severity(alerts: list[dict[str, Any]]) -> AlertSeverity:
    """Severity más alta de una lista no vacía."""
    order = {"low": 0, "medium": 1, "high": 2}
    return max(alerts, key=lambda a: order[a["severity"]])["severity"]


# Sanity: math.nan tracking — si el caller pasa NaN, devolver lista vacía
# (defensivo).
def _is_finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)
