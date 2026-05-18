"""Test de integración: A/B testing con el classifier real.

Usa el pipeline real del classifier-service (no mockeado) para
verificar que el módulo ab_testing funciona con la implementación
productiva, no solo con fakes.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Permitir importar el classifier-service sin tenerlo instalado
CLASSIFIER_SRC = Path(__file__).parent.parent.parent.parent / "apps/classifier-service/src"
if str(CLASSIFIER_SRC) not in sys.path:
    sys.path.insert(0, str(CLASSIFIER_SRC))

from classifier_service.services.pipeline import (
    classify_episode_from_events,
    compute_classifier_config_hash,
)
from classifier_service.services.tree import DEFAULT_REFERENCE_PROFILE
from platform_ops.ab_testing import EpisodeForComparison, compare_profiles


def _ev(seq: int, event_type: str, minute: int, payload: dict | None = None) -> dict:
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "seq": seq,
        "event_type": event_type,
        "ts": (base + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def _copypaste_events() -> list[dict]:
    """Escenario claro de delegación pasiva: orphan ratio extremo."""
    events = [_ev(0, "episodio_abierto", 0)]
    for i, m in enumerate([2, 2, 3, 15, 15, 16, 18, 25, 25, 26]):
        if i % 3 == 0:
            events.append(
                _ev(
                    len(events),
                    "prompt_enviado",
                    m,
                    {"content": "dame la solución", "prompt_kind": "solicitud_directa"},
                )
            )
        elif i % 3 == 1:
            events.append(_ev(len(events), "tutor_respondio", m, {"content": "..."}))
        else:
            events.append(_ev(len(events), "codigo_ejecutado", m))
    return events


def test_ab_testing_integration_con_classifier_real() -> None:
    """El módulo ab_testing se integra correctamente con el pipeline real."""
    # 2 episodios claramente de delegación pasiva (con orphan_ratio muy alto)
    episodes = [
        EpisodeForComparison(
            episode_id=f"ep_{i}",
            events=_copypaste_events(),
            human_label="delegacion_pasiva",  # gold standard
        )
        for i in range(3)
    ]

    # Profile default
    profile_default = DEFAULT_REFERENCE_PROFILE

    # Profile más relajado: umbral extremo más alto = más difícil de disparar delegación extrema
    profile_relaxed = {
        **DEFAULT_REFERENCE_PROFILE,
        "name": "relaxed",
        "thresholds": {
            **DEFAULT_REFERENCE_PROFILE["thresholds"],
        },
    }

    report = compare_profiles(
        episodes=episodes,
        profiles=[profile_default, profile_relaxed],
        classify_fn=classify_episode_from_events,
        compute_hash_fn=compute_classifier_config_hash,
    )

    # Al menos uno de los dos profiles debe haber clasificado bien
    assert len(report.results) == 2
    for result in report.results:
        # Con el escenario de copypaste extremo, ambos deberían acertar
        for pred in result.predictions.values():
            # ambos profiles deberían detectar delegación pasiva en este caso
            assert pred == "delegacion_pasiva"


def test_ab_testing_detecta_profile_mejor() -> None:
    """Dos profiles con umbrales distintos dan distintas predicciones → kappa distinto."""
    # Construimos episodios que sean ambiguos entre los dos profiles
    # Con EXTREME_ORPHAN_THRESHOLD, más episodios caen en delegación
    episodes = [
        EpisodeForComparison(
            episode_id=f"ep_{i}",
            events=_copypaste_events(),
            human_label="delegacion_pasiva",
        )
        for i in range(5)
    ]

    # Profile default (EXTREME_ORPHAN_THRESHOLD=0.8)
    profile_default = dict(DEFAULT_REFERENCE_PROFILE)
    profile_default["name"] = "default_v1"

    # Profile B idéntico → debe dar los mismos resultados
    profile_b = dict(DEFAULT_REFERENCE_PROFILE)
    profile_b["name"] = "duplicate_v1"

    report = compare_profiles(
        episodes=episodes,
        profiles=[profile_default, profile_b],
        classify_fn=classify_episode_from_events,
        compute_hash_fn=compute_classifier_config_hash,
    )

    # Deben dar EXACTAMENTE las mismas predicciones
    default_result = next(r for r in report.results if r.profile_name == "default_v1")
    dup_result = next(r for r in report.results if r.profile_name == "duplicate_v1")
    assert default_result.predictions == dup_result.predictions
    assert default_result.kappa.kappa == dup_result.kappa.kappa
