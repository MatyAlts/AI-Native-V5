"""Tests de A/B testing de reference_profiles."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from platform_ops.ab_testing import (
    EpisodeForComparison,
    compare_profiles,
)

# ── Fakes que simulan el classifier-service ──────────────────────────


@dataclass
class FakeClassification:
    appropriation: str


def fake_compute_hash(profile: dict) -> str:
    """Hash simplificado para tests."""
    return f"hash_of_{profile.get('name', 'x')}_{profile.get('version', 'x')}"


def make_fake_classify(per_profile_rules: dict[str, dict[str, str]]):
    """Factory que devuelve una classify_fn parametrizada.

    Args:
        per_profile_rules: {profile_name: {episode_id: predicted_label}}
    """

    def classify_fn(events, reference_profile):
        profile_name = reference_profile["name"]
        # Los tests pasan episode_id como primer seq para poder identificarlo
        if not events:
            return FakeClassification("apropiacion_superficial")
        episode_id = events[0].get("episode_id", "ep_unknown")
        rules = per_profile_rules.get(profile_name, {})
        pred = rules.get(episode_id, "apropiacion_superficial")
        return FakeClassification(pred)

    return classify_fn


def _ep(episode_id: str, human_label: str) -> EpisodeForComparison:
    return EpisodeForComparison(
        episode_id=episode_id,
        events=[{"episode_id": episode_id, "seq": 0}],  # stub
        human_label=human_label,
    )


# ── Tests ─────────────────────────────────────────────────────────────


def test_lista_vacia_de_episodios_falla() -> None:
    with pytest.raises(ValueError, match="episodes"):
        compare_profiles([], [{"name": "x"}], make_fake_classify({}), fake_compute_hash)


def test_lista_vacia_de_profiles_falla() -> None:
    with pytest.raises(ValueError, match="profiles"):
        compare_profiles(
            [_ep("e1", "apropiacion_reflexiva")], [], make_fake_classify({}), fake_compute_hash
        )


def test_profile_perfecto_tiene_kappa_1() -> None:
    """Si el profile predice exactamente lo mismo que los humanos → kappa=1."""
    episodes = [
        _ep("e1", "apropiacion_reflexiva"),
        _ep("e2", "delegacion_pasiva"),
        _ep("e3", "apropiacion_superficial"),
    ]
    perfect_profile = {"name": "perfect", "version": "v1"}
    # Este profile predice exactamente igual que el humano
    classify_fn = make_fake_classify(
        {
            "perfect": {
                "e1": "apropiacion_reflexiva",
                "e2": "delegacion_pasiva",
                "e3": "apropiacion_superficial",
            },
        }
    )

    report = compare_profiles(episodes, [perfect_profile], classify_fn, fake_compute_hash)
    assert report.n_episodes == 3
    assert len(report.results) == 1
    assert report.results[0].kappa.kappa == 1.0
    assert report.winner_by_kappa == "perfect"


def test_dos_profiles_compiten_gana_el_mejor() -> None:
    episodes = [
        _ep("e1", "apropiacion_reflexiva"),
        _ep("e2", "apropiacion_reflexiva"),
        _ep("e3", "delegacion_pasiva"),
        _ep("e4", "delegacion_pasiva"),
    ]
    profile_a = {"name": "default", "version": "v1"}
    profile_b = {"name": "stricter", "version": "v2"}

    classify_fn = make_fake_classify(
        {
            # default acierta los 4
            "default": {
                "e1": "apropiacion_reflexiva",
                "e2": "apropiacion_reflexiva",
                "e3": "delegacion_pasiva",
                "e4": "delegacion_pasiva",
            },
            # stricter falla en 1 (clasifica reflexiva como superficial)
            "stricter": {
                "e1": "apropiacion_superficial",  # error
                "e2": "apropiacion_reflexiva",
                "e3": "delegacion_pasiva",
                "e4": "delegacion_pasiva",
            },
        }
    )

    report = compare_profiles(
        episodes,
        [profile_a, profile_b],
        classify_fn,
        fake_compute_hash,
    )

    assert report.winner_by_kappa == "default"
    # default = 1.0, stricter < 1.0
    default_result = next(r for r in report.results if r.profile_name == "default")
    stricter_result = next(r for r in report.results if r.profile_name == "stricter")
    assert default_result.kappa.kappa == 1.0
    assert stricter_result.kappa.kappa < 1.0


def test_report_incluye_predicciones_y_hash() -> None:
    episodes = [_ep("e1", "apropiacion_reflexiva")]
    profile = {"name": "test", "version": "v1"}
    classify_fn = make_fake_classify(
        {
            "test": {"e1": "apropiacion_reflexiva"},
        }
    )

    report = compare_profiles(episodes, [profile], classify_fn, fake_compute_hash)
    result = report.results[0]
    assert result.predictions == {"e1": "apropiacion_reflexiva"}
    assert result.profile_hash == "hash_of_test_v1"
    assert result.profile_version == "v1"


def test_summary_table_legible() -> None:
    episodes = [_ep("e1", "apropiacion_reflexiva"), _ep("e2", "delegacion_pasiva")]
    profile_a = {"name": "default", "version": "v1"}
    classify_fn = make_fake_classify(
        {
            "default": {"e1": "apropiacion_reflexiva", "e2": "delegacion_pasiva"},
        }
    )

    report = compare_profiles(episodes, [profile_a], classify_fn, fake_compute_hash)
    table = report.summary_table()

    assert "A/B Testing" in table
    assert "default" in table
    assert "v1" in table
    assert "Ganador" in table


def test_tres_profiles_simultaneos() -> None:
    """Verificar escalabilidad a N profiles."""
    episodes = [_ep(f"e{i}", "apropiacion_reflexiva") for i in range(5)]
    profiles = [
        {"name": "p1", "version": "v1"},
        {"name": "p2", "version": "v1"},
        {"name": "p3", "version": "v1"},
    ]
    # Cada profile tiene tasas de acierto distintas
    classify_fn = make_fake_classify(
        {
            "p1": {f"e{i}": "apropiacion_reflexiva" for i in range(5)},  # perfecto
            "p2": {f"e{i}": "apropiacion_reflexiva" for i in range(3)},  # 3/5 bien
            "p3": {f"e{i}": "apropiacion_superficial" for i in range(5)},  # todo mal
        }
    )

    report = compare_profiles(episodes, profiles, classify_fn, fake_compute_hash)
    assert len(report.results) == 3
    # p1 gana con kappa=1.0
    assert report.winner_by_kappa == "p1"
