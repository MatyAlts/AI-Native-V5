"""Agregación de clasificaciones por comisión para vista docente."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.models import Classification


@dataclass
class AppropriationCounts:
    delegacion_pasiva: int = 0
    apropiacion_superficial: int = 0
    apropiacion_reflexiva: int = 0

    @property
    def total(self) -> int:
        return self.delegacion_pasiva + self.apropiacion_superficial + self.apropiacion_reflexiva


@dataclass
class DailyCounts:
    date: str  # ISO "YYYY-MM-DD"
    counts: AppropriationCounts = field(default_factory=AppropriationCounts)


@dataclass
class AggregatedStats:
    comision_id: UUID
    period_days: int
    total_episodes: int
    distribution: AppropriationCounts
    avg_ct_summary: float | None
    avg_ccd_mean: float | None
    avg_ccd_orphan_ratio: float | None
    avg_cii_stability: float | None
    avg_cii_evolution: float | None
    timeseries: list[DailyCounts]


async def aggregate_by_comision(
    session: AsyncSession,
    comision_id: UUID,
    period_days: int = 30,
) -> AggregatedStats:
    """Agrega clasificaciones `is_current=true` de una comisión.

    Usa los promedios DE las fichas actuales (no re-clasificaciones).
    """
    since = datetime.now(UTC) - timedelta(days=period_days)

    # Totales y averages en una query
    result = await session.execute(
        select(
            Classification.appropriation,
            func.count(Classification.id).label("n"),
            func.avg(Classification.ct_summary).label("avg_ct"),
            func.avg(Classification.ccd_mean).label("avg_ccd_mean"),
            func.avg(Classification.ccd_orphan_ratio).label("avg_ccd_orphan"),
            func.avg(Classification.cii_stability).label("avg_cii_stab"),
            func.avg(Classification.cii_evolution).label("avg_cii_evo"),
        )
        .where(
            Classification.comision_id == comision_id,
            Classification.is_current.is_(True),
            Classification.classified_at >= since,
        )
        .group_by(Classification.appropriation)
    )

    dist = AppropriationCounts()
    all_avgs: list[dict] = []
    for row in result.mappings():
        appropriation = row["appropriation"]
        n = int(row["n"])
        if appropriation == "delegacion_pasiva":
            dist.delegacion_pasiva = n
        elif appropriation == "apropiacion_superficial":
            dist.apropiacion_superficial = n
        elif appropriation == "apropiacion_reflexiva":
            dist.apropiacion_reflexiva = n
        all_avgs.append(dict(row))

    # Promedio global (ponderado por n por appropriation)
    total_n = sum(int(a["n"]) for a in all_avgs)

    def weighted_avg(field_name: str) -> float | None:
        parts = [
            (float(a[field_name]), int(a["n"])) for a in all_avgs if a.get(field_name) is not None
        ]
        if not parts:
            return None
        total_w = sum(n for _, n in parts)
        if total_w == 0:
            return None
        return sum(v * n for v, n in parts) / total_w

    # Timeseries: por día, count por appropriation
    ts_result = await session.execute(
        select(
            func.date_trunc("day", Classification.classified_at).label("day"),
            Classification.appropriation,
            func.count(Classification.id).label("n"),
        )
        .where(
            Classification.comision_id == comision_id,
            Classification.is_current.is_(True),
            Classification.classified_at >= since,
        )
        .group_by("day", Classification.appropriation)
        .order_by("day")
    )

    ts_map: dict[str, AppropriationCounts] = {}
    for row in ts_result.mappings():
        day = row["day"].date().isoformat()
        if day not in ts_map:
            ts_map[day] = AppropriationCounts()
        counts = ts_map[day]
        n = int(row["n"])
        if row["appropriation"] == "delegacion_pasiva":
            counts.delegacion_pasiva = n
        elif row["appropriation"] == "apropiacion_superficial":
            counts.apropiacion_superficial = n
        elif row["appropriation"] == "apropiacion_reflexiva":
            counts.apropiacion_reflexiva = n

    timeseries = [DailyCounts(date=day, counts=counts) for day, counts in sorted(ts_map.items())]

    return AggregatedStats(
        comision_id=comision_id,
        period_days=period_days,
        total_episodes=total_n,
        distribution=dist,
        avg_ct_summary=weighted_avg("avg_ct"),
        avg_ccd_mean=weighted_avg("avg_ccd_mean"),
        avg_ccd_orphan_ratio=weighted_avg("avg_ccd_orphan"),
        avg_cii_stability=weighted_avg("avg_cii_stab"),
        avg_cii_evolution=weighted_avg("avg_cii_evo"),
        timeseries=timeseries,
    )
