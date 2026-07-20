"""Métricas custom de ctr-service emitidas via OTel SDK.

Single source of truth — todas las métricas Prometheus que el CTR emite vienen
de este módulo. Los call sites importan los instruments y llaman .add()/.record()
sin tocar el wiring del MeterProvider (configurado en packages/observability via
setup_observability).

REGLA DE CARDINALIDAD: las labels permitidas son lista cerrada documentada en
openspec/specs/metrics-instrumentation-otlp/spec.md. `student_pseudonym`,
`episode_id`, `user_id`, y cualquier UUID per-instancia están PROHIBIDOS —
explotaría Prometheus + expondría correlation cross-metric (privacidad).

Para CTR las labels permitidas son: `tenant_id`, `event_type`, `partition`,
`comision_id`. NUNCA `student_pseudonym` ni `episode_id`.
"""

from __future__ import annotations

from platform_observability import get_meter

_meter = get_meter("ctr-service")

# ── Counters ──────────────────────────────────────────────────────────

# Eventos CTR escritos al stream — el contador central del piloto.
# Labels permitidas: tenant_id, event_type, partition (0-7).
ctr_events_total = _meter.create_counter(
    "ctr_events_total",
    description="Total de eventos CTR publicados al stream Redis particionado.",
    unit="1",
)

# Episodios marcados como integrity_compromised (ADR-010 / RN-039).
# Target estricto del piloto: 0. Cualquier valor > 0 dispara investigación I01.
ctr_episodes_integrity_compromised_total = _meter.create_counter(
    "ctr_episodes_integrity_compromised_total",
    description="Episodios marcados con integrity_compromised=true (cadena CTR rota).",
    unit="1",
)

# Attestations Ed25519 emitidas exitosamente al integrity-attestation-service
# (ADR-021 / RN-128). Side-channel — la attestation NO bloquea el cierre.
ctr_attestations_emitted_total = _meter.create_counter(
    "ctr_attestations_emitted_total",
    description="Attestations Ed25519 firmadas exitosamente por el servicio externo.",
    unit="1",
)

# ── Histograms ────────────────────────────────────────────────────────

# Latencia del compute SHA-256 self_hash de un evento. Expected p99 < 50ms.
ctr_self_hash_compute_seconds = _meter.create_histogram(
    "ctr_self_hash_compute_seconds",
    description="Tiempo de compute del SHA-256 self_hash de un evento CTR.",
    unit="s",
)

# Duración de un episodio (delta entre EpisodioAbierto.ts y EpisodioCerrado.ts).
# Labels: tenant_id, comision_id. NO `student_pseudonym`.
ctr_episode_duration_seconds = _meter.create_histogram(
    "ctr_episode_duration_seconds",
    description="Duración total de un episodio (open → close) en segundos.",
    unit="s",
)

# ── Gauges ────────────────────────────────────────────────────────────

# Worker lag por partición (XPENDING count del Redis Stream).
# Updated periodically por cada worker en su loop principal.
ctr_worker_xpending_count = _meter.create_up_down_counter(
    "ctr_worker_xpending_count",
    description="Cantidad de mensajes pendientes (XPENDING) en el stream por partición.",
    unit="1",
)

# Attestations pendientes de firma en el integrity-attestation-service.
# SLO: < 24h decay (ADR-021). El gauge refleja backlog actual.
ctr_attestations_pending_count = _meter.create_up_down_counter(
    "ctr_attestations_pending_count",
    description="Attestations Ed25519 pendientes de firma (backlog del servicio externo).",
    unit="1",
)


__all__ = [
    "ctr_attestations_emitted_total",
    "ctr_attestations_pending_count",
    "ctr_episode_duration_seconds",
    "ctr_episodes_integrity_compromised_total",
    "ctr_events_total",
    "ctr_self_hash_compute_seconds",
    "ctr_worker_xpending_count",
]
