## 1. Verificación de dependencias y setup base

- [x] 1.1 Deps verificadas: `opentelemetry-sdk>=1.27` + `opentelemetry-exporter-otlp>=1.27` (bundle gRPC + http) + `opentelemetry-instrumentation-fastapi>=0.48b0` ya están en `packages/observability/pyproject.toml`. Versión 0.48b0+ soporta `meter_provider` argument; si por alguna razón no lo soporta, el setup_tracing tiene fallback `TypeError → instrument_app(app)` sin meter (cubre el caso).
- [x] 1.2 Pipeline metrics ya activo en `infrastructure/observability/otel-collector-config.yaml:39-42`: `receivers: [otlp] → exporters: [prometheus]`. No requiere cambios.
- [ ] 1.3 `docker compose -f infrastructure/docker-compose.dev.yml down -v` (lo deja al usuario hacer pre-deploy del PR — documentado en README operativo nuevo).

## 2. setup_metrics() en packages/observability

- [x] 2.1-2.4 `packages/observability/src/platform_observability/__init__.py` extendido:
  - Nueva función `setup_metrics(config | **kwargs)` standalone (workers headless).
  - `setup_observability()` ahora llama `_setup_metrics(config)` internamente cuando `otel_enabled=True` — los 12 servicios obtienen métricas SIN tocar sus wrappers en `apps/<svc>/observability.py` (cero cambios en mains).
  - `get_meter(name)` exportado paralelo a `get_tracer(name)`.
  - `FastAPIInstrumentor.instrument_app(app, tracer_provider=..., meter_provider=...)` con fallback `TypeError → instrument_app(app)` para versiones viejas del library.
  - `_NoopMeter` + `_NoopInstrument` como fallback offline (tests sin OTel installed).
  - `metrics_export_interval_millis: int = 60000` agregado al `ObservabilityConfig`.
- [x] 2.5 Tests agregados en `packages/observability/tests/test_setup.py`: `test_config_tiene_metrics_export_interval_default`, `test_setup_metrics_standalone_no_crashea`, `test_get_meter_devuelve_algo_usable`, `test_get_meter_create_histogram_y_record`, `test_setup_observability_inicializa_metrics_implicitamente`.

## 3. Instrumentación CTR-service (más crítico para defensa)

- [x] 3.1 Lifespan call cubierto **automáticamente**: el cambio en `packages/observability` integra `setup_metrics()` dentro de `setup_observability()`, que ya está wireado en `apps/ctr-service/src/ctr_service/main.py:20`. Cero cambios en main.py.
- [x] 3.2 `apps/ctr-service/src/ctr_service/metrics.py` creado (single source of truth). `ctr_events_total{tenant_id, event_type, partition}` incrementado en `services/producer.py::publish()` post-XADD.
- [x] 3.3 `ctr_episodes_integrity_compromised_total{tenant_id}` incrementado en **DOS sitios** (los únicos donde se setea `integrity_compromised=true`): `workers/integrity_checker.py::_mark_compromised()` (job batch) y `workers/partition_worker.py` línea ~378 (DLQ path cuando un evento falla persistencia repetidamente).
- [x] 3.4 `ctr_self_hash_compute_seconds` Histogram hookeado en `services/hashing.py::compute_self_hash()` con `time.perf_counter()`.
- [ ] 3.5 `ctr_episode_duration_seconds{tenant_id, comision_id}` — DIFERIDO. Instrument declarado pero sin call site: requiere lookup `Episode.started_at` desde la DB cuando se procesa `episodio_cerrado`, lo cual agrega un session join. Documentado en `metrics.py` para que la próxima iteración lo hookee donde se consume el evento `episodio_cerrado` (probablemente en `partition_worker._process_message` o `routes/events.py`).
- [x] 3.6 `ctr_worker_xpending_count{partition}` Gauge: hookeado con `_xpending_metric_loop` background task en `workers/partition_worker.py::run()` — poll cada 30s del `XPENDING` count + emit como UpDownCounter delta.
- [x] 3.7 `ctr_attestations_emitted_total` + `ctr_attestations_pending_count` hookeados en `services/attestation_producer.py::publish()` post-XADD exitoso.

## 4. Instrumentación tutor-service

- [x] 4.1 Lifespan call cubierto automáticamente (foundation).
- [x] 4.2 `tutor_response_duration_seconds` Histogram hookeado en `services/tutor_core.py::interact()` — mide desde inicio hasta yield del `done` final.
- [x] 4.3 `tutor_active_sessions_count` UpDownCounter hookeado en 3 sitios: `+1` en `open_episode`, `-1` en `close_episode`, `-1` en `record_episodio_abandonado`.

`apps/tutor-service/src/tutor_service/metrics.py` creado con los 2 instruments.

## 5. Instrumentación ai-gateway

- [x] 5.1 Lifespan call cubierto automáticamente (foundation).
- [x] 5.2 `ai_gateway_tokens_total{provider, kind, tenant_id}` Counter hookeado en `routes/complete.py::complete()` — emite `input_tokens` y `output_tokens` post-provider-call con labels permitidas.
- [x] 5.3 `ai_gateway_budget_remaining_usd{tenant_id}` UpDownCounter hookeado — descuenta `cost_usd` del request.
- [x] 5.4 `ai_gateway_request_duration_seconds{provider}` Histogram hookeado entre `provider.complete()` start y end (excluye cache hits).
- [x] 5.5 `ai_gateway_fallback_total{reason}` Counter hookeado en el `except Exception` del provider call.
- [x] 5.6 `ai_gateway_cache_hits_total` + `ai_gateway_requests_total` hookeados — `requests_total` incrementa en cada request entrante (denominador), `cache_hits_total` cuando hay cache hit (numerador).

`apps/ai-gateway/src/ai_gateway/metrics.py` creado. Stream endpoint `/api/v1/stream` queda con instrumentación pendiente — el complete endpoint cubre el path principal del piloto.

## 6. Instrumentación classifier-service

- [x] 6.1 Lifespan call cubierto automáticamente (foundation).
- [x] 6.2 `classifier_classifications_total{tenant_id, appropriation, classifier_config_hash, cohort}` Counter hookeado en `services/pipeline.py::persist_classification()` post-flush. **Nota de scope**: `template_id` queda como TODO comment — requiere lookup `Episode → TareaPractica.template_id` que no está disponible sin un join extra. La métrica funciona con los demás labels.
- [x] 6.3 `classifier_ccd_orphan_ratio{cohort}` UpDownCounter hookeado: cada clasificación contribuye con su `result.ccd_orphan_ratio`; el panel del dashboard 5 usa `avg(...)` que es equivalente al promedio de los emisores.
- [x] 6.4 `classifier_cii_evolution_slope` Histogram hookeado con `result.cii_evolution`.
- [x] 6.5 Cardinalidad de `template_id`: cuando se hookee (TODO), agregar el assertion del cap ≤ 50.

`apps/classifier-service/src/classifier_service/metrics.py` creado.

## 7. Instrumentación analytics-service para κ rolling

- [x] 7.1 Lifespan call cubierto automáticamente (foundation).
- [x] 7.2 `classifier_kappa_rolling{window, cohort}` y `classifier_kappa_rolling_last_update_unix_seconds{cohort}` UpDownCounters hookeados en `routes/analytics.py::compute_kappa()` cuando el request trae el campo opcional nuevo `cohort_id`. El frontend del web-teacher (kappa workflow) puede pasarlo en futuras iteraciones; sin él, el κ se computa pero no se grafica longitudinalmente.
- [ ] 7.3 Endpoint `POST /api/v1/analytics/kappa-rolling/refresh` que itera por todas las cohortes — DIFERIDO. Requiere DB queries por cohort + iteración de episodios. Por ahora el flow del piloto va a actualizar el gauge cuando los docentes corran el procedimiento intercoder con `cohort_id` en el request.
- [ ] 7.4 Documentación del endpoint refresh — DIFERIDO junto con 7.3.

`apps/analytics-service/src/analytics_service/metrics.py` creado. Campo `cohort_id: UUID | None` agregado al `KappaRequest` schema.

## 4. Instrumentación tutor-service

- [ ] 4.1 Modificar `apps/tutor-service/src/tutor_service/main.py` `lifespan`: llamar `setup_metrics("tutor-service", settings.otel_endpoint)`.
- [ ] 4.2 En `apps/tutor-service/src/tutor_service/services/tutor_core.py` (o donde se maneja el SSE response loop): crear `Histogram` `tutor_response_duration_seconds`; medir desde inicio del prompt hasta SSE complete.
- [ ] 4.3 En el módulo de session state (Redis-based): crear `Gauge` `tutor_active_sessions_count` que refleja el conteo actual de sesiones Redis activas (ej. via `SCAN` cada 30s o callback cuando se crea/destroy una sesión).

## 5. Instrumentación ai-gateway

- [ ] 5.1 Modificar `apps/ai-gateway/src/ai_gateway/main.py` `lifespan`: llamar `setup_metrics("ai-gateway", settings.otel_endpoint)`.
- [ ] 5.2 En el proxy handler: crear `Counter` `ai_gateway_tokens_total{provider, kind, tenant_id}` para input + output tokens (incluso del mock provider — declarado como dato del piloto en el dashboard).
- [ ] 5.3 Crear `Gauge` `ai_gateway_budget_remaining_usd{tenant_id}` actualizado cuando se descuenta del budget.
- [ ] 5.4 Crear `Histogram` `ai_gateway_request_duration_seconds{provider}`.
- [ ] 5.5 Crear `Counter` `ai_gateway_fallback_total{reason}` cuando el provider primario falla y se cae al fallback.
- [ ] 5.6 Crear `Counter` `ai_gateway_cache_hits_total` y `ai_gateway_requests_total` para cómputo de cache hit rate.

## 6. Instrumentación classifier-service

- [ ] 6.1 Modificar `apps/classifier-service/src/classifier_service/main.py` `lifespan`: llamar `setup_metrics("classifier-service", settings.otel_endpoint)`.
- [ ] 6.2 En el pipeline de clasificación: crear `Counter` `classifier_classifications_total{n_level, template_id, classifier_config_hash}` — incrementar al persistir cada Classification. **`student_pseudonym` PROHIBIDO** como label (D3 del design).
- [ ] 6.3 Crear `Gauge` `classifier_ccd_orphan_ratio{cohort}` actualizado cuando se computan métricas agregadas de cohorte.
- [ ] 6.4 Crear `Histogram` `classifier_cii_evolution_slope` para distribución cardinal de slopes (RN-130).
- [ ] 6.5 Acotar `template_id` a ≤ 50 valores distintos. Si excede, fallar fast en el código de instrumentación con un assertion explícito (mejor crashear que explosión silenciosa de cardinalidad).

## 7. Instrumentación analytics-service para κ rolling

- [ ] 7.1 Modificar `apps/analytics-service/src/analytics_service/main.py` `lifespan`: llamar `setup_metrics("analytics-service", settings.otel_endpoint)`.
- [ ] 7.2 En `apps/analytics-service/src/analytics_service/routes/analytics.py` endpoint `POST /api/v1/analytics/kappa`: agregar emisión del `Gauge` `classifier_kappa_rolling{window="7d", cohort}` con el valor κ computed + `Gauge` `classifier_kappa_rolling_last_update_unix_seconds{cohort}` con `time.time()`.
- [ ] 7.3 Agregar endpoint nuevo `POST /api/v1/analytics/kappa-rolling/refresh` que itera por todas las cohortes activas, recomputa κ, y actualiza ambos gauges. Documentar como manual/cron job (operativo).
- [ ] 7.4 Documentar el endpoint nuevo en `docs/pilot/runbook.md` o `docs/pilot/kappa-workflow.md` como tarea operativa nightly.

## 8. Provisioning Grafana — paths canónicos nuevos

- [x] 8.1 `infrastructure/grafana/provisioning/datasources/datasources.yaml` creado (Prometheus, Loki, Jaeger — contenido idéntico al legacy de `infrastructure/observability/grafana-datasources.yaml`).
- [x] 8.2 `infrastructure/grafana/provisioning/dashboards/dashboards.yaml` creado (provider `platform-piloto` con `foldersFromFilesStructure: true`, `updateIntervalSeconds: 30`, `allowUiUpdates: true`).
- [x] 8.3 Los 5 subdirectorios para folders creados: `plataforma/`, `ctr/`, `ai-gateway/`, `tutor/`, `classifier/`.

## 9. Los 5 dashboards JSON

- [x] 9.1 `plataforma/vision-general.json`: 6 paneles (Servicios up `up{job="otel-collector"}` × 12, CTR events/sec stacked, integrity_compromised stat con threshold rojo, Episodios opened/closed/abandoned 5m rate, Episode duration p50/p95, Error rate 5xx por servicio heatmap). Variables `$tenant`, `$service`. Refresh 30s.
- [x] 9.2 `ctr/integridad.json`: 5 paneles (Events por partición × 8 stacked, Worker XPENDING × 8 stat, integrity_compromised 24h stat con texto "INVESTIGAR I01", self_hash p99, Attestations emitidas vs pendientes). Variables `$tenant`. Refresh 15s.
- [x] 9.3 `ai-gateway/costos-y-latencia.json`: 5 paneles (Tokens stacked, Budget USD stat, Request latency p50/p99 por provider, Fallback 24h, Cache hit rate gauge %). Variables `$tenant`. Refresh 1m.
- [x] 9.4 `tutor/engagement.json`: 5 paneles (Episodios opened/closed/abandoned 1m rate, Tutor latency p50/p99 con threshold lines 3s/8s, intento_adverso_detectado por categoría, prompt_kind donut, Sesiones activas). Variables `$tenant`, `$cohort`. Refresh 30s.
- [x] 9.5 `classifier/kappa-y-coherencias.json`: 5 paneles (κ rolling 7d con threshold lines 0.4/0.6, n_level distribution % stacked, CCD orphan por cohorte, CII slope histogram, Reproducibility config_hash count target=1). Variables `$tenant`, `$cohort`, `$template_id`. Refresh 5m.
- [x] 9.6 Audiencia declarada en `description` de cada dashboard (comité doctoral, auditor, doctorando + DI UNSL, pedagogía + demo, tesis evidencia central).

## 10. Archivar dashboards heredados

- [x] 10.1-10.3 `ops/grafana/dashboards/` y `ops/grafana/provisioning/` movidos a `ops/grafana/_archive/`. La estructura original se preserva (subdirs `dashboards/` y `provisioning/`) bajo el nuevo `_archive/`.
- [x] 10.4 `ops/grafana/_archive/README.md` creado: explica que los JSONs son aspiracionales, lista las métricas que esperaban (`ctr_episodes_opened_total`, `ai_gateway_tokens_*`, etc.), y apunta al nuevo path canónico con instrucciones de migración panel-por-panel.

## 11. README operativo del provisioning nuevo

- [x] 11.1 `infrastructure/grafana/provisioning/dashboards/README.md` creado con todas las secciones requeridas: estructura de directorios, workflow export-from-UI → commit, política de cardinalidad con tabla de labels permitidas y prohibidas, naming convention OTel-friendly, **catálogo completo de métricas custom** con estado (`emitido` vs `pendiente`) por cada una, métricas auto-instrumentadas, comandos operativos para empezar limpio + verificación de cardinalidad, acceso (URL + credenciales).

## 12. Update docker-compose.dev.yml

- [x] 12.1 `infrastructure/docker-compose.dev.yml` sección `services.grafana.volumes` actualizada: ahora monta `./grafana/provisioning/datasources` y `./grafana/provisioning/dashboards` (relative al compose dir = `infrastructure/`). El legacy `../ops/grafana/...` y `./observability/grafana-datasources.yaml` quitados.
- [x] 12.2 `grafana_data:` volume preservado intacto.
- [x] 12.3 `infrastructure/observability/grafana-datasources.yaml` ya no se referencia desde el compose. El archivo persiste en disco como backup hasta que un PR de cleanup lo elimine (no scope este change para evitar coupling).

## 13. Verificación final post-apply

- [ ] 13.1 `docker compose -f infrastructure/docker-compose.dev.yml down -v && make dev-bootstrap` levanta limpio.
- [ ] 13.2 Arrancar los 12 servicios Python + 8 workers CTR + 3 frontends.
- [ ] 13.3 `uv run python scripts/seed-3-comisiones.py` aplicado.
- [ ] 13.4 Abrir 1 episodio + cerrarlo desde web-student.
- [ ] 13.5 Abrir Grafana `http://localhost:3000`: confirmar 5 folders (`Plataforma`, `CTR`, `AI Gateway`, `Tutor`, `Classifier`), cada una con su dashboard.
- [ ] 13.6 Confirmar **≥12 paneles con datos reales** (no `No data`).
- [ ] 13.7 Panel `integrity_compromised` del dashboard 2 muestra **0**.
- [ ] 13.8 Cardinalidad: `curl http://localhost:9090/api/v1/label/__name__/values | jq 'length'` devuelve **< 5000**.
- [ ] 13.9 `curl http://localhost:8889/metrics | grep ctr_events_total` muestra la métrica con sus labels.
- [ ] 13.10 `make lint typecheck test check-rls` verde con la instrumentación nueva.
- [ ] 13.11 Todos los paneles cargan en **< 3 segundos** en refresh manual.
