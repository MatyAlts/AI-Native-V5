## ADDED Requirements

### Requirement: Métricas BYOK exportadas via OTLP

El `ai-gateway` SHALL exportar las siguientes métricas Prometheus via OTLP collector:

- `byok_key_usage_total` (Counter) — labels: `provider`, `scope_type` (tenant/facultad/materia/env_fallback), `tenant_id`. Incrementa por request exitoso.
- `byok_key_resolution_total` (Counter) — labels: `resolved_scope`, `provider`. Incrementa por cada resolución (con o sin hit).
- `byok_key_resolution_duration_seconds` (Histogram) — buckets `[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1]`. Mide latencia del resolver (incluye lookup Redis + DB query).
- `byok_key_cost_usd_total` (Counter) — labels: `key_id`, `provider`. Suma costo monetario.
- `byok_budget_exceeded_total` (Counter) — labels: `key_id`. Incrementa por request rechazado por budget cap.

Las labels SHALL respetar el cardinality budget existente del spec: `tenant_id` permitido (multi-tenant es central), `key_id` es alta cardinalidad pero acotada (~100 keys totales en piloto), `scope_id` (UUID) NO se incluye como label — va a logs structlog en su lugar.

#### Scenario: Métricas BYOK aparecen en Prometheus

- **WHEN** el gateway sirve un request resuelto con scope=facultad, provider=Anthropic, tenant=X
- **THEN** `byok_key_usage_total{provider="anthropic", scope_type="facultad", tenant_id="X"}` SHALL incrementar en 1
- **AND** la métrica SHALL ser scrapeable en `http://localhost:9090/api/v1/query?query=byok_key_usage_total`

### Requirement: Métricas pedagógicas nuevas

El sistema SHALL exportar:

- `tests_ejecutados_total` (Counter) — labels: `tenant_id`, `comision_id`, `result` (pass/fail/error). Emitida desde tutor-service post-ejecución.
- `reflexion_completada_total` (Counter) — labels: `tenant_id`, `comision_id`. Emitida desde tutor-service post-evento CTR.
- `tp_generated_by_ai_total` (Counter) — labels: `tenant_id`, `materia_id`, `provider`. Emitida desde academic-service post-llamada exitosa.

#### Scenario: Tests ejecutados emite por result

- **WHEN** alumno corre 5 tests, 3 pasan y 2 fallan
- **THEN** `tests_ejecutados_total{result="pass"}` SHALL incrementar en 3
- **AND** `tests_ejecutados_total{result="fail"}` SHALL incrementar en 2

### Requirement: Dashboards Grafana incluyen panel BYOK

El dashboard `infrastructure/grafana/provisioning/dashboards/byok/byok-overview.json` SHALL crearse con paneles:

- Costo mensual acumulado por provider (timeseries con `sum by (provider)(byok_key_cost_usd_total)`)
- Top 10 keys por costo en los últimos 7d (table)
- Resolución p99 latencia (gauge)
- Distribución de scope_type resuelto (pie chart)
- Budget cap hits últimas 24h (stat con threshold rojo si > 0)

#### Scenario: Dashboard provisionado al levantar Grafana

- **WHEN** se ejecuta `make dev-bootstrap` y Grafana inicia
- **THEN** el dashboard `byok/byok-overview` SHALL aparecer en la UI sin import manual
