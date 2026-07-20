"""A/B testing de reference_profiles del clasificador N4.

Permite correr MÚLTIPLES profiles sobre el mismo set de eventos y
comparar cómo clasifican cada profile. Esencial para calibrar umbrales
con datos reales del piloto:

  - Dado un set etiquetado por humanos (gold standard),
  - Dado dos profiles candidatos (A = default, B = tighter thresholds),
  - ¿Cuál de los dos tiene mayor Kappa contra el etiquetado humano?

Arquitectura: re-uso puro del pipeline del classifier-service. Los
profiles se pasan como dicts en memoria; no hay que tocar la DB ni
reemplazar el `is_current` de las clasificaciones reales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from platform_ops.kappa_analysis import (
    KappaRating,
    KappaResult,
    compute_cohen_kappa,
)


@dataclass
class EpisodeForComparison:
    """Un episodio con sus eventos crudos + su etiqueta de gold standard."""

    episode_id: str
    events: list[dict]  # formato que espera classify_episode_from_events
    human_label: str  # etiqueta de gold standard (rater humano)


@dataclass
class ProfileComparisonResult:
    """Resultado de evaluar un profile contra un set etiquetado."""

    profile_name: str
    profile_version: str
    profile_hash: str
    kappa: KappaResult
    predictions: dict[str, str]  # episode_id → predicción del profile

    @property
    def interpretation(self) -> str:
        return self.kappa.interpretation


@dataclass
class ABComparisonReport:
    """Comparación de 2+ profiles contra un gold standard."""

    n_episodes: int
    results: list[ProfileComparisonResult] = field(default_factory=list)
    winner_by_kappa: str | None = None  # profile_name con mejor kappa

    def summary_table(self) -> str:
        """Tabla legible para humanos."""
        lines = [
            f"A/B Testing de {len(self.results)} profiles sobre {self.n_episodes} episodios",
            "",
            f"{'Profile':<30} {'Version':<10} {'Kappa':<10} {'Interpretación':<20}",
            "-" * 70,
        ]
        for r in self.results:
            lines.append(
                f"{r.profile_name:<30} {r.profile_version:<10} "
                f"{r.kappa.kappa:<10.4f} {r.interpretation:<20}"
            )
        if self.winner_by_kappa:
            lines.append("")
            lines.append(f"Ganador (mayor Kappa): {self.winner_by_kappa}")
        return "\n".join(lines)


def compare_profiles(
    episodes: list[EpisodeForComparison],
    profiles: list[dict[str, Any]],
    classify_fn,
    compute_hash_fn,
) -> ABComparisonReport:
    """Evalúa múltiples profiles contra un set etiquetado.

    Args:
        episodes: lista de episodios con events + human_label
        profiles: lista de dicts con formato de reference_profile
        classify_fn: función `classify_episode_from_events(events, reference_profile)`
            del classifier-service
        compute_hash_fn: función `compute_classifier_config_hash(profile)` del
            classifier-service

    Returns:
        ABComparisonReport con un ProfileComparisonResult por cada profile.
    """
    if not episodes:
        raise ValueError("episodes no puede estar vacío")
    if not profiles:
        raise ValueError("profiles no puede estar vacío")

    results: list[ProfileComparisonResult] = []

    for profile in profiles:
        # 1. Clasificar todos los episodios con este profile
        predictions: dict[str, str] = {}
        ratings: list[KappaRating] = []

        for ep in episodes:
            classification = classify_fn(ep.events, reference_profile=profile)
            pred = classification.appropriation
            predictions[ep.episode_id] = pred

            ratings.append(
                KappaRating(
                    episode_id=ep.episode_id,
                    rater_a=pred,  # predicción del profile (modelo)
                    rater_b=ep.human_label,  # gold standard humano
                )
            )

        # 2. Calcular Kappa del profile vs humano
        kappa = compute_cohen_kappa(ratings)

        results.append(
            ProfileComparisonResult(
                profile_name=profile.get("name", "unknown"),
                profile_version=profile.get("version", "unknown"),
                profile_hash=compute_hash_fn(profile),
                kappa=kappa,
                predictions=predictions,
            )
        )

    # Determinar ganador
    winner = None
    if results:
        winner = max(results, key=lambda r: r.kappa.kappa).profile_name

    return ABComparisonReport(
        n_episodes=len(episodes),
        results=results,
        winner_by_kappa=winner,
    )


__all__ = [
    "ABComparisonReport",
    "EpisodeForComparison",
    "ProfileComparisonResult",
    "compare_profiles",
]
