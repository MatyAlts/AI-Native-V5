# Grafana Dashboards — provisioning canónico del piloto

Path canónico (post `grafana-dashboards-provisioned` epic): este directorio.
Path legacy (archivado): `ops/grafana/_archive/`.

## Estructura

```
infrastructure/grafana/provisioning/
├── datasources/
│   └── datasources.yaml             # Prometheus, Loki, Jaeger
└── dashboards/
    ├── dashboards.yaml              # provider con foldersFromFilesStructure: true
    ├── README.md                    # este archivo
    ├── plataforma/                  # → folder Grafana "Plataforma"
    │   └── vision-general.json
    ├── ctr/                         # → folder Grafana "CTR"
    │   └── integridad.json
    ├── ai-gateway/                  # → folder Grafana "AI Gateway"
    │   └── costos-y-latencia.json
    ├── tutor/                       # → folder Grafana "Tutor"
    │   └── engagement.json
    └── classifier/                  # → folder Grafana "Classifier"
        └── kappa-y-coherencias.json
```

## Workflow de edición (anti-drift)

`allowUiUpdates: true` está activo en `dashboards.yaml` — podés iterar visualmente
en la UI sin commitear, **pero los cambios solo persisten al filesystem si los
exportás manualmente**:

1. Abrí Grafana en `http://localhost:3000` (admin/admin).
2. Editá el dashboard.
3. `Share → Export → Save to file` (o `Save dashboard JSON`).
4. Reemplazá el JSON commiteado en este directorio con el exportado.
5. PR con `git diff`.

⚠ **Si NO exportás**, los cambios viven solo en el `grafana_data:` volume del
container y se pierden cuando alguien hace `docker compose down -v`.

## Política de cardinalidad de labels

Las **labels permitidas** en métricas Prometheus emitidas por servicios del
piloto son una **lista cerrada**:

| Label | Cardinalidad esperada | Notas |
|-------|----------------------|-------|
| `tenant_id` | ~5 (piloto-1 single-tenant UNSL + dev) | UUID del tenant |
| `service_name` | 12 | Nombre del servicio Python |
| `event_type` | ~15 | Enum CTR (episodio_abierto, prompt_enviado, etc.) |
| `partition` | 8 | Sharding del CTR (0-7) |
| `provider` | ~3 | Proveedor LLM (mock, openai, anthropic) |
| `kind` | 2 | input / output (tokens) |
| `n_level` | 4 | N1-N4 (clasificación cognitiva) |
| `cohort` | ~30 | comision_id (alias) |
| `prompt_kind` | 5 | enum semántico del tutor |
| `template_id` | ≤ 50 | TareaPracticaTemplate UUIDs (capped) |
| `http_status_code` | ~10 | 2xx/4xx/5xx (auto-instrumentation) |
| `http_method` | 5 | GET/POST/PATCH/DELETE/PUT |
| `http_route` | ~50 por servicio | Path templates (auto-instrumentation) |

**Labels PROHIBIDAS** (rechazo en code review):

- `student_pseudonym` — explotaría con N=18 estudiantes × cohorte × template; además expone correlation cross-metric (privacidad).
- `episode_id` — UUID per-instancia, cardinality unbounded.
- `user_id` — idem.
- `prompt_id`, `attestation_id`, `classification_id` — idem.
- Cualquier UUID que no sea `tenant_id` o `template_id` (acotado a 50).

Las quartiles/alertas individuales por estudiante viven en el plano API
(`analytics-service` endpoints `/student/{id}/alerts`, `/cohort/{id}/cii-quartiles`)
NO en métricas Prometheus.

## Naming convention de métricas custom

- **Prefijo por servicio**: `ctr_*`, `ai_gateway_*`, `tutor_*`, `classifier_*`, `analytics_*`. Evita colisión con métricas auto-instrumentadas de OTel libraries.
- **Sufijos OTel-friendly**:
  - Counters: `*_total` (ej. `ctr_events_total`).
  - Histograms: `*_seconds` (timings) o `*_bytes`/`*_count` (sizes).
  - Gauges: nombre directo sin sufijo (ej. `ctr_worker_xpending_count`, `tutor_active_sessions_count`).

## Métricas custom emitidas (catálogo)

| Métrica | Tipo | Servicio | Labels permitidas | Estado |
|---------|------|----------|-------------------|--------|
| `ctr_events_total` | Counter | ctr-service | `tenant_id`, `event_type`, `partition` | ✓ emitido |
| `ctr_episodes_integrity_compromised_total` | Counter | ctr-service | `tenant_id` | ✓ emitido |
| `ctr_self_hash_compute_seconds` | Histogram | ctr-service | (none) | declarado, sin call site |
| `ctr_episode_duration_seconds` | Histogram | ctr-service | `tenant_id`, `comision_id` | declarado, sin call site |
| `ctr_worker_xpending_count` | UpDownCounter | ctr-service | `partition` | declarado, sin call site |
| `ctr_attestations_emitted_total` | Counter | ctr-service | (none) | declarado, sin call site |
| `ctr_attestations_pending_count` | UpDownCounter | ctr-service | (none) | declarado, sin call site |
| `tutor_response_duration_seconds` | Histogram | tutor-service | (none) | pendiente |
| `tutor_active_sessions_count` | Gauge | tutor-service | (none) | pendiente |
| `ai_gateway_tokens_total` | Counter | ai-gateway | `provider`, `kind`, `tenant_id` | pendiente |
| `ai_gateway_budget_remaining_usd` | Gauge | ai-gateway | `tenant_id` | pendiente |
| `ai_gateway_request_duration_seconds` | Histogram | ai-gateway | `provider` | pendiente |
| `ai_gateway_fallback_total` | Counter | ai-gateway | `reason` | pendiente |
| `ai_gateway_cache_hits_total` + `_requests_total` | Counter | ai-gateway | (none) | pendiente |
| `classifier_classifications_total` | Counter | classifier-service | `n_level`, `template_id`, `classifier_config_hash` | pendiente |
| `classifier_ccd_orphan_ratio` | Gauge | classifier-service | `cohort` | pendiente |
| `classifier_cii_evolution_slope` | Histogram | classifier-service | (none) | pendiente |
| `classifier_kappa_rolling` | Gauge | analytics-service | `window`, `cohort` | pendiente |
| `classifier_kappa_rolling_last_update_unix_seconds` | Gauge | analytics-service | `cohort` | pendiente |

Las métricas `pendiente` están declaradas en `apps/<svc>/metrics.py` o se
agregarán cuando cada servicio se instrumente. Los paneles que las grafican
quedan vacíos hasta entonces; eso NO rompe el dashboard ni la página.

## Métricas auto-instrumentadas

`FastAPIInstrumentor` (configurado en `packages/observability::setup_observability()`)
emite automáticamente:

- `http_server_requests_total{service_name, http_method, http_status_code, http_route}` — counter de requests HTTP.
- `http_server_duration_seconds_bucket{...}` — histogram de latencia HTTP.

Estas alimentan el panel "Error rate 5xx por servicio" del dashboard 1.

## Comandos operativos

```bash
# Empezar limpio (descarta volume Grafana viejo, fuerza re-provisioning):
docker compose -f infrastructure/docker-compose.dev.yml down -v
make dev-bootstrap

# Verificar que las métricas custom están saliendo:
curl -s http://localhost:8889/metrics | grep ctr_events_total

# Ver cardinalidad total de Prometheus (target: < 5000 series):
curl -s http://localhost:9090/api/v1/label/__name__/values | jq 'length'

# Listar series de una métrica específica para detectar cardinalidad sospechosa:
curl -s 'http://localhost:9090/api/v1/series?match[]=ctr_events_total' | jq '.data | length'
```

## Acceso

`http://localhost:3000` con `admin/admin` (cambiar en deploy real).

Los 5 dashboards aparecen en folders `Plataforma`, `CTR`, `AI Gateway`, `Tutor`,
`Classifier` después del primer arranque post-provisioning.
