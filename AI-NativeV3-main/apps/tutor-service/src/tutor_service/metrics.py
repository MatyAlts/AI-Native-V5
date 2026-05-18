"""Métricas custom de tutor-service emitidas via OTel SDK.

Single source of truth — el catálogo permitido vive en
openspec/specs/metrics-instrumentation-otlp/spec.md.

Cardinality rule recap: `student_pseudonym`/`episode_id`/`user_id` PROHIBIDOS
como labels. Las series por `event_type` viajan en `ctr_events_total` (emitido
por ctr-service), NO acá — evita duplicar.
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter("tutor-service")

# Latencia end-to-end del turno SSE: desde que llega el prompt al servicio
# hasta que se completa el último chunk del response. SLO p95 < 3s, p99 < 8s.
tutor_response_duration_seconds = _meter.create_histogram(
    "tutor_response_duration_seconds",
    description="Latencia del turno SSE del tutor (prompt → último chunk).",
    unit="s",
)

# Sesiones activas (UpDownCounter — incrementa en open_episode, decrementa en
# close_episode/abandonment). Reflects sessions Redis activas.
tutor_active_sessions_count = _meter.create_up_down_counter(
    "tutor_active_sessions_count",
    description="Sesiones de tutor activas (Redis state).",
    unit="1",
)


__all__ = [
    "tutor_active_sessions_count",
    "tutor_response_duration_seconds",
]
