"""Tests del service de agregación de clasificaciones.

Usa un session fake que intercepta los execute() y devuelve los rows
deseados. Así verificamos la lógica de agregación (pesos, buckets,
timeseries) sin necesidad de DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from classifier_service.services.aggregation import aggregate_by_comision


@dataclass
class FakeRow:
    data: dict

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def keys(self):
        return self.data.keys()

    def __iter__(self):
        return iter(self.data)


@dataclass
class FakeResult:
    rows: list[dict]

    def mappings(self):
        return [FakeRow(r) for r in self.rows]


@dataclass
class FakeSession:
    """Devuelve resultados pre-configurados en orden de llamada."""

    canned: list[list[dict]] = field(default_factory=list)
    _call = 0

    async def execute(self, stmt):
        if self._call >= len(self.canned):
            return FakeResult([])
        result = FakeResult(self.canned[self._call])
        self._call += 1
        return result


async def test_agregacion_vacia_devuelve_ceros() -> None:
    session = FakeSession(canned=[[], []])  # distribución vacía, timeseries vacío
    stats = await aggregate_by_comision(session, uuid4(), period_days=7)

    assert stats.total_episodes == 0
    assert stats.distribution.delegacion_pasiva == 0
    assert stats.distribution.apropiacion_superficial == 0
    assert stats.distribution.apropiacion_reflexiva == 0
    assert stats.avg_ct_summary is None
    assert stats.timeseries == []


async def test_agregacion_cuenta_por_tipo() -> None:
    session = FakeSession(
        canned=[
            # Distribución (1ª query)
            [
                {
                    "appropriation": "delegacion_pasiva",
                    "n": 3,
                    "avg_ct": 0.2,
                    "avg_ccd_mean": 0.1,
                    "avg_ccd_orphan": 0.8,
                    "avg_cii_stab": 0.3,
                    "avg_cii_evo": 0.3,
                },
                {
                    "appropriation": "apropiacion_superficial",
                    "n": 5,
                    "avg_ct": 0.5,
                    "avg_ccd_mean": 0.5,
                    "avg_ccd_orphan": 0.3,
                    "avg_cii_stab": 0.4,
                    "avg_cii_evo": 0.5,
                },
                {
                    "appropriation": "apropiacion_reflexiva",
                    "n": 2,
                    "avg_ct": 0.8,
                    "avg_ccd_mean": 0.8,
                    "avg_ccd_orphan": 0.1,
                    "avg_cii_stab": 0.7,
                    "avg_cii_evo": 0.7,
                },
            ],
            # Timeseries (2ª query, vacío para simplificar)
            [],
        ]
    )

    stats = await aggregate_by_comision(session, uuid4(), period_days=30)

    assert stats.total_episodes == 10
    assert stats.distribution.delegacion_pasiva == 3
    assert stats.distribution.apropiacion_superficial == 5
    assert stats.distribution.apropiacion_reflexiva == 2


async def test_avg_es_ponderado_por_n() -> None:
    """Promedio debe ser ponderado por cantidad de episodios en cada bucket."""
    session = FakeSession(
        canned=[
            [
                {
                    "appropriation": "delegacion_pasiva",
                    "n": 10,
                    "avg_ct": 0.2,
                    "avg_ccd_mean": 0.1,
                    "avg_ccd_orphan": 0.8,
                    "avg_cii_stab": 0.3,
                    "avg_cii_evo": 0.3,
                },
                {
                    "appropriation": "apropiacion_reflexiva",
                    "n": 10,
                    "avg_ct": 0.8,
                    "avg_ccd_mean": 0.8,
                    "avg_ccd_orphan": 0.1,
                    "avg_cii_stab": 0.7,
                    "avg_cii_evo": 0.7,
                },
            ],
            [],
        ]
    )

    stats = await aggregate_by_comision(session, uuid4(), period_days=30)

    # 10 * 0.2 + 10 * 0.8 = 10; dividido por 20 = 0.5
    assert stats.avg_ct_summary == pytest.approx(0.5)
    # Orphan: 10*0.8 + 10*0.1 = 9; / 20 = 0.45
    assert stats.avg_ccd_orphan_ratio == pytest.approx(0.45)


async def test_timeseries_agrupa_por_dia() -> None:
    d1 = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    d2 = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)

    session = FakeSession(
        canned=[
            [],  # distribución vacía para enfocar en timeseries
            [
                {"day": d1, "appropriation": "apropiacion_reflexiva", "n": 3},
                {"day": d1, "appropriation": "apropiacion_superficial", "n": 2},
                {"day": d2, "appropriation": "delegacion_pasiva", "n": 1},
                {"day": d2, "appropriation": "apropiacion_reflexiva", "n": 4},
            ],
        ]
    )

    stats = await aggregate_by_comision(session, uuid4(), period_days=7)

    assert len(stats.timeseries) == 2
    assert stats.timeseries[0].date == "2026-10-01"
    assert stats.timeseries[0].counts.apropiacion_reflexiva == 3
    assert stats.timeseries[0].counts.apropiacion_superficial == 2
    assert stats.timeseries[0].counts.delegacion_pasiva == 0

    assert stats.timeseries[1].date == "2026-10-02"
    assert stats.timeseries[1].counts.delegacion_pasiva == 1
    assert stats.timeseries[1].counts.apropiacion_reflexiva == 4
