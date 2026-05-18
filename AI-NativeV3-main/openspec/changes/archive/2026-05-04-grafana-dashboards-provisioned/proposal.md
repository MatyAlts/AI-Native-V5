## Why

Hoy Grafana corre (`infrastructure/docker-compose.dev.yml:173-191`, puerto 3000) con datasources auto-provisionados (Prometheus, Loki, Jaeger), pero los dashboards visibles al login son **dos JSONs huérfanos** en `ops/grafana/dashboards/` que referencian métricas que **no se emiten hoy** (`ctr_episodes_opened_total`, `ctr_events_total`, `ctr_episode_duration_seconds`, `http_server_duration_seconds_bucket`, etc.). El comité doctoral va a ver paneles "No data" — defensible pero no memorable. El piloto UNSL va a tener 4 meses de operación sin un dashboard que el docente o el coordinador puedan abrir para ver "¿está vivo el sistema?".

La defensa gana enormemente con **evidencia en vivo** del CTR escribiendo eventos, del tutor respondiendo bajo SLO, del ai-gateway sin gastar de más, y del classifier sosteniendo κ. La inversión incremental es chica si lo aceptamos como **dashboards + instrumentación mínima** del subset que se grafica — no como observabilidad completa.

## What Changes

### Hallazgos previos a la decisión de scope

Antes de diseñar paneles, esta sesión verificó la pipeline real:

- **`packages/observability/src/platform_observability/__init__.py`**: configura **tracing OTLP + structlog + Sentry**, pero NO `MeterProvider`, NO OTLPMetricExporter, NO helpers para `Counter`/`Histogram`/`Gauge`. Cero métricas custom emitidas.
- **`infrastructure/observability/prometheus.yml`**: scrape único contra `otel-collector:8889` (Prometheus exporter del Collector). NO scrapea los 12 servicios directo en `/metrics`.
- **`infrastructure/observability/otel-collector-config.yaml`**: pipeline de métricas existe (`receivers: [otlp] → exporters: [prometheus]`) pero **nadie le manda métricas** porque ningún servicio tiene `MeterProvider` configurado — solo traces y logs.
- **`apps/*/src/**`**: cero `prometheus_client.Counter`, cero `meter.create_counter`, cero endpoint `/metrics` real (solo aparece como ruta exempt en `api-gateway/middleware/{rate_limit,jwt_auth}.py` por defensa preventiva).
- **`ops/grafana/dashboards/{platform-slos,unsl-pilot}.json`**: existen como artefactos heredados — referencian métricas auto-instrumentadas por OTel (`http_server_duration_seconds_bucket`, `http_server_requests_total`) y métricas custom de negocio (`ctr_episodes_opened_total`, `ctr_events_total`, `ctr_episode_duration_seconds`, `ai_gateway_tokens_*`, `classifier_kappa_*`) que **nunca se emitieron**. Los paneles van a renderizar pero todos los queries devuelven empty.
- **`ops/grafana/provisioning/dashboards/platform.yaml`**: provider de archivos ya wireado a `/var/lib/grafana/dashboards` con `updateIntervalSeconds: 30, allowUiUpdates: true`. El sidecar JSON-loop ya funciona — el issue es **qué JSON poner ahí**, no cómo cargarlo.

**Conclusión**: la emisión de métricas es **partial / casi cero**. Sin instrumentación en este change, los dashboards quedan exclusivamente con paneles `up` (de service discovery) + tracing-derivado (Jaeger panel embebido). Eso NO cumple la promesa de la defensa. Por lo tanto:

- **Instrumentación mínima entra dentro de scope**, restringida al subset que aparece en los 5 dashboards. NO se instrumenta nada que no se grafique.
- Se reusa el OTel Collector ya wireado (vía OTLP gRPC `:4317`) — NO se agrega `prometheus_client` ni un endpoint `/metrics` por servicio (evita romper la regla de "todo va por el gateway"; OTLP push elimina firewall a nivel de gateway).
- Los dos dashboards heredados se **archivan** (movidos a `ops/grafana/dashboards/_archive/`) y reemplazados por los 5 nuevos, ya que sus métricas son aspiracionales.

### 5 dashboards provisionados

Cada uno como JSON en `infrastructure/grafana/provisioning/dashboards/<carpeta>/<slug>.json` (NUEVO path canónico, alineado con la convención de Grafana 11; los `ops/grafana/*` quedan como deprecated y se archivan en el mismo PR de aplicación).

1. **Plataforma — visión general** (`folder: Plataforma`, refresh `30s`, audiencia: comité doctoral + DI UNSL).
   - **Servicios up** (stat panel × 12) — `up{job="otel-collector"}` desagregado por `service_name`. Verde si todos los 12 = 1.
   - **CTR events/sec** (timeseries) — `sum(rate(ctr_events_total[1m]))` apilado por `event_type`.
   - **integrity_compromised counter** (stat con threshold rojo > 0) — `sum(ctr_episodes_integrity_compromised_total)`. Target: 0.
   - **Episodios abiertos vs cerrados** (timeseries) — `rate(ctr_events_total{event_type="episodio_abierto"}[5m])` vs `..._cerrado` y `..._abandonado`.
   - **Episode duration p50/p95** (timeseries) — `histogram_quantile(0.5|0.95, sum(rate(ctr_episode_duration_seconds_bucket[10m])) by (le))`.
   - **Error rate por servicio** (heatmap) — `sum(rate(http_server_requests_total{http_status_code=~"5.."}[5m])) by (service_name)`.

2. **CTR — integridad** (`folder: CTR`, refresh `15s`, audiencia: auditor del piloto + defensa).
   - **Events written por partición** (timeseries stacked × 8) — `sum(rate(ctr_events_total[1m])) by (partition)`.
   - **Worker lag (XPENDING)** (gauge × 8) — `ctr_worker_xpending_count{partition=~"[0-7]"}`.
   - **integrity_compromised events** (stat alerta visual) — `sum(increase(ctr_episodes_integrity_compromised_total[24h]))`. Target estricto: 0; cualquier valor > 0 paint rojo + texto "INVESTIGAR I01".
   - **self_hash compute latency** (timeseries) — `histogram_quantile(0.99, sum(rate(ctr_self_hash_compute_seconds_bucket[5m])) by (le))`.
   - **Attestations Ed25519 emitidas / pendientes** (stat) — `ctr_attestations_emitted_total` vs `ctr_attestations_pending_count` (RN-128).

3. **AI Gateway — costos y latencia** (`folder: AI Gateway`, refresh `1m`, audiencia: doctorando + DI UNSL para budget).
   - **Tokens used por proveedor** (timeseries stacked) — `sum(rate(ai_gateway_tokens_total[5m])) by (provider, kind)` (`kind ∈ {input, output}`).
   - **Budget remaining $USD por tenant** (stat con threshold) — `ai_gateway_budget_remaining_usd{tenant=~"$tenant"}`.
   - **Request latency p50/p99** (timeseries) — `histogram_quantile(0.5|0.99, sum(rate(ai_gateway_request_duration_seconds_bucket[5m])) by (le, provider))`.
   - **Fallback events** (stat) — `sum(increase(ai_gateway_fallback_total[24h]))`.
   - **Cache hit rate** (gauge %) — `sum(rate(ai_gateway_cache_hits_total[5m])) / sum(rate(ai_gateway_requests_total[5m]))`.

4. **Tutor — engagement** (`folder: Tutor`, refresh `30s`, audiencia: pedagogía + demo).
   - **Episodios opened/closed/abandoned per minuto** (timeseries) — 3 series del `rate(ctr_events_total{event_type=~"...")[1m]`.
   - **Tutor response latency p50/p99** (timeseries) — `histogram_quantile(0.5|0.99, sum(rate(tutor_response_duration_seconds_bucket[5m])) by (le))`. SLO line a 3s (p95) y 8s (p99) con thresholds.
   - **intento_adverso_detectado rate** (timeseries por categoría) — `sum(rate(ctr_events_total{event_type="intento_adverso_detectado"}[5m])) by (category)` (RN-129).
   - **prompt_kind distribution** (pie) — `sum by (prompt_kind) (rate(ctr_events_total{event_type="prompt_enviado"}[1h]))`.
   - **Sesiones activas** (stat) — `tutor_active_sessions_count`.

5. **Classifier — kappa & coherencias** (`folder: Classifier`, refresh `5m`, audiencia: tesis — evidencia central).
   - **κ rolling 7d por cohorte** (timeseries) — `classifier_kappa_rolling{window="7d", cohort=~"$cohort"}` (gauge actualizado por job nightly del analytics-service). Target line κ ≥ 0.6.
   - **n_level distribution por template** (stacked area %) — `sum by (n_level, template_id) (rate(classifier_classifications_total[1h]))` normalizado.
   - **CCD orphan ratio** (timeseries) — `avg(classifier_ccd_orphan_ratio)` por cohorte.
   - **CII evolution slope histogram** (histogram) — distribución de `classifier_cii_evolution_slope` (RN-130).
   - **Reproducibility — config_hash count** (stat) — `count(count by (classifier_config_hash) (classifier_classifications_total))`. Target: 1 si todas las clasificaciones del piloto comparten la misma config (auditabilidad).

### Estrategia de provisioning

- **Nuevo path canónico**: `infrastructure/grafana/provisioning/{datasources,dashboards}/`. El `docker-compose.dev.yml` se actualiza para montar este nuevo path (en el mismo PR de apply); el path antiguo `ops/grafana/` se mueve a `_archive/` con README de deprecación que apunta al nuevo.
- **Datasources** ya provisionados en `infrastructure/observability/grafana-datasources.yaml`. Se mueven al nuevo path canónico — no se cambia contenido.
- **Folders en Grafana**: `Plataforma`, `CTR`, `AI Gateway`, `Tutor`, `Classifier` (uno por dashboard). Provider YAML usa `foldersFromFilesStructure: true` para que la jerarquía surja del filesystem.
- **Variables / templating**:
  - `$tenant` — `label_values(ctr_events_total, tenant_id)` (default: tenant demo `aaaaaaaa-...` para no exponer producción).
  - `$cohort` — `label_values(ctr_events_total{tenant_id="$tenant"}, comision_id)`.
  - `$service` — `label_values(up, service_name)` (solo en dashboard 1).
  - `$template_id` — `label_values(classifier_classifications_total{tenant_id="$tenant"}, template_id)` (solo en dashboard 5).
- **Workflow de edición** (anti-drift): Grafana corre con `allowUiUpdates: true` para permitir iteración visual; cuando se quiere persistir, se exporta el JSON via UI (`Share → Export → Save to file`) y se commitea al path provisioned. El README del directorio documenta el loop. Esto es deuda aceptada por velocidad — alternativa (Jsonnet/Grizzly) queda fuera de scope.

### Instrumentación mínima dentro de scope

Sólo lo que aparece en los 5 dashboards de arriba. NO se instrumentan métricas que no se grafiquen. Implementación:

- **`packages/observability/__init__.py`**: agregar `setup_metrics(service_name, otel_endpoint)` que crea `MeterProvider` con `OTLPMetricExporter(insecure=True, endpoint=otel_endpoint)`. Helper `get_meter(name)` paralelo a `get_tracer(name)`. Mantiene la regla "todo via OTel Collector" — cero `prometheus_client`, cero endpoint `/metrics` por servicio.
- **`apps/ctr-service/src/ctr_service/services/producer.py` + `routes/events.py`**: `Counter` `ctr_events_total{tenant_id, event_type, partition}`, `Counter` `ctr_episodes_integrity_compromised_total`, `Histogram` `ctr_self_hash_compute_seconds`, `Histogram` `ctr_episode_duration_seconds{tenant_id, comision_id}`, `Gauge` `ctr_worker_xpending_count{partition}`, `Counter` `ctr_attestations_emitted_total` y `Gauge` `ctr_attestations_pending_count`.
- **`apps/ai-gateway/src/ai_gateway/`**: `Counter` `ai_gateway_tokens_total{provider, kind, tenant}`, `Gauge` `ai_gateway_budget_remaining_usd{tenant}`, `Histogram` `ai_gateway_request_duration_seconds{provider}`, `Counter` `ai_gateway_fallback_total{reason}`, `Counter` `ai_gateway_cache_hits_total` + `..._requests_total`.
- **`apps/tutor-service/src/tutor_service/`**: `Histogram` `tutor_response_duration_seconds`, `Gauge` `tutor_active_sessions_count`. (Las series por `event_type` salen del `ctr_events_total` ya que se etiqueta con `event_type`.)
- **`apps/classifier-service/src/classifier_service/`**: `Counter` `classifier_classifications_total{n_level, template_id, classifier_config_hash}`, `Gauge` `classifier_ccd_orphan_ratio{cohort}`, `Histogram` `classifier_cii_evolution_slope`. **κ rolling NO se mide aquí en runtime** — el dashboard lo lee de un endpoint del analytics-service (`/api/v1/analytics/kappa-rolling`) que se expone como métrica push (job nightly). Se documenta como tal.
- **Cardinalidad**: las labels de alta cardinalidad están deliberadamente acotadas — `student_pseudonym` JAMÁS se usa como label de Prometheus (explotaría con N=18 estudiantes × cohorte × template). Las quartiles/alertas individuales viven en el plano API (analytics-service) y no en métricas. `template_id` se acota a `LIMIT 50` por ahora (aceptable para piloto-1 con ~3-5 templates por materia).

## Capabilities

### New Capabilities

- `observability-dashboards`: Sistema de dashboards Grafana provisionados sobre métricas OTel Collector → Prometheus, con 5 dashboards definidos como JSON commiteable en `infrastructure/grafana/provisioning/dashboards/`. Cubre la convención de folders, variables (`$tenant`, `$cohort`, `$service`, `$template_id`), refresh por dashboard, audiencia declarada por panel, política de cardinalidad de labels (no `student_pseudonym`), y workflow anti-drift de export-from-UI → JSON commit.
- `metrics-instrumentation-otlp`: Capa mínima de emisión de métricas OTLP (`MeterProvider` + `OTLPMetricExporter`) en `packages/observability`, instrumentando exclusivamente las métricas que aparecen en los 5 dashboards: CTR events/integrity/duration/attestations, ai-gateway tokens/budget/latency/fallback/cache, tutor response latency + sessions, classifier classifications/ccd-orphan/cii-slope. NO incluye `prometheus_client` ni endpoints `/metrics` per-service — todo va por OTLP push al Collector ya wireado.

### Modified Capabilities

Ninguna — no hay specs previas en `openspec/specs/` (la dir está vacía). Esta capability nace nueva. Los dashboards heredados de `ops/grafana/` no son una capability — son artefactos que se archivan en el apply phase.

## Impact

- **Código nuevo**:
  - `infrastructure/grafana/provisioning/datasources/datasources.yaml` (movido desde `infrastructure/observability/grafana-datasources.yaml`, contenido idéntico).
  - `infrastructure/grafana/provisioning/dashboards/dashboards.yaml` (provider con `foldersFromFilesStructure: true`).
  - `infrastructure/grafana/provisioning/dashboards/{plataforma,ctr,ai-gateway,tutor,classifier}/<slug>.json` (5 archivos).
  - `infrastructure/grafana/provisioning/dashboards/README.md` (workflow de edición + export → commit).
  - `packages/observability/src/platform_observability/__init__.py` extendido con `setup_metrics()`, `get_meter()`, `MetricsConfig`.
- **Código modificado**:
  - `infrastructure/docker-compose.dev.yml`: cambiar volumes del servicio `grafana` para montar el nuevo path canónico (`infrastructure/grafana/provisioning/`) en vez de `ops/grafana/`.
  - `apps/ctr-service/`, `apps/ai-gateway/`, `apps/tutor-service/`, `apps/classifier-service/`: agregar `setup_metrics()` al `lifespan` + emisiones de métricas en hot path.
- **Código archivado**:
  - `ops/grafana/dashboards/{platform-slos,unsl-pilot}.json` → `ops/grafana/dashboards/_archive/` con README explicando que son aspiracionales y referenciaban métricas que no se emitían.
  - `ops/grafana/provisioning/` → archivado por el mismo motivo.
- **Dependencias**:
  - `opentelemetry-sdk[metrics]` y `opentelemetry-exporter-otlp-proto-grpc` ya están instalados (vienen en el extra del SDK que ya usamos para tracing) — verificar versión y unblockear el grupo de métricas en el `pyproject.toml` de `packages/observability` si está pinned para excluirlas.
- **CI**: ningún cambio en `.github/workflows/`. El gate `make lint typecheck test check-rls` debe seguir verde con la instrumentación nueva.
- **Tiempo estimado**: 1.5 días (Día 5-6 del epic).
  - Día 5 mañana: `setup_metrics()` en `packages/observability`, instrumentación de ctr-service + tutor-service.
  - Día 5 tarde: instrumentación de ai-gateway + classifier-service.
  - Día 6: 5 dashboards JSON + provisioning + smoke en `make dev-bootstrap`.
- **Servicios requeridos para que los dashboards muestren data**:
  - 12 servicios Python corriendo (con la instrumentación nueva activa).
  - 8 CTR partition workers consumiendo (sin ellos, `ctr_events_total` por partición queda en 0).
  - `seed-3-comisiones.py` ejecutado.
  - Al menos 1 episodio abierto + 1 cerrado para que los histograms tengan buckets poblados.
  - `LLM_PROVIDER=mock` (los counters de `ai_gateway_tokens_total` cuentan tokens del mock — defendible, declarado en el dashboard).

## Non-goals

- **Alerting rules**: no se definen `alert.rules.yaml` ni Alertmanager. La defensa muestra dashboards, no incident response. Es change separado posterior si emerge necesidad.
- **Synthetic monitoring / blackbox probing**: ningún `blackbox_exporter`, ningún job que pegue a `/health` desde fuera. El existing `make check-health` cubre el caso operacional.
- **Multi-tenant dashboard cloning**: no se duplican dashboards por tenant. La variable `$tenant` cubre el caso single-pane-of-glass del piloto. Si el día de mañana hay N tenants reales productivos, sí se evalúa.
- **Migración a OTel-only end-to-end**: el path Prometheus (Collector → exporter Prometheus → Prometheus DB → Grafana) se mantiene. NO se mueve a OTel Metrics Backend ni a Mimir/Cortex.
- **Cobertura completa de los 12 servicios**: `identity-service` (skeleton by-design) y `evaluation-service` (skeleton sin uso) NO se instrumentan. El dashboard 1 muestra `up` para los 12 (eso sale gratis por el `up` que el Collector emite del scrape de sí mismo) pero no espera métricas de negocio de esos dos.
- **Dashboards para `web-*`**: los frontends Vite no exportan métricas en el piloto (no hay `web-vitals` push a OTel). Cubierto por Sentry / browser console si emerge.
- **Loki dashboards**: los logs siguen accesibles via Explore en Grafana. No se diseñan paneles que combinen logs + métricas. Posible follow-up.

## Risks

- **Budget de 1.5 días es ajustado** si la instrumentación mínima resulta tener más fricción que la prevista (ej. el `OTLPMetricExporter` requiere parámetros adicionales en algún servicio Python que ya tiene un `lifespan` complicado). Mitigación: el orden del Día 5-6 está priorizado — primero ctr-service (el más crítico para la defensa) y tutor-service (engagement); si al final del Día 5 los dashboards 1-2-4 son verdes con data real, el dashboard 3 (ai-gateway) y 5 (classifier) pueden quedar con instrumentación parcial y datos sintéticos del seed sin bloquear la defensa.
- **Cardinalidad de labels** — `student_pseudonym` y `episode_id` JAMÁS se usan como labels (declarado en scope arriba). Si por accidente se introduce, Prometheus puede explotar — el ratchet del Collector en `infrastructure/observability/otel-collector-config.yaml` tiene `memory_limiter: limit_mib: 512` que actuará como throttle, pero no como protección semántica. Mitigación: agregar test smoke al PR de apply que cuente series cardinality en Prometheus después de seed + 1 episodio cerrado, y falle si > 5000 series.
- **JSON drift dashboard ↔ commit**: el modo `allowUiUpdates: true` permite editar en UI sin commitear. El README documenta el flujo, pero queda como deuda operativa. Mitigación reforzable: agregar un check en CI `scripts/check-grafana-dashboards-clean.sh` que verifique que los JSONs commiteados coinciden con los provisionados — fuera de scope para este change pero declarable como follow-up.
- **Métricas custom requieren naming alineado con OTel semconv** — si hoy adoptamos `ctr_events_total` y mañana OTel publica `ctr_events_count` como semconv, hay que migrar. Aceptado: el piloto no lleva tanto tiempo. Quedan documentadas las métricas en `infrastructure/grafana/provisioning/dashboards/README.md`.
- **`grafana_data:` volume persiste estado**: si Grafana tiene state previo (folders viejos, dashboards en otra ubicación), el provisioning nuevo puede chocar. Mitigación: el README documenta `docker compose down -v` antes del primer `make dev-bootstrap` post-apply para empezar limpio.
- **Auto-instrumentación FastAPI ya emite spans pero NO histogramas HTTP por default** en el setup actual (`FastAPIInstrumentor.instrument_app(app)` instala traces, no metrics). El dashboard 1 panel "error rate por servicio" depende de `http_server_requests_total`, que es métrica de la auto-instrumentación de métricas — distinta API. `setup_metrics()` debe llamar a `FastAPIInstrumentor()` con el `meter_provider` configurado, no solo con el tracer. Documentado en design phase.

## Acceptance criteria

- [ ] `make dev-bootstrap` levanta limpio y los 5 dashboards aparecen en Grafana (`http://localhost:3000`) bajo las 5 folders correspondientes (`Plataforma`, `CTR`, `AI Gateway`, `Tutor`, `Classifier`).
- [ ] Después de `uv run python scripts/seed-3-comisiones.py` + arrancar al menos 1 episodio + cerrarlo desde web-student, **al menos 12 paneles de los 5 dashboards muestran datos reales** (no "No data"). Los paneles que dependan de eventos no producidos por el flow demo (ej. `intento_adverso_detectado`) pueden quedar vacíos pero NO crashear.
- [ ] Panel "integrity_compromised" del dashboard 2 muestra **0** después del seed + flujo demo.
- [ ] Todos los paneles cargan en **< 3 segundos** desde el Refresh manual.
- [ ] Los 4 servicios instrumentados (ctr-service, ai-gateway, tutor-service, classifier-service) emiten métricas verificables con `curl http://localhost:8889/metrics | grep ctr_events_total` (Prometheus exporter del Collector).
- [ ] `make lint typecheck test check-rls` verde con la instrumentación nueva.
- [ ] Los dashboards heredados (`ops/grafana/dashboards/{platform-slos,unsl-pilot}.json`) están movidos a `_archive/` con README explicando la decisión.
- [ ] `infrastructure/grafana/provisioning/dashboards/README.md` documenta: workflow export-from-UI → commit, política de labels (no `student_pseudonym`), naming convention OTel-friendly, comando para empezar limpio (`docker compose down -v`).
- [ ] Cardinalidad de Prometheus después del flujo demo `< 5000 series`. Verificable con `curl http://localhost:9090/api/v1/label/__name__/values | jq 'length'`.

## Open questions

- ¿Vale la pena un panel embebido de Jaeger (trace explore) en el dashboard 1, o eso es ruido visual? Decisión deferida a design phase.
- κ rolling necesita un job que push-ee la métrica desde analytics-service. ¿Job en cron de docker-compose, en GitHub Actions, o endpoint que recompute on-pull? Decisión deferida a design phase. Default sugerido: endpoint del analytics-service que el panel del dashboard 5 consume via datasource Prometheus con un `pushgateway` chico (componente nuevo) — o directamente como tabla queryable via PostgresDB datasource (otra opción a evaluar).
