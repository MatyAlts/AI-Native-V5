"""Tests del modulo cii_longitudinal (ADR-018, G2 minimo)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from platform_ops.cii_longitudinal import (
    CII_LONGITUDINAL_VERSION,
    MIN_EPISODES_FOR_LONGITUDINAL,
    compute_cii_evolution_longitudinal,
    compute_evolution_per_template,
    compute_mean_slope,
)


def _cls(
    *,
    template_id: UUID | str | None,
    appropriation: str,
    minute_offset: int = 0,
) -> dict[str, Any]:
    """Helper para construir una classification fake."""
    base = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    return {
        "template_id": template_id,
        "appropriation": appropriation,
        "classified_at": base + timedelta(minutes=minute_offset),
        "episode_id": uuid4(),
    }


# ---------------------------------------------------------------------------
# compute_evolution_per_template
# ---------------------------------------------------------------------------


def test_template_con_3_episodios_mejorando_da_slope_positivo() -> None:
    """delegacion(0) → superficial(1) → reflexiva(2) — slope = +1.0."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=120),
    ]
    result = compute_evolution_per_template(classifications)
    assert len(result) == 1
    entry = result[0]
    assert entry["template_id"] == tid
    assert entry["n_episodes"] == 3
    assert entry["scores_ordinal"] == [0, 1, 2]
    assert entry["slope"] == 1.0
    assert entry["insufficient_data"] is False


def test_template_con_3_episodios_empeorando_da_slope_negativo() -> None:
    """reflexiva(2) → superficial(1) → delegacion(0) — slope = -1.0."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=120),
    ]
    result = compute_evolution_per_template(classifications)
    assert result[0]["slope"] == -1.0


def test_template_con_3_episodios_estable_da_slope_cero() -> None:
    """Mismo nivel en los 3 episodios — slope = 0.0."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=120),
    ]
    result = compute_evolution_per_template(classifications)
    assert result[0]["slope"] == 0.0


def test_template_con_2_episodios_es_insufficient_data() -> None:
    """N=2 < MIN_EPISODES_FOR_LONGITUDINAL=3 → slope=null + insufficient_data=true."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=60),
    ]
    result = compute_evolution_per_template(classifications)
    assert len(result) == 1
    entry = result[0]
    assert entry["n_episodes"] == 2
    assert entry["slope"] is None
    assert entry["insufficient_data"] is True


def test_template_con_1_episodio_es_insufficient_data() -> None:
    tid = uuid4()
    classifications = [_cls(template_id=tid, appropriation="apropiacion_reflexiva")]
    result = compute_evolution_per_template(classifications)
    assert result[0]["slope"] is None
    assert result[0]["insufficient_data"] is True


def test_classifications_sin_template_id_se_skippean() -> None:
    """TPs huerfanas (template_id=None) NO entran al calculo. Limitacion
    declarada del piloto inicial."""
    tid = uuid4()
    classifications = [
        _cls(template_id=None, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=60),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=120),
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=180),
    ]
    result = compute_evolution_per_template(classifications)
    # Solo el template tid aparece — los None se descartan
    assert len(result) == 1
    assert result[0]["template_id"] == tid
    assert result[0]["n_episodes"] == 3


def test_multiples_templates_dan_un_slope_por_template() -> None:
    """Estudiante con episodios sobre 2 templates distintos → 2 entries."""
    t1 = uuid4()
    t2 = uuid4()
    classifications = [
        # Template 1: mejorando
        _cls(template_id=t1, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=t1, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=t1, appropriation="apropiacion_reflexiva", minute_offset=120),
        # Template 2: estable
        _cls(template_id=t2, appropriation="apropiacion_reflexiva", minute_offset=200),
        _cls(template_id=t2, appropriation="apropiacion_reflexiva", minute_offset=260),
        _cls(template_id=t2, appropriation="apropiacion_reflexiva", minute_offset=320),
    ]
    result = compute_evolution_per_template(classifications)
    by_template = {entry["template_id"]: entry for entry in result}
    assert by_template[t1]["slope"] == 1.0
    assert by_template[t2]["slope"] == 0.0


def test_input_desordenado_se_ordena_por_classified_at() -> None:
    """El orden de la lista de input no debe afectar el resultado.
    Lo que ordena es `classified_at` ascendente."""
    tid = uuid4()
    # Mismo escenario "mejorando", pero input desordenado
    classifications = [
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=120),
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=60),
    ]
    result = compute_evolution_per_template(classifications)
    assert result[0]["scores_ordinal"] == [0, 1, 2]
    assert result[0]["slope"] == 1.0


def test_classified_at_como_string_iso_8601_funciona() -> None:
    """`classified_at` puede venir como str ISO-8601 (caso de DataSources que
    no parsean a datetime) — debe funcionar igual."""
    tid = uuid4()
    classifications = [
        {
            "template_id": tid,
            "appropriation": "delegacion_pasiva",
            "classified_at": "2026-04-01T10:00:00Z",
        },
        {
            "template_id": tid,
            "appropriation": "apropiacion_superficial",
            "classified_at": "2026-04-01T11:00:00Z",
        },
        {
            "template_id": tid,
            "appropriation": "apropiacion_reflexiva",
            "classified_at": "2026-04-01T12:00:00Z",
        },
    ]
    result = compute_evolution_per_template(classifications)
    assert result[0]["slope"] == 1.0


def test_appropriation_invalida_se_skippea_silenciosamente() -> None:
    """Si por bug en el clasificador llega un appropriation no canonico,
    el calculo lo descarta en vez de crashear. Defensivo."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=0),
        _cls(template_id=tid, appropriation="invalid_label", minute_offset=60),
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=120),
    ]
    result = compute_evolution_per_template(classifications)
    # El invalid_label se descarta — N efectivo = 2 → insufficient
    assert result[0]["n_episodes"] == 2
    assert result[0]["insufficient_data"] is True


# ---------------------------------------------------------------------------
# compute_mean_slope
# ---------------------------------------------------------------------------


def test_mean_slope_promedia_solo_templates_con_slope_no_null() -> None:
    """Templates con N<3 (slope=null) NO entran al promedio."""
    per_template = [
        {"template_id": "t1", "n_episodes": 3, "slope": 1.0, "insufficient_data": False},
        {"template_id": "t2", "n_episodes": 3, "slope": -1.0, "insufficient_data": False},
        {"template_id": "t3", "n_episodes": 2, "slope": None, "insufficient_data": True},
    ]
    assert compute_mean_slope(per_template) == 0.0


def test_mean_slope_es_none_si_ningun_template_tiene_n_suficiente() -> None:
    per_template = [
        {"template_id": "t1", "n_episodes": 1, "slope": None, "insufficient_data": True},
        {"template_id": "t2", "n_episodes": 2, "slope": None, "insufficient_data": True},
    ]
    assert compute_mean_slope(per_template) is None


def test_mean_slope_lista_vacia_es_none() -> None:
    assert compute_mean_slope([]) is None


# ---------------------------------------------------------------------------
# compute_cii_evolution_longitudinal (helper de alto nivel)
# ---------------------------------------------------------------------------


def test_helper_devuelve_estructura_completa_para_endpoint() -> None:
    """Output del helper es lo que se serializa al endpoint analytics."""
    t1 = uuid4()
    t2 = uuid4()
    classifications = [
        _cls(template_id=t1, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=t1, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=t1, appropriation="apropiacion_reflexiva", minute_offset=120),
        _cls(template_id=t2, appropriation="delegacion_pasiva", minute_offset=200),
        _cls(template_id=t2, appropriation="delegacion_pasiva", minute_offset=260),
    ]
    result = compute_cii_evolution_longitudinal(classifications)

    assert result["n_groups_evaluated"] == 1  # solo t1 con N=3
    assert result["n_groups_insufficient"] == 1  # t2 con N=2
    assert result["n_episodes_total"] == 5
    assert len(result["evolution_per_template"]) == 2
    assert result["mean_slope"] == 1.0  # promedio de [1.0] (t1)
    assert result["sufficient_data"] is True
    assert result["labeler_version"] == CII_LONGITUDINAL_VERSION


def test_helper_lista_vacia_devuelve_estructura_vacia() -> None:
    """Estudiante sin classifications — modo dev, episodio nuevo, etc."""
    result = compute_cii_evolution_longitudinal([])
    assert result["n_groups_evaluated"] == 0
    assert result["n_groups_insufficient"] == 0
    assert result["n_episodes_total"] == 0
    assert result["evolution_per_template"] == []
    assert result["mean_slope"] is None
    assert result["sufficient_data"] is False
    assert result["labeler_version"] == CII_LONGITUDINAL_VERSION


def test_helper_solo_huerfanas_es_sufficient_data_false() -> None:
    """Estudiante con classifications pero todas sin template_id —
    insufficient_data porque ninguna entra al calculo."""
    classifications = [
        _cls(template_id=None, appropriation="apropiacion_reflexiva", minute_offset=0),
        _cls(template_id=None, appropriation="apropiacion_reflexiva", minute_offset=60),
        _cls(template_id=None, appropriation="apropiacion_reflexiva", minute_offset=120),
    ]
    result = compute_cii_evolution_longitudinal(classifications)
    assert result["n_episodes_total"] == 0
    assert result["mean_slope"] is None
    assert result["sufficient_data"] is False


def test_helper_es_funcion_pura_sin_side_effects() -> None:
    """Mismo input → mismo output. Idempotencia."""
    tid = uuid4()
    classifications = [
        _cls(template_id=tid, appropriation="delegacion_pasiva", minute_offset=0),
        _cls(template_id=tid, appropriation="apropiacion_superficial", minute_offset=60),
        _cls(template_id=tid, appropriation="apropiacion_reflexiva", minute_offset=120),
    ]
    result_a = compute_cii_evolution_longitudinal(classifications)
    result_b = compute_cii_evolution_longitudinal(classifications)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Constantes documentadas
# ---------------------------------------------------------------------------


def test_min_episodes_for_longitudinal_es_3() -> None:
    """ADR-018 documenta N=3 minimo. Si bumpea, hay que actualizar el ADR."""
    assert MIN_EPISODES_FOR_LONGITUDINAL == 3


def test_labeler_version_es_v1() -> None:
    assert CII_LONGITUDINAL_VERSION == "1.0.0"
