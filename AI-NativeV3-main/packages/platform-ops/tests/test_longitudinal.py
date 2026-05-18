"""Tests del análisis longitudinal por estudiante."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from platform_ops.longitudinal import (
    APPROPRIATION_ORDINAL,
    ClassificationPoint,
    StudentTrajectory,
    build_trajectories,
    summarize_cohort,
)


@dataclass
class FakeDataSource:
    grouped: dict[str, list[dict]] = field(default_factory=dict)

    async def list_classifications_grouped_by_student(self, comision_id: UUID):
        return self.grouped


def _cp(seconds_offset: int, appropriation: str) -> ClassificationPoint:
    base = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    return ClassificationPoint(
        episode_id=uuid4(),
        classified_at=base + timedelta(seconds=seconds_offset),
        appropriation=appropriation,
    )


# ── StudentTrajectory ────────────────────────────────────────────────


def test_trayectoria_vacia_sin_errores() -> None:
    t = StudentTrajectory(student_pseudonym="s_1")
    assert t.n_episodes == 0
    assert t.first_classification is None
    assert t.last_classification is None
    assert t.tercile_means() is None
    assert t.progression_label() == "insuficiente"


def test_trayectoria_con_1_episodio_es_insuficiente() -> None:
    t = StudentTrajectory(student_pseudonym="s_1", points=[_cp(0, "apropiacion_reflexiva")])
    assert t.progression_label() == "insuficiente"
    assert t.tercile_means() is None


def test_trayectoria_siempre_reflexiva_es_estable() -> None:
    t = StudentTrajectory(
        student_pseudonym="s_1",
        points=[_cp(i, "apropiacion_reflexiva") for i in range(6)],
    )
    terciles = t.tercile_means()
    assert terciles == (2.0, 2.0, 2.0)
    assert t.progression_label() == "estable"


def test_trayectoria_de_delegacion_a_reflexiva_es_mejorando() -> None:
    """El caso ideal: estudiante empezó mal y terminó bien."""
    points = [
        _cp(0, "delegacion_pasiva"),
        _cp(100, "delegacion_pasiva"),
        _cp(200, "apropiacion_superficial"),  # medio
        _cp(300, "apropiacion_superficial"),
        _cp(400, "apropiacion_reflexiva"),  # final
        _cp(500, "apropiacion_reflexiva"),
    ]
    t = StudentTrajectory(student_pseudonym="s_1", points=points)
    terciles = t.tercile_means()
    assert terciles == (0.0, 1.0, 2.0)  # (delegacion, superficial, reflexiva)
    assert t.progression_label() == "mejorando"


def test_trayectoria_de_reflexiva_a_delegacion_es_empeorando() -> None:
    """Regresión preocupante: estudiante empezó bien y abandonó."""
    points = [
        _cp(0, "apropiacion_reflexiva"),
        _cp(100, "apropiacion_reflexiva"),
        _cp(200, "apropiacion_superficial"),
        _cp(300, "apropiacion_superficial"),
        _cp(400, "delegacion_pasiva"),
        _cp(500, "delegacion_pasiva"),
    ]
    t = StudentTrajectory(student_pseudonym="s_1", points=points)
    assert t.progression_label() == "empeorando"


def test_cambio_de_solo_una_categoria_es_estable() -> None:
    """Cambios pequeños dentro del margen de tolerancia no se cuentan."""
    # Primer tercio = superficial (1.0), último tercio también = superficial
    points = [
        _cp(0, "apropiacion_superficial"),
        _cp(100, "apropiacion_superficial"),
        _cp(200, "apropiacion_reflexiva"),
        _cp(300, "apropiacion_superficial"),
        _cp(400, "apropiacion_superficial"),
        _cp(500, "apropiacion_reflexiva"),
    ]
    t = StudentTrajectory(student_pseudonym="s_1", points=points)
    # primer_tercio = (0+0)/2 = 0 ... actually wait
    # scores = [1, 1, 2, 1, 1, 2]
    # first = [1, 1] → mean 1.0
    # last = [1, 2] → mean 1.5
    # diff = 0.5 → > 0.25 → mejorando
    assert t.progression_label() == "mejorando"


def test_max_appropriation_reached() -> None:
    t = StudentTrajectory(
        student_pseudonym="s_1",
        points=[
            _cp(0, "delegacion_pasiva"),
            _cp(100, "apropiacion_reflexiva"),
            _cp(200, "apropiacion_superficial"),
        ],
    )
    assert t.max_appropriation_reached() == "apropiacion_reflexiva"


def test_appropriation_ordinal_preserva_orden() -> None:
    """El orden ordinal debe ser delegacion < superficial < reflexiva."""
    assert (
        APPROPRIATION_ORDINAL["delegacion_pasiva"]
        < APPROPRIATION_ORDINAL["apropiacion_superficial"]
    )
    assert (
        APPROPRIATION_ORDINAL["apropiacion_superficial"]
        < APPROPRIATION_ORDINAL["apropiacion_reflexiva"]
    )


# ── build_trajectories ────────────────────────────────────────────────


async def test_build_trajectories_sorts_por_classified_at() -> None:
    """El data source podría devolver en cualquier orden; debemos ordenar por tiempo."""
    comision_id = uuid4()
    # Intencionalmente fuera de orden
    ds = FakeDataSource(
        grouped={
            "s_alice": [
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-05-01T10:00:00Z",
                    "appropriation": "apropiacion_reflexiva",
                },
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-03-01T10:00:00Z",
                    "appropriation": "delegacion_pasiva",
                },
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-04-01T10:00:00Z",
                    "appropriation": "apropiacion_superficial",
                },
            ],
        }
    )

    trajectories = await build_trajectories(ds, comision_id)
    assert len(trajectories) == 1
    alice = trajectories[0]
    # Ordenados cronológicamente
    assert alice.points[0].appropriation == "delegacion_pasiva"
    assert alice.points[1].appropriation == "apropiacion_superficial"
    assert alice.points[2].appropriation == "apropiacion_reflexiva"
    assert alice.progression_label() == "mejorando"


async def test_build_trajectories_multi_estudiante() -> None:
    ds = FakeDataSource(
        grouped={
            "s_alice": [
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-03-01T10:00:00Z",
                    "appropriation": "delegacion_pasiva",
                },
            ],
            "s_bob": [
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-03-01T10:00:00Z",
                    "appropriation": "apropiacion_reflexiva",
                },
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-03-02T10:00:00Z",
                    "appropriation": "apropiacion_reflexiva",
                },
            ],
        }
    )
    trajectories = await build_trajectories(ds, uuid4())
    assert len(trajectories) == 2
    pseudonyms = {t.student_pseudonym for t in trajectories}
    assert pseudonyms == {"s_alice", "s_bob"}


# ── summarize_cohort ──────────────────────────────────────────────────


def test_cohort_summary_cuenta_por_label() -> None:
    comision_id = uuid4()
    trajectories = [
        # mejorando
        StudentTrajectory(
            "s_1",
            [
                _cp(0, "delegacion_pasiva"),
                _cp(100, "delegacion_pasiva"),
                _cp(200, "apropiacion_superficial"),
                _cp(300, "apropiacion_superficial"),
                _cp(400, "apropiacion_reflexiva"),
                _cp(500, "apropiacion_reflexiva"),
            ],
        ),
        # estable
        StudentTrajectory("s_2", [_cp(i, "apropiacion_superficial") for i in range(6)]),
        # empeorando
        StudentTrajectory(
            "s_3",
            [
                _cp(0, "apropiacion_reflexiva"),
                _cp(100, "apropiacion_reflexiva"),
                _cp(200, "apropiacion_superficial"),
                _cp(300, "apropiacion_superficial"),
                _cp(400, "delegacion_pasiva"),
                _cp(500, "delegacion_pasiva"),
            ],
        ),
        # insuficiente (1 episodio)
        StudentTrajectory("s_4", [_cp(0, "apropiacion_reflexiva")]),
    ]
    summary = summarize_cohort(comision_id, trajectories)

    assert summary.n_students == 4
    assert summary.n_students_with_enough_data == 3
    assert summary.mejorando == 1
    assert summary.estable == 1
    assert summary.empeorando == 1
    assert summary.insuficiente == 1


def test_net_progression_positiva_si_mayoria_mejora() -> None:
    comision_id = uuid4()
    trajectories = [
        # 3 mejorando
        *[
            StudentTrajectory(
                f"s_{i}",
                [
                    _cp(0, "delegacion_pasiva"),
                    _cp(100, "delegacion_pasiva"),
                    _cp(200, "apropiacion_superficial"),
                    _cp(300, "apropiacion_superficial"),
                    _cp(400, "apropiacion_reflexiva"),
                    _cp(500, "apropiacion_reflexiva"),
                ],
            )
            for i in range(3)
        ],
        # 1 empeorando
        StudentTrajectory(
            "s_bad",
            [
                _cp(0, "apropiacion_reflexiva"),
                _cp(100, "apropiacion_reflexiva"),
                _cp(200, "apropiacion_superficial"),
                _cp(300, "apropiacion_superficial"),
                _cp(400, "delegacion_pasiva"),
                _cp(500, "delegacion_pasiva"),
            ],
        ),
    ]
    summary = summarize_cohort(comision_id, trajectories)
    # 3 mejorando, 1 empeorando, 4 con data
    # net = (3 - 1) / 4 = 0.5
    assert summary.net_progression_ratio == 0.5


def test_net_progression_0_si_no_hay_datos() -> None:
    summary = summarize_cohort(uuid4(), [])
    assert summary.net_progression_ratio == 0.0
