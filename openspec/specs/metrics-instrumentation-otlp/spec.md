# metrics-instrumentation-otlp

## Purpose

Capability that owns la capa mínima de emisión de métricas OTLP en el piloto:
`MeterProvider` + `OTLPMetricExporter` configurados en
`packages/observability::setup_observability()`, instrumentando exclusivamente
las métricas que aparecen en los 5 dashboards Grafana provisionados (capability
`observability-dashboards`).

Decisión arquitectónica clave: **NO incluye `prometheus_client` ni endpoints
`/metrics` per-service**. Todas las métricas viajan por OTLP push gRPC al OTel
Collector ya wireado en `infrastructure/observability/otel-collector-config.yaml`,
que las exporta a Prometheus en su endpoint `:8889`.

Cada servicio instrumentado tiene su propio `apps/<svc>/src/<svc>/metrics.py`
como single source of truth — los call sites importan los instruments y llaman
`.add()`/`.record()` sin tocar el wiring del MeterProvider.

## Requirements

### Requirement: Setup_metrics helper en packages/observability

`packages/observability/src/platform_observability/__init__.py` SHALL exportar una función `setup_metrics(service_name, otel_endpoint)` que configura un `MeterProvider` global con `OTLPMetricExporter(insecure=True, endpoint=otel_endpoint)` apuntando al OTel Collector ya wireado (default `otel-collector:4317`).

La función SHALL exportar también `get_meter(name)` paralelo a `get_tracer(name)` para que cada servicio obtenga un meter scoped a su nombre.

`setup_observability()` SHALL llamar internamente a `_setup_metrics()` cuando `otel_enabled=True`, y `FastAPIInstrumentor.instrument_app(app, meter_provider=meter_provider)` (además del setup de tracer ya existente) para activar la auto-instrumentación de métricas HTTP. Esto permite que los 12 servicios obtengan métricas SIN tocar sus wrappers `apps/<svc>/observability.py`.

#### Scenario: setup_metrics inicializa MeterProvider correctamente

- **WHEN** un servicio llama `setup_metrics("ctr-service", "otel-collector:4317")` (o invoca `setup_observability()` que ya lo llama internamente)
- **THEN** las llamadas subsiguientes a `get_meter("ctr-service.events")` devuelven un Meter válido cuyas métricas se exportan al OTel Collector via OTLP gRPC

#### Scenario: Auto-instrumentación HTTP activa

- **WHEN** un servicio con `setup_observability()` activo recibe un request HTTP
- **THEN** las métricas HTTP auto-instrumentadas (nombres exactos según versión de `opentelemetry-instrumentation-fastapi`, ej. `http_server_requests_total` o `http_server_request_duration_*`) SHALL incrementarse y ser visibles en el endpoint Prometheus exporter del Collector

### Requirement: NO prometheus_client and NO per-service /metrics endpoint

Ningún servicio del piloto SHALL agregar la dependencia `prometheus_client` ni exponer un endpoint `/metrics` propio. Todas las métricas SHALL viajar por OTLP push al Collector ya wireado.

Esto preserva la regla "todo va por el api-gateway" (no se expone `/metrics` a frontends ni operadores externos), reduce superficie de fallo (un solo path: OTel Collector), y mantiene consistencia con el patrón de tracing actual.

#### Scenario: Servicios no exponen /metrics

- **WHEN** se hace `curl http://127.0.0.1:8007/metrics` (ctr-service) o cualquier puerto de servicio Python del piloto
- **THEN** el endpoint NO SHALL existir (404 Not Found), excepto que sea el endpoint del Prometheus exporter del OTel Collector (puerto 8889)

#### Scenario: Métricas visibles en el endpoint del Collector

- **WHEN** un servicio instrumentado emite métricas y se hace `curl http://localhost:8889/metrics`
- **THEN** las métricas custom (ej. `ctr_events_total`) SHALL aparecer en el output con sus labels permitidas

### Requirement: CTR-service SHALL emit metrics for events, integrity, attestations

`apps/ctr-service/` SHALL emitir las siguientes métricas custom via OTel Metrics SDK (declaradas en `apps/ctr-service/src/ctr_service/metrics.py`):

- `ctr_events_total` (Counter) — labels: `tenant_id`, `event_type`, `partition` (0-7).
- `ctr_episodes_integrity_compromised_total` (Counter) — labels: `tenant_id`. Target estricto: 0.
- `ctr_self_hash_compute_seconds` (Histogram) — buckets ajustados a expected p99 < 50ms.
- `ctr_episode_duration_seconds` (Histogram) — labels: `tenant_id`, `comision_id`. Call site pendiente — instrument declarado.
- `ctr_worker_xpending_count` (UpDownCounter) — labels: `partition` (0-7). Background poll cada 30s en partition_worker.
- `ctr_attestations_emitted_total` (Counter) y `ctr_attestations_pending_count` (UpDownCounter) — Ed25519 attestations (RN-128).

#### Scenario: Evento CTR incrementa Counter

- **WHEN** ctr-service procesa un `EpisodioAbierto` event
- **THEN** `ctr_events_total{tenant_id, event_type="episodio_abierto", partition}` SHALL incrementarse en 1

#### Scenario: integrity_compromised se mantiene en 0 bajo flujo normal

- **WHEN** un episodio se cierra normalmente sin tampering
- **THEN** `ctr_episodes_integrity_compromised_total` SHALL permanecer en 0

### Requirement: AI-gateway SHALL emit metrics for tokens, budget, latency, fallback, cache

`apps/ai-gateway/` SHALL emitir las siguientes métricas custom (declaradas en `apps/ai-gateway/src/ai_gateway/metrics.py`):

- `ai_gateway_tokens_total` (Counter) — labels: `provider`, `kind` (`input|output`), `tenant_id`.
- `ai_gateway_budget_remaining_usd` (UpDownCounter) — labels: `tenant_id`.
- `ai_gateway_request_duration_seconds` (Histogram) — labels: `provider`.
- `ai_gateway_fallback_total` (Counter) — labels: `reason`.
- `ai_gateway_cache_hits_total` (Counter) y `ai_gateway_requests_total` (Counter) para cómputo de cache hit rate.

Las métricas SHALL contar correctamente aún con `LLM_PROVIDER=mock` (declarado como dato del piloto en el dashboard).

#### Scenario: Request al mock provider incrementa tokens

- **WHEN** el ai-gateway proxea una request al mock provider con prompt + response
- **THEN** `ai_gateway_tokens_total{provider="mock", kind="input"}` y `..."output"` SHALL incrementarse con el conteo de tokens del mock

### Requirement: Tutor-service SHALL emit response duration and active sessions

`apps/tutor-service/` SHALL emitir (declaradas en `apps/tutor-service/src/tutor_service/metrics.py`):

- `tutor_response_duration_seconds` (Histogram) — desde inicio del prompt hasta SSE complete (medido en `interact()`).
- `tutor_active_sessions_count` (UpDownCounter) — sesiones Redis activas. `+1` en `open_episode`, `-1` en `close_episode` y `record_episodio_abandonado`.

NO se necesita emitir series por `event_type` desde tutor-service: esas viajan via `ctr_events_total{event_type=...}`.

#### Scenario: SSE completion mide latency

- **WHEN** un episodio recibe un prompt y el tutor responde via SSE
- **THEN** `tutor_response_duration_seconds_bucket` SHALL incrementarse con el delta de tiempo desde request inicial hasta SSE done

### Requirement: Classifier-service SHALL emit classifications and coherence metrics

`apps/classifier-service/` SHALL emitir (declaradas en `apps/classifier-service/src/classifier_service/metrics.py`):

- `classifier_classifications_total` (Counter) — labels: `tenant_id`, `appropriation` (alias N4: delegacion_pasiva | apropiacion_superficial | apropiacion_reflexiva), `classifier_config_hash`, `cohort`. **`student_pseudonym` PROHIBIDO** como label. **`template_id` queda como TODO** — requiere lookup `Episode → TareaPractica.template_id` no disponible sin un join extra.
- `classifier_ccd_orphan_ratio` (UpDownCounter) — labels: `cohort`.
- `classifier_cii_evolution_slope` (Histogram).

#### Scenario: Clasificación incrementa Counter por appropriation

- **WHEN** classifier-service procesa una clasificación con `appropriation="apropiacion_reflexiva"`
- **THEN** `classifier_classifications_total{appropriation="apropiacion_reflexiva", classifier_config_hash="...", cohort="..."}` SHALL incrementarse en 1

### Requirement: κ rolling SHALL be pushed by analytics-service via OTel SDK

`apps/analytics-service/` SHALL emitir los gauges (declarados en `apps/analytics-service/src/analytics_service/metrics.py`):

- `classifier_kappa_rolling{window="7d", cohort}` — actualizado por el endpoint `POST /api/v1/analytics/kappa` cuando el request trae el campo opcional nuevo `cohort_id`.
- `classifier_kappa_rolling_last_update_unix_seconds{cohort}` — segundo gauge updated en sync con el anterior, para que el panel del dashboard 5 muestre `time() - kappa_rolling_last_update_unix_seconds` como "frescura del dato".

NO se introduce `Pushgateway` separado. Las métricas viajan por OTLP al Collector como cualquier otra.

#### Scenario: Endpoint kappa actualiza gauge

- **WHEN** se llama `POST /api/v1/analytics/kappa` con `cohort_id` y un batch que computa κ=0.72
- **THEN** `classifier_kappa_rolling{window="7d", cohort=...}` SHALL valer 0.72 y `classifier_kappa_rolling_last_update_unix_seconds{cohort=...}` SHALL valer el unix timestamp del momento del compute

### Requirement: Cardinality limits — student_pseudonym FORBIDDEN as label

Las siguientes labels SHALL JAMÁS aparecer en ninguna métrica Prometheus emitida por servicios del piloto:

- `student_pseudonym`
- `episode_id`
- `user_id`
- `prompt_id`
- Cualquier UUID per-instancia (CTR self_hash, classification_id, attestation_id, etc.).

Las labels permitidas (lista cerrada): `tenant_id`, `service_name`, `event_type`, `partition` (0-7), `provider`, `kind`, `n_level` (N1-N4), `cohort` (alias de comision_id, max ~30 valores), `prompt_kind` (5 enum values), `template_id` (cardinalidad ≤ 50 declarada cuando se hookee).

#### Scenario: Code review detecta label prohibido

- **WHEN** un PR introduce una métrica con label `student_pseudonym`
- **THEN** el reviewer SHALL bloquear el PR con referencia a este requirement; alternativamente la métrica se mueve al plano API (analytics-service endpoint) en vez de Prometheus
