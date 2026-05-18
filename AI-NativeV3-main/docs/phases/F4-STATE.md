# Estado del repositorio — F4 completado

F4 es la fase de **hardening + observabilidad**: convierte la plataforma
funcional de F3 en una plataforma operable en producción. Agrega
trazabilidad completa de requests, rate limiting, verificación periódica
de integridad del CTR, dashboards con SLOs, y la vista docente agregada
que justifica el trabajo de todas las fases anteriores.

## Entregables F4

### 1. Package `platform-observability` — observabilidad unificada

`packages/observability/`:

- `setup_observability()` único para todos los servicios. Configura:
  - **OTel tracing** con OTLP gRPC exporter, resource incluyendo
    `service_name` + `deployment.environment`
  - **W3C Trace Context** propagation via header `traceparent` — los
    traces cruzan límites de servicio automáticamente
  - **Auto-instrumentación** de FastAPI (spans por request), httpx
    (propagación en llamadas outbound), SQLAlchemy (spans por query),
    Redis (spans por operación)
  - **structlog** con `trace_id` y `span_id` inyectados en cada log line
    → cada log es correlacionable con su trace
  - **Sentry** opcional para captura de errores críticos (no duplica
    tracing — solo errores)
- `get_tracer(__name__)` helper para crear spans manuales:
  ```python
  tracer = get_tracer(__name__)
  with tracer.start_as_current_span("classify_episode", attributes={"episode_id": str(eid)}):
      do_stuff()
  ```
- Fallback `_NoopTracer` si OTel no está instalado (tests offline)
- Tests: 6/6 pasan (config defaults, setup sin app, sin Sentry DSN,
  tracer manual, spans anidados, idempotencia)

### 2. Rate limiting en api-gateway

`apps/api-gateway/src/api_gateway/services/rate_limit.py` y
`middleware/rate_limit.py`:

- **Sliding window con Redis** — contador incrementado atómicamente,
  TTL igual al tamaño de ventana + margen
- **3 tiers por path**:
  - `/api/v1/episodes/*` → 30 req/min por principal (tutor + CTR son caros)
  - `/api/v1/retrieve` → 60 req/min (RAG es costoso pero barato vs LLM)
  - `/api/v1/classify_episode` → 20 req/min (feature cara)
  - Default → 300 req/min
- **Principal inference**: user_id → tenant_id → IP (fallback)
- **Rutas exentas**: health checks, metrics, docs
- **Fail-open si Redis cae**: no bloquear tráfico legítimo por incidente
  de infra
- Devuelve **429 con `Retry-After`** y headers `X-RateLimit-Limit` /
  `X-RateLimit-Remaining`
- Tests: 12/12 pasan (permite hasta el límite, rechaza tras exceder,
  principals independientes, todos los fallbacks de principal, path-based
  config, tiers separados)

### 3. CronJob de verificación de integridad del CTR

`apps/ctr-service/src/ctr_service/workers/integrity_checker.py`:

- `IntegrityChecker.run(limit, since)` recorre episodios cerrados
  (últimas 24h por default)
- Para cada episodio:
  1. Lee todos sus eventos ordenados por `seq`
  2. Recomputa `self_hash` y `chain_hash` desde `GENESIS_HASH`
  3. Si alguno no coincide con el persistido → marca el episodio como
     `integrity_compromised=true` + `estado="integrity_compromised"`
- `VerificationReport` con:
  - `episodes_scanned`, `episodes_valid`, `episodes_corrupted`
  - `new_compromised`: IDs recién detectados
  - `already_compromised`: IDs ya marcados antes (no se re-chequean)
  - `duration_seconds`
- **Exit code**: 0 si todo íntegro, 1 si detectó violaciones nuevas
- CLI: `python -m ctr_service.workers.integrity_checker --since-hours 24`

**Manifiesto K8s** (`ops/k8s/ctr-integrity-checker.yaml`):
- `CronJob` cada 6h con `concurrencyPolicy: Forbid`
- `ServiceAccount` dedicada con permisos mínimos
- `PrometheusRule` con 2 alertas:
  - `CTRIntegrityJobFailed` (el job crashea) → severity critical
  - `CTRIntegrityViolationsDetected` (exit code 1) → severity critical

Tests: 5/5 pasan, incluyendo detección de manipulación de payload.

### 4. Tests de integración con testcontainers (preparados para CI)

`apps/ctr-service/tests/integration/test_ctr_end_to_end.py`:

- 3 tests end-to-end con **Postgres 16 + Redis 7** reales via testcontainers
- Cubren:
  1. **RLS cross-tenant**: tenant B no puede ver episodios de tenant A
     aunque el SELECT no tenga filtro de tenant_id
  2. **Worker persiste con cadena correcta**: publish → worker consume →
     `chain_hash` del evento coincide con el `last_chain_hash` del episodio
  3. **Idempotencia por event_uuid**: publicar el mismo evento dos veces
     produce una sola fila persistida

- **Skip automático sin Docker** (`conftest.py` detecta `docker info`):
  en sandbox local se skipean; en CI (GitHub Actions con Docker) se
  corren.

### 5. Vista docente de analytics agregados

**Backend** — `apps/classifier-service/src/classifier_service/services/aggregation.py`:

- `aggregate_by_comision(session, comision_id, period_days)`:
  - Una query SQL con `group_by(appropriation)` + avg de las 5 coherencias
  - Una query SQL para timeseries con `date_trunc('day', classified_at)`
  - Promedios **ponderados por n** de cada bucket
  - Solo considera `is_current=true` (la reclasificación preserva
    históricos con `is_current=false` pero no afectan stats actuales)
- `GET /api/v1/classifications/aggregated?comision_id={id}&period_days={n}`
- Tests: 4/4 pasan (vacío → ceros, cuenta por tipo, avg ponderado por n,
  timeseries agrupa por día)

**Frontend** — `apps/web-admin/src/pages/ClasificacionesPage.tsx`:

- Agregada al `Router.tsx` como nueva ruta "Clasificaciones N4"
- Selector de período (7/30/90 días)
- 3 cards de distribución con colores/emojis por tipo
- 3 medidores de promedio (CT, CCD, CII estabilidad)
- Gráfico de barras apiladas por día (verde reflexiva, amarillo
  superficial, rojo delegación)
- Estados: loading, error con hint de debug, empty state
- Consume el endpoint real (reemplazó los mocks del turno anterior)

### 6. Dashboards Grafana con SLOs

`ops/grafana/dashboards/platform-slos.json`:

- **Row 1 — Tutor latency**: P50/P95/P99 de `/episodes/*/message` con
  thresholds visuales (verde < 3s, amarillo < 8s, rojo > 8s)
- **Row 2 — AI Gateway**: tokens consumidos por feature, cache hit
  ratio (SLO: > 30% en clasificación)
- **Row 3 — CTR**: eventos persistidos por partición, episodios
  `integrity_compromised_total` (objetivo: 0), DLQ size
- **Row 4 — Clasificación N4**: distribución por tipo (pie 7 días) +
  tendencia de apropiación reflexiva como % del total
- **Row 5 — API Gateway**: requests 429 por tier + error rate 5xx con
  SLO de < 1%

### 7. PrometheusRules con SLO alerts

`ops/prometheus/slo-rules.yaml`:

- **Tutor**: `TutorFirstTokenLatencyP95High` (warning, >3s 10min) y
  `TutorFirstTokenLatencyP99Critical` (critical, >8s 5min)
- **CTR**: `CTRNewIntegrityCompromised` (critical), `CTRDLQGrowing`
  (warning), `CTRWorkerBacklog` (warning, stream length > 1000)
- **AI Gateway**: `AIBudgetNearExhausted` (warning a 80%)
- **Classifier**: `ClassifierBacklogGrowing` (cerrados - clasificados > 10/h)
- **Errores generales**: `ServiceErrorRateHigh` (error rate > 1%)

## Suite completa — 172/172 tests pasan

```
packages/contracts/tests/test_hashing.py .......................... 7
packages/observability/tests/test_setup.py ....................... 6  ← nuevo F4
apps/academic-service/tests/unit/test_schemas.py ................. 10
apps/academic-service/tests/integration/test_casbin_matrix.py .... 23
apps/content-service/tests/unit/*.py ............................. 24
apps/ctr-service/tests/unit/*.py ................................. 19  ← +5 integrity
apps/governance-service/tests/unit/*.py ........................... 7
apps/ai-gateway/tests/unit/*.py .................................. 13
apps/tutor-service/tests/unit/*.py ............................... 12
apps/classifier-service/tests/unit/*.py .......................... 39  ← +4 aggregation
apps/api-gateway/tests/unit/*.py ................................. 12  ← nuevo F4 rate limit
──────────────────────────────────────────────────────────────────────
                                                                 172

Delta F4: +27 tests nuevos
```

Tests de integración adicionales (3) escritos para CI con Docker — se
skipean automáticamente en entornos sin Docker.

## Propiedades críticas preservadas y añadidas

1. **Trazabilidad end-to-end**: request HTTP entra al api-gateway → se
   propaga `traceparent` a todos los servicios internos → cada log line
   lleva `trace_id` y `span_id` → un solo query en Jaeger muestra el
   request completo pasando por tutor → content → ai-gateway → ctr.

2. **Defensa en profundidad contra abuso**: rate limit en el gateway
   (antes de siquiera llegar al tutor), budget en el ai-gateway
   (antes de llamar al LLM), filtro doble en retrieval (RLS +
   `comision_id` explícito).

3. **Detección activa de manipulación del CTR**: el integrity checker
   corre cada 6h y marca automáticamente los episodios con cadena rota.
   No depende de que alguien abra la UI para descubrirlo.

4. **Visibilidad docente**: el endpoint agregado + la UI hacen que el
   docente pueda ver la distribución N4 de su comisión a diferencia de
   F3 donde solo se veía la clasificación individual de un estudiante.

5. **SLOs explícitos y monitoreados**: los thresholds están en los
   dashboards y en las PrometheusRules. No hay "definición informal" de
   qué es aceptable — está en código.

## Cómo correr F4 localmente

```bash
# Suite completa (incluyendo lo nuevo de F4)
cd /home/claude/platform
EMBEDDER=mock RERANKER=identity STORAGE=mock LLM_PROVIDER=mock \
PYTHONPATH=apps/academic-service/src:apps/content-service/src:apps/ctr-service/src:apps/governance-service/src:apps/ai-gateway/src:apps/tutor-service/src:apps/classifier-service/src:apps/api-gateway/src:packages/contracts/src:packages/test-utils/src:packages/observability/src \
  python3 -m pytest \
    apps/academic-service/tests/ \
    apps/content-service/tests/unit/ \
    apps/ctr-service/tests/unit/ \
    apps/governance-service/tests/unit/ \
    apps/ai-gateway/tests/unit/ \
    apps/tutor-service/tests/unit/ \
    apps/classifier-service/tests/unit/ \
    apps/api-gateway/tests/unit/ \
    packages/contracts/tests/ \
    packages/observability/tests/

# Esperado: 172 passed

# Tests de integración (requieren Docker)
docker info  # verificar que Docker está corriendo
python3 -m pytest apps/ctr-service/tests/integration/

# Ejecutar integrity checker ad-hoc
python3 -m ctr_service.workers.integrity_checker --since-hours 24
```

## Qué queda para F5+

- **Editor Monaco + ejecución Python sandbox**: hoy el web-student usa
  textarea plano. Integrar Monaco + Pyodide client-side para ejecutar
  Python en el navegador sin backend.
- **Canary deployments + rollback automático**: Helm chart existe en F0;
  falta agregar análisis automático (Argo Rollouts o Flagger).
- **Autenticación Keycloak real en frontends**: hoy todos los frontends
  usan headers X-* de dev. F5 agrega el flow OIDC completo.
- **Migración de cada servicio al `platform-observability` unificado**:
  los services conservan `observability.py` propios; migrarlos reduce
  duplicación y garantiza que todos inicialicen OTel del mismo modo.
- **Tests de integración para los otros servicios**: hoy solo ctr-service
  tiene tests con testcontainers. Replicar el patrón para
  content-service (RAG con pgvector real), tutor-service (flujo completo
  con todos los services), classifier-service.
- **Exportación automática de datos a investigadores**: endpoints que
  exporten eventos CTR y clasificaciones con pseudonimización para
  análisis externos (aporte tesis).

## Próxima fase — F5 (meses 14-15): Multi-tenant + producción

- Onboarding de nuevos tenants (creación de realm Keycloak + seed de DB)
- Migración de API keys de LLM provider a secretos por tenant
- Feature flags por tenant (active_configs.yaml refinado)
- Auditoría de accesos sospechosos
- Backup/restore automáticos de las 3 bases
- Privacy controls: export de datos de un estudiante, derecho al olvido
