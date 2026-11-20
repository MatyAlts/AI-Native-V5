"""Change `sobreuso-no-es-delegacion` (P1 + A1 del plan CIbSE 2027).

La pasiva que vino SOLO de la regla de sobreuso (`delegacion_pasiva` +
subgrupo `dependiente_sobreuso`) no entra a la escala ordinal de progreso.
La etiqueta persistida no se toca: estos tests cubren el predicado y los
cálculos que lo consumen (tercios, máximo, pendientes longitudinales).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from platform_ops.cii_longitudinal import (
    compute_evolution_general,
    compute_evolution_per_template,
    compute_evolution_per_unidad,
)
from platform_ops.longitudinal import (
    APPROPRIATION_ORDINAL,
    SUBGRUPO_SOBREUSO,
    ClassificationPoint,
    StudentTrajectory,
    build_trajectories,
    es_pasiva_por_sobreuso,
    ordinal_progreso,
    subgrupo_key_de,
)

_BASE = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
_PASIVA = "delegacion_pasiva"
_REFLEXIVA = "apropiacion_reflexiva"


def _cp(i: int, appropriation: str, subgrupo_key: str | None = None) -> ClassificationPoint:
    return ClassificationPoint(
        episode_id=uuid4(),
        classified_at=_BASE + timedelta(hours=i),
        appropriation=appropriation,
        subgrupo_key=subgrupo_key,
    )


def _cls(
    i: int,
    appropriation: str,
    subgrupo_key: str | None = None,
    template_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "episode_id": uuid4(),
        "template_id": template_id,
        "unidad_id": None,
        "classified_at": _BASE + timedelta(hours=i),
        "appropriation": appropriation,
        "subgrupo_key": subgrupo_key,
    }


# ── Predicado ──────────────────────────────────────────────────────────


def test_constante_coincide_con_el_subgrupo_del_arbol() -> None:
    from classifier_service.services.subgrupo import DEPENDIENTE_SOBREUSO

    assert DEPENDIENTE_SOBREUSO.key == SUBGRUPO_SOBREUSO
    assert DEPENDIENTE_SOBREUSO.eje == _PASIVA


@pytest.mark.parametrize(
    ("appropriation", "subgrupo_key", "esperado"),
    [
        (_PASIVA, "dependiente_sobreuso", True),
        # Delegación real: sigue siendo pasiva.
        (_PASIVA, "dependiente_delegador", False),
        # Clasificación vieja sin subgrupo: igual que hoy.
        (_PASIVA, None, False),
        # Revisión humana cambió la etiqueta: manda la revisión.
        (_REFLEXIVA, "dependiente_sobreuso", False),
        (None, "dependiente_sobreuso", False),
    ],
)
def test_es_pasiva_por_sobreuso(
    appropriation: str | None, subgrupo_key: str | None, esperado: bool
) -> None:
    assert es_pasiva_por_sobreuso(appropriation, subgrupo_key) is esperado


@pytest.mark.parametrize(
    ("features", "esperado"),
    [
        ({"subgrupo": {"key": "dependiente_sobreuso"}}, "dependiente_sobreuso"),
        ({}, None),
        (None, None),
        ({"subgrupo": None}, None),
        ({"subgrupo": {"key": 3}}, None),
        ("no-es-dict", None),
    ],
)
def test_subgrupo_key_de_es_defensivo(features: object, esperado: str | None) -> None:
    assert subgrupo_key_de(features) == esperado


def test_ordinal_progreso() -> None:
    assert ordinal_progreso(_PASIVA, "dependiente_sobreuso") is None
    assert ordinal_progreso(_PASIVA, "dependiente_delegador") == 0
    assert ordinal_progreso(_PASIVA) == 0
    assert ordinal_progreso("apropiacion_superficial", None) == 1
    assert ordinal_progreso(_REFLEXIVA, "dependiente_sobreuso") == 2
    assert ordinal_progreso("autonomo") is None
    assert ordinal_progreso("sin_clasificar") is None
    assert ordinal_progreso(None) is None
    # Los valores de la escala no cambian.
    assert APPROPRIATION_ORDINAL == {
        "delegacion_pasiva": 0,
        "apropiacion_superficial": 1,
        "apropiacion_reflexiva": 2,
    }


# ── Trayectoria (progresión de cohorte) ───────────────────────────────


def test_tramo_de_sobreuso_no_hace_empeorar() -> None:
    """Escenario del spec: reflexiva, reflexiva, sobreuso, sobreuso, reflexiva."""
    t = StudentTrajectory(
        student_pseudonym="s",
        points=[
            _cp(0, _REFLEXIVA),
            _cp(1, _REFLEXIVA),
            _cp(2, _PASIVA, "dependiente_sobreuso"),
            _cp(3, _PASIVA, "dependiente_sobreuso"),
            _cp(4, _REFLEXIVA),
        ],
    )
    assert t.tercile_means() == (2.0, 2.0, 2.0)
    assert t.progression_label() == "estable"
    # El episodio sigue en la lista de puntos.
    assert t.n_episodes == 5


def test_delegacion_real_sigue_contando() -> None:
    t = StudentTrajectory(
        student_pseudonym="s",
        points=[
            _cp(0, _REFLEXIVA),
            _cp(1, _REFLEXIVA),
            _cp(2, _PASIVA, "dependiente_delegador"),
            _cp(3, _PASIVA, "dependiente_delegador"),
        ],
    )
    assert t.progression_label() == "empeorando"


def test_max_appropriation_ignora_sobreuso() -> None:
    solo_sobreuso = StudentTrajectory(
        student_pseudonym="s",
        points=[_cp(i, _PASIVA, "dependiente_sobreuso") for i in range(3)],
    )
    assert solo_sobreuso.max_appropriation_reached() is None
    assert solo_sobreuso.progression_label() == "insuficiente"


class _DS:
    def __init__(self, grouped: dict[str, list[dict]]) -> None:
        self.grouped = grouped

    async def list_classifications_grouped_by_student(self, comision_id: UUID):
        return self.grouped


async def test_build_trajectories_lee_subgrupo_key_y_tolera_su_ausencia() -> None:
    ds = _DS(
        {
            "s": [
                {
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-09-01T10:00:00Z",
                    "appropriation": _PASIVA,
                    "subgrupo_key": "dependiente_sobreuso",
                },
                {
                    # Data source viejo, sin la clave.
                    "episode_id": str(uuid4()),
                    "classified_at": "2026-09-02T10:00:00Z",
                    "appropriation": _PASIVA,
                },
            ]
        }
    )
    [t] = await build_trajectories(ds, uuid4())
    assert [p.subgrupo_key for p in t.points] == ["dependiente_sobreuso", None]


# ── Pendientes longitudinales (trayectoria del alumno, cuartiles, alertas) ──


def test_pendiente_por_template_excluye_sobreuso() -> None:
    tid = uuid4()
    items = [
        _cls(0, _REFLEXIVA, template_id=tid),
        _cls(1, _PASIVA, "dependiente_sobreuso", template_id=tid),
        _cls(2, _REFLEXIVA, template_id=tid),
        _cls(3, _REFLEXIVA, template_id=tid),
    ]
    [entry] = compute_evolution_per_template(items)
    assert entry["scores_ordinal"] == [2, 2, 2]
    assert entry["slope"] == 0.0


def test_pendiente_por_unidad_y_general_excluyen_sobreuso() -> None:
    items = [
        _cls(0, _REFLEXIVA),
        _cls(1, _PASIVA, "dependiente_sobreuso"),
        _cls(2, _PASIVA, "dependiente_delegador"),
        _cls(3, _REFLEXIVA),
    ]
    general = compute_evolution_general(items)
    assert general["scores_ordinal"] == [2, 0, 2]
    [unidad] = compute_evolution_per_unidad(items)
    assert unidad["scores_ordinal"] == [2, 0, 2]
