"""Tests de la logica pura de deteccion de episodios fantasma.

Sin DB: la funcion `select_ghost_episodes` opera sobre `EpisodeInfo` planos.
Casos cubiertos (espejo del enunciado de la limpieza retroactiva):
    (a) 1 clasificado + 3 paused mismo ejercicio -> marca los 3 paused.
    (b) paused de ejercicio NO completado -> no marca.
    (c) paused unico sin completado -> no marca.
    (d) ya superseded -> no re-marca.
    (e) closed sin clasificar -> no marca (no es paused).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from platform_ops.ghost_episodes import (
    EpisodeInfo,
    build_superseded_meta,
    select_ghost_episodes,
)

STUDENT = UUID("b1b1b1b1-0001-0001-0001-000000000001")
PROBLEMA = UUID("11111111-2222-3333-4444-555555555555")
EJERCICIO = UUID("99999999-8888-7777-6666-555555555555")


def _ep(
    estado: str,
    is_classified: bool,
    *,
    ejercicio_id: UUID | None = EJERCICIO,
    problema_id: UUID = PROBLEMA,
    student: UUID = STUDENT,
    meta: dict | None = None,
    episode_id: UUID | None = None,
) -> EpisodeInfo:
    return EpisodeInfo(
        episode_id=episode_id or uuid4(),
        student_pseudonym=student,
        problema_id=problema_id,
        ejercicio_id=ejercicio_id,
        estado=estado,
        is_classified=is_classified,
        opened_at=datetime.now(UTC),
        events_count=3,
        meta=meta or {},
    )


def test_a_marca_los_3_paused_cuando_hay_uno_clasificado() -> None:
    """1 clasificado (closed) + 3 paused mismo ejercicio -> marca los 3 paused."""
    good = _ep("closed", is_classified=True)
    paused = [_ep("paused", is_classified=False) for _ in range(3)]
    episodes = [good, *paused]

    marks = select_ghost_episodes(episodes)

    assert len(marks) == 3
    marked_ids = {m.episode_id for m in marks}
    assert marked_ids == {p.episode_id for p in paused}
    # Todos apuntan al episodio bueno como superseded_by.
    assert all(m.superseded_by == good.episode_id for m in marks)


def test_b_paused_de_ejercicio_no_completado_no_se_marca() -> None:
    """Paused de un ejercicio que nadie completo (sin clasificado) -> no marca."""
    # Ejercicio X tiene un clasificado; ejercicio Y solo tiene un paused.
    ejercicio_x = uuid4()
    ejercicio_y = uuid4()
    completado_x = _ep("closed", is_classified=True, ejercicio_id=ejercicio_x)
    huerfano_y = _ep("paused", is_classified=False, ejercicio_id=ejercicio_y)

    marks = select_ghost_episodes([completado_x, huerfano_y])

    assert marks == []


def test_c_paused_unico_sin_completado_no_se_marca() -> None:
    """Un solo paused, nadie completo el ejercicio -> no marca."""
    solo = _ep("paused", is_classified=False)

    marks = select_ghost_episodes([solo])

    assert marks == []


def test_d_ya_superseded_no_se_re_marca() -> None:
    """Idempotencia: episodios ya marcados (meta superseded) se saltean."""
    good = _ep("closed", is_classified=True)
    ya_marcado = _ep(
        "paused",
        is_classified=False,
        meta={"superseded": True, "superseded_by": str(good.episode_id)},
    )
    pendiente = _ep("paused", is_classified=False)

    marks = select_ghost_episodes([good, ya_marcado, pendiente])

    # Solo el pendiente; el ya marcado se omite.
    assert len(marks) == 1
    assert marks[0].episode_id == pendiente.episode_id


def test_e_closed_sin_clasificar_no_se_marca() -> None:
    """Un closed sin clasificar NO se marca (la condicion 1 exige paused)."""
    good = _ep("closed", is_classified=True)
    closed_sin_clasificar = _ep("closed", is_classified=False)

    marks = select_ghost_episodes([good, closed_sin_clasificar])

    assert marks == []


def test_agrupa_por_ejercicio_distinto_no_cruza() -> None:
    """Dos ejercicios distintos: el paused de uno no se marca por el clasificado del otro."""
    ej_a = uuid4()
    ej_b = uuid4()
    good_a = _ep("closed", is_classified=True, ejercicio_id=ej_a)
    paused_a = _ep("paused", is_classified=False, ejercicio_id=ej_a)
    paused_b = _ep("paused", is_classified=False, ejercicio_id=ej_b)  # sin bueno en B

    marks = select_ghost_episodes([good_a, paused_a, paused_b])

    assert len(marks) == 1
    assert marks[0].episode_id == paused_a.episode_id


def test_legacy_sin_ejercicio_id_agrupa_por_problema() -> None:
    """Episodios legacy (ejercicio_id=None) agrupan por (student, problema)."""
    good = _ep("closed", is_classified=True, ejercicio_id=None)
    paused = _ep("paused", is_classified=False, ejercicio_id=None)

    marks = select_ghost_episodes([good, paused])

    assert len(marks) == 1
    assert marks[0].episode_id == paused.episode_id
    assert marks[0].ejercicio_id is None


def test_superseded_by_es_deterministico() -> None:
    """El episodio 'bueno' elegido es estable (menor episode_id) entre corridas."""
    e1 = UUID("00000000-0000-0000-0000-000000000001")
    e2 = UUID("00000000-0000-0000-0000-000000000002")
    good_low = _ep("closed", is_classified=True, episode_id=e1)
    good_high = _ep("closed", is_classified=True, episode_id=e2)
    paused = _ep("paused", is_classified=False)

    marks = select_ghost_episodes([good_high, paused, good_low])

    assert len(marks) == 1
    assert marks[0].superseded_by == e1  # el de menor episode_id


def test_build_superseded_meta_no_muta_y_agrega_claves() -> None:
    original = {"prompts": 5, "tiempo_activo": 120}
    by = uuid4()
    at = "2026-06-17T12:00:00+00:00"

    new_meta = build_superseded_meta(original, superseded_by=by, superseded_at=at)

    # No muta el original.
    assert "superseded" not in original
    # Agrega las 4 claves + preserva las existentes.
    assert new_meta["prompts"] == 5
    assert new_meta["tiempo_activo"] == 120
    assert new_meta["superseded"] is True
    assert new_meta["superseded_by"] == str(by)
    assert new_meta["superseded_reason"] == "ghost_resume_duplicate"
    assert new_meta["superseded_at"] == at


def test_build_superseded_meta_acepta_none() -> None:
    new_meta = build_superseded_meta(None, superseded_by=uuid4(), superseded_at="x")
    assert new_meta["superseded"] is True
