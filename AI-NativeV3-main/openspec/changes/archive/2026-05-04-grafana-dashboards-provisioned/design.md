## Context

El piloto UNSL llega a defensa doctoral con Grafana operacional pero **mostrando paneles "No data"**: los 2 JSONs heredados de `ops/grafana/dashboards/` referencian métricas que ningún servicio emite. La causa raíz no es el provisioning (el sidecar funciona bien) sino que `packages/observability` configura `tracing OTLP + structlog + Sentry` pero **nunca instaló el `MeterProvider`** — cero métricas custom emitidas en los 12 servicios.

Sin un cambio acá, la defensa abre Grafana y el comité doctoral ve un dashboard vacío. Aceptable técnicamente, pero pierde la evidencia visual del CTR escribiendo events en vivo, del tutor respondiendo bajo SLO, del ai-gateway sin gastar de más, y del classifier sosteniendo κ. Esa evidencia tangible es uno de los activos más fuertes que el modelo híbrido honesto puede mostrar — el comité no necesita confiar en logs textuales si ve series temporales subiendo en tiempo real.

El proposal acordó **5 dashboards + instrumentación mínima** del subset graficado (NO observabilidad completa) con scope contenido para 1.5 días de Día 5-6 del epic. Dos open questions quedaron explícitas y este design las cierra: panel embebido de Jaeger (D5) y mecanismo de push para κ rolling (D4).

## Goals / Non-Goals

**Goals:**
- 5 dashboards Grafana provisionados (`Plataforma`, `CTR`, `AI Gateway`, `Tutor`, `Classifier`) que muestren **datos reales** post-`make dev-bootstrap` + `seed-3-comisiones` + flujo demo.
- Instrumentación OTel Metrics mínima — exclusivamente las métricas que aparecen en los 5 dashboards. Cero scope creep a métricas que no se grafican.
- Reusar el OTel Collector ya wireado (OTLP gRPC :4317) — ningún `prometheus_client`, ningún endpoint `/metrics` per-service.
- Cardinalidad acotada por diseño — `student_pseudonym`/`episode_id` JAMÁS como labels (impacto privacidad + costo Prometheus).
- Workflow operativo declarado para anti-drift JSON ↔ UI.
- Path canónico nuevo `infrastructure/grafana/provisioning/` alineado con Grafana 11.

**Non-Goals:**
- Alerting rules (`alert.rules.yaml`, Alertmanager) — change separado.
- Synthetic monitoring (`blackbox_exporter`).
- Multi-tenant dashboard cloning — `$tenant` variable cubre el single-pane-of-glass del piloto.
- Migración a Mimir/Cortex o OTel Metrics Backend nativo — el path Collector → Prometheus se mantiene.
- Instrumentación de `identity-service` y `evaluation-service` (skeletons by-design).
- Dashboards para frontends Vite (sin web-vitals push).
- Loki dashboards combinados logs+metrics — Explore tab cubre el caso.

## Decisions

### D1 — OTel Metrics SDK vs `prometheus_client`

**Choice**: `MeterProvider` + `OTLPMetricExporter` via OTel SDK. Reusa el OTel Collector ya wireado (OTLP gRPC :4317 → Prometheus exporter :8889).

**Why over alternatives**:
- *Alternativa A: `prometheus_client.Counter/Histogram` + endpoint `/metrics` per-service*. Rechazada — cada servicio tendría que exponer `/metrics`, requeriría agregarlo al ROUTE_MAP del api-gateway o configurar scrape directo en Prometheus contra los 12 servicios. Rompe la regla "todo va por el gateway" y genera fricción de firewall en deploy real.
- *Alternativa B: dual emission (OTel push + Prometheus pull)*. Rechazada — ROI negativo, doble configuración, dos lugares para que diverjan los nombres de métricas.

**Tradeoff aceptado**: dependencia adicional sobre el OTel Collector (sin él, las métricas se pierden). El Collector ya es dependencia crítica para tracing — agregar metrics al mismo path no aumenta superficie operativa.

### D2 — Auto-instrumentación FastAPI con `meter_provider` además del `tracer`

**Choice**: en `packages/observability.setup_metrics()`, llamar a `FastAPIInstrumentor.instrument_app(app, meter_provider=meter_provider)` en addition al setup del tracer existente.

**Why over alternatives**:
- *Alternativa A: instrumentar manualmente `http_server_requests_total` por servicio*. Rechazada — duplicación + drift; auto-instrumentation lo hace gratis.
- *Alternativa B: confiar en spans de tracing como derivación*. Rechazada — Grafana usaría Jaeger datasource y el panel "error rate" requiere queries Prometheus específicas.

**Riesgo**: si la versión de `opentelemetry-instrumentation-fastapi` instalada no soporta `meter_provider` (solo `tracer_provider`), el panel "error rate" del dashboard 1 queda vacío hasta upgrade. Mitigación: verificar versión en task 1.1; si vieja, bumpear como sub-tarea.

### D3 — Cardinalidad de labels: hard limits explícitos

**Choice**: la lista de labels permitidas es **cerrada** y declarada en el spec:
- Permitidas: `tenant_id`, `service_name`, `event_type`, `partition` (0-7), `provider` (LLM), `kind` (input/output), `n_level` (N1-N4), `cohort` (alias de comision_id, max ~30 valores), `prompt_kind` (5 enum values), `template_id` (cardinalidad ≤ 50 declarada).
- **Prohibidas**: `student_pseudonym`, `episode_id`, `user_id`, `prompt_id`, cualquier UUID por-instancia.

**Why**: con 18 estudiantes × 5 templates × 3 cohortes × 4 n_levels = 1080 series solo por `student_pseudonym × template × cohort × n_level`. Multiplicar por timestamps de buckets de histograms y Prometheus muere. Además, `student_pseudonym` como label expone correlation cross-metric (privacidad).

**Tradeoff**: las quartiles/alertas individuales por estudiante viven en el plano API (analytics-service `/student/{id}/alerts`) y NO en métricas Prometheus. Aceptado.

**Enforcement**: smoke test `scripts/check-grafana-cardinality.sh` que pega a `curl http://localhost:9090/api/v1/label/__name__/values | jq 'length'` post-seed-and-flow y falla si > 5000 series. Agregado como gate de CI follow-up (no bloqueante en este PR).

### D4 — κ rolling: push del analytics-service via OTel push, NO Pushgateway separado

**Choice**: el analytics-service expone un job nightly (cron o endpoint manual `POST /api/v1/analytics/kappa-rolling/refresh`) que recomputa κ por cohorte sobre ventana 7d y actualiza un `Gauge` `classifier_kappa_rolling{window="7d", cohort}` via OTel SDK. La métrica viaja por OTLP al Collector → Prometheus como cualquier otra métrica del piloto.

**Why over alternatives**:
- *Alternativa A: Pushgateway separado*. Rechazada — componente nuevo en infra, otra superficie de fallo, incompatible con el patrón "todo via OTel Collector". Y los Pushgateways son específicamente para batch jobs de corta duración con valores que nunca decaen — el use case del piloto.
- *Alternativa B: PostgresDB datasource en Grafana queryeando una tabla `analytics.kappa_rolling`*. Rechazada — agrega un datasource más, queries SQL en Grafana son menos portables, y el κ rolling es una métrica observabilidad-natural (gauge temporal), no un fact de negocio.
- *Alternativa C: recompute on-pull (Grafana llama al endpoint via JSON datasource)*. Rechazada — recomputo cada refresh = costo computacional alto + dependencia bidireccional Grafana → analytics-service.

**Implementación**: dentro del `setup_metrics()` del analytics-service, agregar un Gauge `classifier_kappa_rolling`. Cada vez que se llama al endpoint `POST /api/v1/analytics/kappa` (intercoder workflow), también se actualiza el gauge para esa cohorte. Adicionalmente, una task scheduled (que se puede correr manualmente o via cron docker) llama a `POST /api/v1/analytics/kappa-rolling/refresh` que itera por todas las cohortes activas y recomputa.

**Tradeoff**: si el job nightly no corre, el gauge queda en su último valor — el dashboard muestra datos viejos sin warning. Aceptable para piloto-1 (operativo manual). Mitigación: panel del dashboard 5 muestra `last_updated_seconds_ago` derivado de `time() - kappa_rolling_last_update_unix_seconds` (segundo gauge, mismo update).

### D5 — Panel Jaeger embebido en dashboard 1: NO

**Choice**: NO incluir un panel embebido de Jaeger en el dashboard 1.

**Why**:
- Grafana 11 tiene "Explore" tab nativa que abre Jaeger con un click — accesible desde cualquier dashboard. Embeberlo duplica funcionalidad y agrega ruido visual.
- El dashboard 1 es para **estado quantitative del sistema** (servicios up, error rates, throughput). El tracing es **debugging exploratory** — distinta intención cognitiva, distinta vista.
- El comité doctoral en defensa NO va a hacer trace exploration — va a ver "está todo verde" o "hay alarmas". Para ese case, el panel embebido sería ignorado.

**Aceptado**: si más adelante surge la necesidad operativa (ej. on-call quiere ver traces correlated en el mismo pane), se evalúa. Por ahora, KISS.

### D6 — `allowUiUpdates: true` con workflow export-from-UI documentado

**Choice**: mantener `allowUiUpdates: true` en el provisioning provider para permitir iteración visual en Grafana UI. El workflow de "persistir cambios" es manual: editar en UI → `Share → Export → Save to file` → reemplazar el JSON commiteado.

**Why over alternatives**:
- *Alternativa A: `allowUiUpdates: false`, edit-only-from-files*. Rechazada — fricción enorme para iterar en demos y defensa. Cualquier ajuste visual requiere git commit + restart.
- *Alternativa B: Jsonnet/Grizzly para tipar dashboards*. Rechazada — overengineering para 5 dashboards. ROI negativo en horizonte piloto-1.

**Tradeoff aceptado**: el JSON commiteado puede divergir del UI live state si alguien edita y olvida exportar. Mitigación: README documenta el flujo, plus follow-up posible (`scripts/check-grafana-dashboards-clean.sh` en CI que verifique diff vs UI export — fuera de scope).

### D7 — Path canónico `infrastructure/grafana/provisioning/`, archivar `ops/grafana/`

**Choice**: nuevo path es `infrastructure/grafana/provisioning/{datasources,dashboards}/`. El path `ops/grafana/` se mueve a `ops/grafana/_archive/` con README de deprecación.

**Why**:
- `infrastructure/` ya contiene `docker-compose.dev.yml` + `helm/` + `observability/` — los dashboards son configuración de infra, alineado con la convención de Grafana 11 (`/etc/grafana/provisioning`).
- Tener config de Grafana en 2 paths (`ops/grafana/` legacy + `infrastructure/grafana/` nuevo) confunde al developer. Movimiento atómico cierra la deuda.
- `ops/` queda como home de scripts/runbooks operativos, no de provisioning.

**Migration**: el `docker-compose.dev.yml` actualiza el `volumes:` del servicio Grafana en el mismo PR de apply. README en `_archive/` explica que los JSONs son aspiracionales y referencian métricas que nunca se emitieron.

### D8 — Métrica `up{job="otel-collector"}` para servicios up

**Choice**: el panel "Servicios up × 12" del dashboard 1 usa `up{job="otel-collector"}` desagregado por `service_name` (label que viene del resource attributes que cada servicio configura).

**Why**: la métrica `up` la emite Prometheus automáticamente del scrape — no requiere instrumentación adicional. Si un servicio no manda métricas en X tiempo, su `service_name` no aparece en el output del Collector y `up` para ese servicio "desaparece". Aceptable para detección de "está vivo": si no manda métricas hace 30s+, está caído.

**Tradeoff**: el `up` técnicamente mide "está mandando métricas a OTel Collector", no "responde HTTP". Es proxy razonable: si no manda, está caído o desconectado. Si responde HTTP pero no manda métricas, hay bug operativo más crítico que un dashboard "verde aparente".

## Risks / Trade-offs

- **Budget de 1.5 días apretado** → priorización: ctr-service + tutor-service (Día 5) son críticos para defensa; ai-gateway + classifier (Día 6) pueden quedar parcialmente instrumentados sin bloquear. Si el Día 6 corre tarde, los dashboards 3-5 se demueltran con data sintética del seed.
- **Cardinalidad explosion** → mitigación D3 + smoke test scripts/check-grafana-cardinality.sh. Si se introduce un label prohibido por accidente, el smoke falla post-seed.
- **JSON drift dashboard ↔ commit** → mitigación D6 (README con workflow). Follow-up posible: script de diff CI.
- **Auto-instrumentación FastAPI versión-sensible** → mitigación D2 (verificar versión en task 1.1).
- **κ rolling depende de cron job manual** → mitigación D4 (panel `last_updated_seconds_ago`). Documentar en README operativo.
- **`grafana_data:` volume con state previo** → mitigación: README documenta `docker compose down -v` antes del primer `make dev-bootstrap` post-apply.
- **Naming convention OTel semconv puede shift** → aceptado para piloto-1; documentación de las métricas custom actuales en README permite migration futura.

## Migration Plan

1. **Pre-apply**: `docker compose -f infrastructure/docker-compose.dev.yml down -v` (limpia volume Grafana viejo).
2. **Apply phase** (en orden):
   1. Verificar deps OTel Metrics SDK y `opentelemetry-instrumentation-fastapi` versión.
   2. Implementar `setup_metrics()` en `packages/observability`.
   3. Instrumentar ctr-service (más crítico).
   4. Instrumentar tutor-service.
   5. Instrumentar ai-gateway.
   6. Instrumentar classifier-service + analytics-service (para κ rolling).
   7. Mover `infrastructure/observability/grafana-datasources.yaml` → `infrastructure/grafana/provisioning/datasources/datasources.yaml`.
   8. Crear provider `infrastructure/grafana/provisioning/dashboards/dashboards.yaml`.
   9. Crear los 5 JSONs de dashboards.
   10. Archivar `ops/grafana/` → `ops/grafana/_archive/` con README.
   11. Actualizar `docker-compose.dev.yml` volumes.
   12. README operativo en `infrastructure/grafana/provisioning/dashboards/`.
3. **Post-apply smoke**:
   1. `make dev-bootstrap` → infra arriba.
   2. Arrancar 12 servicios + 8 workers CTR + 3 frontends.
   3. `seed-3-comisiones`.
   4. Abrir 1 episodio + cerrarlo (web-student).
   5. Abrir Grafana :3000, verificar 5 folders, verificar ≥12 paneles con data, verificar `integrity_compromised=0`.
   6. Correr `scripts/check-grafana-cardinality.sh` (nuevo).

**Rollback**: el git revert del PR restaura los dashboards heredados (que mostrarán "No data" pero no romperán Grafana). Métricas dejan de emitirse, app sigue funcionando — desacoplado.

## Open Questions

- **`scripts/check-grafana-cardinality.sh` en CI**: el script existe en este change pero NO se agrega como gate de CI. ¿Lo agregamos como follow-up change separado, o aceptamos que viva fuera del CI hasta que emerja una regresión real?
  → **Resolución**: deferido a follow-up. Documentar en `BUGS-PILOTO.md` como deuda con prioridad media.
- **Naming de métricas: ¿prefijo `platform_` o nombre directo?** El proposal usa `ctr_events_total`, `ai_gateway_tokens_total` (sin prefijo `platform_`). Es consistente entre métricas custom del piloto pero podría colisionar con métricas auto-generadas de OTel libraries.
  → **Resolución**: mantener sin prefijo. Las métricas custom usan el nombre del servicio como prefijo (`ctr_*`, `ai_gateway_*`, `tutor_*`, `classifier_*`) — eso ya da espacio de nombres separado. Si en el futuro chocar con OTel semconv, migrate atómico.
