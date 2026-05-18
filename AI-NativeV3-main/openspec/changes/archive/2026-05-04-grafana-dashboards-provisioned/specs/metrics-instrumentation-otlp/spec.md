## ADDED Requirements

### Requirement: Setup_metrics helper en packages/observability

`packages/observability/src/platform_observability/__init__.py` SHALL exportar una función `setup_metrics(service_name, otel_endpoint)` que configura un `MeterProvider` global con `OTLPMetricExporter(insecure=True, endpoint=otel_endpoint)` apuntando al OTel Collector ya wireado (default `otel-collector:4317`).

La función SHALL exportar también `get_meter(name)` paralelo a `get_tracer(name)` para que cada servicio obtenga un meter scoped a su nombre.

`setup_metrics()` SHALL llamar a `FastAPIInstrumentor.instrument_app(app, meter_provider=meter_provider)` (además del setup de tracer ya existente) para activar la auto-instrumentación de métricas HTTP (`http_server_requests_total`, `http_server_duration_seconds_bucket`).

#### Scenario: setup_metrics inicializa MeterProvider correctamente

- **WHEN** un servicio llama `setup_metrics("ctr-service", "otel-collector:4317")` en su `lifespan`
- **THEN** las llamadas subsiguientes a `get_meter("ctr-service.events")` devuelven un Meter válido cuyas métricas se exportan al OTel Collector via OTLP gRPC

#### Scenario: Auto-instrumentación HTTP activa

- **WHEN** un servicio con `setup_metrics()` activo recibe un request HTTP a `/api/v1/foo`
- **THEN** las métricas `http_server_requests_total{service_name, http_method, http_status_code, http_route}` y `http_server_duration_seconds_bucket{...}` SHALL incrementarse y ser visibles en el endpoint Prometheus exporter del Collector

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

`apps/ctr-service/` SHALL emitir las siguientes métricas custom via OTel Metrics SDK:

- `ctr_events_total` (Counter) — labels: `tenant_id`, `event_type`, `partition` (0-7).
- `ctr_episodes_integrity_compromised_total` (Counter) — labels: `tenant_id`. Target estricto: 0.
- `ctr_self_hash_compute_seconds` (Histogram) — buckets ajustados a expected p99 < 50ms.
- `ctr_episode_duration_seconds` (Histogram) — labels: `tenant_id`, `comision_id`.
- `ctr_worker_xpending_count` (Gauge) — labels: `partition` (0-7). Reflects Redis Stream lag.
- `ctr_attestations_emitted_total` (Counter) y `ctr_attestations_pending_count` (Gauge) — Ed25519 attestations (RN-128).

#### Scenario: Evento CTR incrementa Counter

- **WHEN** ctr-service procesa un `EpisodioAbierto` event para `tenant=aaaa..., partition=3`
- **THEN** `ctr_events_total{tenant_id="aaaa...", event_type="episodio_abierto", partition="3"}` SHALL incrementarse en 1

#### Scenario: integrity_compromised se mantiene en 0 bajo flujo normal

- **WHEN** un episodio se cierra normalmente sin tampering
- **THEN** `ctr_episodes_integrity_compromised_total` SHALL permanecer en 0

### Requirement: AI-gateway SHALL emit metrics for tokens, budget, latency, fallback, cache

`apps/ai-gateway/` SHALL emitir las siguientes métricas custom:

- `ai_gateway_tokens_total` (Counter) — labels: `provider`, `kind` (`input|output`), `tenant_id`.
- `ai_gateway_budget_remaining_usd` (Gauge) — labels: `tenant_id`.
- `ai_gateway_request_duration_seconds` (Histogram) — labels: `provider`.
- `ai_gateway_fallback_total` (Counter) — labels: `reason`.
- `ai_gateway_cache_hits_total` (Counter) y `ai_gateway_requests_total` (Counter) para cómputo de cache hit rate.

Las métricas SHALL contar correctamente aún con `LLM_PROVIDER=mock` (el mock cuenta tokens también — esto está declarado en el dashboard como dato del piloto).

#### Scenario: Request al mock provider incrementa tokens

- **WHEN** el ai-gateway proxea una request al mock provider con prompt + response
- **THEN** `ai_gateway_tokens_total{provider="mock", kind="input"}` y `..."output"` SHALL incrementarse con el conteo de tokens del mock

### Requirement: Tutor-service SHALL emit response duration and active sessions

`apps/tutor-service/` SHALL emitir:

- `tutor_response_duration_seconds` (Histogram) — desde inicio del prompt hasta SSE complete.
- `tutor_active_sessions_count` (Gauge) — sesiones Redis activas.

NO se necesita emitir series por `event_type` desde tutor-service: esas viajan via `ctr_events_total{event_type=...}` que ya etiqueta el evento.

#### Scenario: SSE completion mide latency

- **WHEN** un episodio recibe un prompt y el tutor responde via SSE
- **THEN** `tutor_response_duration_seconds_bucket` SHALL incrementarse con el delta de tiempo desde request inicial hasta SSE done

### Requirement: Classifier-service SHALL emit classifications and coherence metrics

`apps/classifier-service/` SHALL emitir:

- `classifier_classifications_total` (Counter) — labels: `n_level`, `template_id`, `classifier_config_hash`. **`student_pseudonym` PROHIBIDO** como label.
- `classifier_ccd_orphan_ratio` (Gauge) — labels: `cohort` (alias de comision_id).
- `classifier_cii_evolution_slope` (Histogram) — distribución cardinal de slopes.

`template_id` SHALL acotarse a ≤ 50 valores distintos (limit declarado para piloto-1; suficiente para ~3-5 templates por materia × ~10 materias).

#### Scenario: Clasificación incrementa Counter por n_level

- **WHEN** classifier-service procesa una clasificación con `n_level=N3, template_id=tpl-001`
- **THEN** `classifier_classifications_total{n_level="N3", template_id="tpl-001", classifier_config_hash="..."}` SHALL incrementarse en 1

### Requirement: κ rolling SHALL be pushed by analytics-service via OTel SDK

`apps/analytics-service/` SHALL emitir los gauges:

- `classifier_kappa_rolling{window="7d", cohort}` — actualizado por (a) el endpoint `POST /api/v1/analytics/kappa` cada vez que se computa κ para una cohorte, y (b) un endpoint nuevo `POST /api/v1/analytics/kappa-rolling/refresh` que itera por todas las cohortes activas y recomputa.
- `classifier_kappa_rolling_last_update_unix_seconds{cohort}` — segundo gauge updated en sync con el anterior, para que el panel del dashboard 5 muestre `time() - kappa_rolling_last_update_unix_seconds` como "frescura del dato".

NO se introduce `Pushgateway` separado. Las métricas viajan por OTLP al Collector como cualquier otra.

#### Scenario: Endpoint kappa actualiza gauge

- **WHEN** se llama `POST /api/v1/analytics/kappa` con un batch que computa κ=0.72 para cohort `bbbb-...`
- **THEN** `classifier_kappa_rolling{window="7d", cohort="bbbb-..."}` SHALL valer 0.72 y `classifier_kappa_rolling_last_update_unix_seconds{cohort="bbbb-..."}` SHALL valer el unix timestamp del momento del compute

### Requirement: Cardinality limits — student_pseudonym FORBIDDEN as label

Las siguientes labels SHALL JAMÁS aparecer en ninguna métrica Prometheus emitida por servicios del piloto:

- `student_pseudonym`
- `episode_id`
- `user_id`
- `prompt_id`
- Cualquier UUID per-instancia (CTR self_hash, classification_id, attestation_id, etc.).

Las labels permitidas (lista cerrada): `tenant_id`, `service_name`, `event_type`, `partition` (0-7), `provider`, `kind`, `n_level` (N1-N4), `cohort` (alias de comision_id, max ~30 valores), `prompt_kind` (5 enum values), `template_id` (cardinalidad ≤ 50 declarada).

#### Scenario: Code review detecta label prohibido

- **WHEN** un PR introduce una métrica con label `student_pseudonym`
- **THEN** el reviewer SHALL bloquear el PR con referencia a este requirement; alternativamente la métrica se mueve al plano API (analytics-service endpoint) en vez de Prometheus
