"""Análisis longitudinal de la progresión N4 por estudiante.

La hipótesis central de la tesis es que, a lo largo del cuatrimestre,
los estudiantes deberían mover su apropiación desde "delegación pasiva"
o "apropiación superficial" hacia "apropiación reflexiva". Este módulo
provee las métricas para verificarlo empíricamente.

Dos niveles de análisis:

  1. **Por estudiante**: serie temporal de clasificaciones ordenadas por
     `classified_at`. Una trayectoria es "mejorando" si el último tercio
     de episodios tiene mayor fracción de apropiacion_reflexiva que el
     primer tercio.

  2. **Por cohorte**: agregación de las trayectorias de todos los
     estudiantes de una comisión, con un indicador de "net progression"
     (% de estudiantes mejorando − % empeorando).

El análisis se hace a partir del mismo data_source que ya consume el
AcademicExporter (desacoplado de la DB, testeable).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

AppropriationValue = Literal[
    "delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva"
]

# Ordinal scores para comparar progresión (mayor = mejor)
APPROPRIATION_ORDINAL: dict[str, int] = {
    "delegacion_pasiva": 0,
    "apropiacion_superficial": 1,
    "apropiacion_reflexiva": 2,
}


@dataclass
class ClassificationPoint:
    """Un punto en la serie temporal de un estudiante."""

    episode_id: UUID
    classified_at: datetime
    appropriation: str
    # Opcional: coherencias individuales para análisis más fino
    ct_summary: float | None = None
    ccd_mean: float | None = None
    ccd_orphan_ratio: float | None = None
    cii_stability: float | None = None
    cii_evolution: float | None = None


@dataclass
class StudentTrajectory:
    """Trayectoria longitudinal de un estudiante."""

    student_pseudonym: str  # UUID del estudiante (string). Solo se anonimiza en `academic_export`.
    points: list[ClassificationPoint] = field(default_factory=list)

    @property
    def n_episodes(self) -> int:
        return len(self.points)

    @property
    def first_classification(self) -> str | None:
        return self.points[0].appropriation if self.points else None

    @property
    def last_classification(self) -> str | None:
        return self.points[-1].appropriation if self.points else None

    def tercile_means(self) -> tuple[float, float, float] | None:
        """Devuelve (media_primer_tercio, medio, último_tercio) en escala ordinal.

        Con al menos 3 episodios; si hay menos, devuelve None.
        """
        if self.n_episodes < 3:
            return None
        scores = [APPROPRIATION_ORDINAL[p.appropriation] for p in self.points]
        n = len(scores)
        size = n // 3
        first = scores[:size]
        last = scores[-size:]
        # Tercio medio: puede solaparse si n no divide en 3
        mid_start = size
        mid_end = n - size
        mid = scores[mid_start:mid_end] if mid_end > mid_start else scores[size : size + 1]
        return (
            sum(first) / len(first),
            sum(mid) / len(mid),
            sum(last) / len(last),
        )

    def progression_label(self) -> str:
        """Clasifica la trayectoria global:
        - 'mejorando'   si el último tercio es mayor que el primero
        - 'estable'     si son iguales
        - 'empeorando'  si baja
        - 'insuficiente' si hay menos de 3 episodios
        """
        terciles = self.tercile_means()
        if terciles is None:
            return "insuficiente"
        first, _mid, last = terciles
        # Margen de 0.25 para tolerar ruido dentro de una misma categoría
        if last - first > 0.25:
            return "mejorando"
        if first - last > 0.25:
            return "empeorando"
        return "estable"

    def max_appropriation_reached(self) -> str | None:
        """La clasificación máxima alcanzada en algún punto."""
        if not self.points:
            return None
        max_ordinal = max(APPROPRIATION_ORDINAL[p.appropriation] for p in self.points)
        for a, o in APPROPRIATION_ORDINAL.items():
            if o == max_ordinal:
                return a
        return None


@dataclass
class CohortProgression:
    """Resumen de progresiones en una cohorte."""

    comision_id: UUID
    n_students: int
    n_students_with_enough_data: int  # >= 3 episodios
    mejorando: int = 0
    estable: int = 0
    empeorando: int = 0
    insuficiente: int = 0

    @property
    def net_progression_ratio(self) -> float:
        """(mejorando - empeorando) / students_with_enough_data.

        Rango [-1, 1]. Positivo indica cohorte mejorando netamente.
        """
        if self.n_students_with_enough_data == 0:
            return 0.0
        return (self.mejorando - self.empeorando) / self.n_students_with_enough_data


class _DataSource:
    """Interface mínima."""

    async def list_classifications_grouped_by_student(
        self,
        comision_id: UUID,
    ) -> dict[str, list[dict]]:
        """Devuelve {student_pseudonym: [classification_dict, ...]} ordenados por classified_at."""
        raise NotImplementedError


async def build_trajectories(
    data_source: _DataSource,
    comision_id: UUID,
) -> list[StudentTrajectory]:
    """Construye trayectorias de todos los estudiantes de una comisión."""
    grouped = await data_source.list_classifications_grouped_by_student(comision_id)
    trajectories: list[StudentTrajectory] = []

    for student_pseudonym, raw_list in grouped.items():
        points: list[ClassificationPoint] = []
        for row in raw_list:
            points.append(
                ClassificationPoint(
                    episode_id=UUID(row["episode_id"])
                    if isinstance(row["episode_id"], str)
                    else row["episode_id"],
                    classified_at=(
                        row["classified_at"]
                        if isinstance(row["classified_at"], datetime)
                        else datetime.fromisoformat(row["classified_at"].replace("Z", "+00:00"))
                    ),
                    appropriation=row["appropriation"],
                    ct_summary=row.get("ct_summary"),
                    ccd_mean=row.get("ccd_mean"),
                    ccd_orphan_ratio=row.get("ccd_orphan_ratio"),
                    cii_stability=row.get("cii_stability"),
                    cii_evolution=row.get("cii_evolution"),
                )
            )
        # Sort defensivo por si el data source no garantiza orden
        points.sort(key=lambda p: p.classified_at)
        trajectories.append(StudentTrajectory(student_pseudonym=student_pseudonym, points=points))

    return trajectories


def summarize_cohort(comision_id: UUID, trajectories: list[StudentTrajectory]) -> CohortProgression:
    """Agrega las trayectorias en un resumen por cohorte."""
    summary = CohortProgression(
        comision_id=comision_id,
        n_students=len(trajectories),
        n_students_with_enough_data=sum(1 for t in trajectories if t.n_episodes >= 3),
    )
    for t in trajectories:
        label = t.progression_label()
        if label == "mejorando":
            summary.mejorando += 1
        elif label == "empeorando":
            summary.empeorando += 1
        elif label == "estable":
            summary.estable += 1
        else:
            summary.insuficiente += 1
    return summary


__all__ = [
    "APPROPRIATION_ORDINAL",
    "ClassificationPoint",
    "CohortProgression",
    "StudentTrajectory",
    "build_trajectories",
    "summarize_cohort",
]
