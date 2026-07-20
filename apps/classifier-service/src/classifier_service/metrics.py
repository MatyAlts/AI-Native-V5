"""Métricas custom de classifier-service emitidas via OTel SDK.

Cardinality rule recap: `student_pseudonym`/`episode_id` PROHIBIDOS como
labels — las quartiles per-student viven en analytics-service endpoints, NO
en métricas Prometheus.

Para classifier las labels permitidas son: `appropriation` (3 valores enum, alias
de `n_level` para retro-compatibilidad — los 3 niveles son `delegacion_pasiva`,
`apropiacion_superficial`, `apropiacion_reflexiva`), `classifier_config_hash`
(reproducibilidad — target: 1 valor único en el piloto), `cohort` (alias de
comision_id, ~30 valores), y `template_id` (cuando se hookee, capped a ≤ 50).
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter("classifier-service")

# Counter de clasificaciones — el contador clave de los paneles del dashboard 5
# (n_level distribution + reproducibility config_hash count).
classifier_classifications_total = _meter.create_counter(
    "classifier_classifications_total",
    description="Clasificaciones N4 persistidas (append-only, ADR-010).",
    unit="1",
)

# Gauge del CCD orphan ratio agregado por cohorte (RN-130). Refleja la
# "ortogonalidad código-discurso" — cuanto más alto, más eventos de código
# huérfanos sin discurso explicativo del estudiante.
classifier_ccd_orphan_ratio = _meter.create_up_down_counter(
    "classifier_ccd_orphan_ratio",
    description="Promedio del CCD orphan ratio per-clasificación, etiquetado por cohorte.",
    unit="1",
)

# Histograma del slope CII (ordinal, RN-130). Distribución cardinal sobre
# datos ordinales — operacionalización conservadora declarada en ADR-018.
classifier_cii_evolution_slope = _meter.create_histogram(
    "classifier_cii_evolution_slope",
    description="Slope del CII evolution por clasificación (cardinal sobre ordinal).",
    unit="1",
)


__all__ = [
    "classifier_ccd_orphan_ratio",
    "classifier_cii_evolution_slope",
    "classifier_classifications_total",
]
