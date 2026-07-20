## Why

Hoy 11 de los 12 servicios activos del piloto devuelven `{"service": "...", "status": "ready", "version": "0.1.0", "checks": {}}` **hardcoded** desde `apps/<svc>/src/<svc_snake>/routes/health.py` (cada uno con un `# TODO: chequear dependencias reales` literal en el código). Solo `ctr-service` chequea DB + Redis con timeout (`apps/ctr-service/src/ctr_service/routes/health.py:_check_db()` + `_check_redis()`).

Las consecuencias en prod son las que CLAUDE.md describe en *"Brechas conocidas"*: las `livenessProbe` y `readinessProbe` de Helm (`infrastructure/helm/platform/templates/backend-services.yaml` líneas 50-61) están bien wireadas — pegan a `/health/live` y `/health/ready` cada 10s/5s — pero como el endpoint devuelve 200 hardcoded, **un pod con DB caída o Redis muerto sigue marcado Ready y sigue recibiendo tráfico**. Eso transforma fallas claras de infra en 500s opacos, complica el debug del piloto durante los 4 meses, y rompe la historia operacional defendible ante el comité doctoral. Replicar el patrón del CTR cierra la brecha sin tocar el contrato del endpoint (`HealthResponse` ya tiene `checks: dict[str, str]` — hoy queda vacío).

## What Changes

- **Nuevo helper compartido `packages/observability/src/platform_observability/health.py`** con tres async helpers reutilizables y un assembler:
  - `check_postgres(engine, timeout=2.0) -> CheckResult` — `SELECT 1` con `asyncio.wait_for`.
  - `check_redis(redis_url, timeout=2.0) -> CheckResult` — `client.ping()` con cleanup de conexión.
  - `check_http(url, timeout=2.0, expect_status=200) -> CheckResult` — `httpx.AsyncClient` con TTL cache opcional (5s) para evitar slowdown de la probe en cadenas downstream.
  - `assemble_readiness(service, version, checks: dict[str, CheckResult], critical: set[str]) -> tuple[HealthResponse, int]` — calcula `status` (ready/degraded/error) y status code (200/200/503).
  - Modelo `CheckResult` con `ok: bool`, `latency_ms: int`, `error: str | None` (suple el formato granular que pide el epic).
- **Replicar el patrón de readiness real en los 11 servicios faltantes** consumiendo el helper. Un PR por servicio (o agrupado por dominio) — cada cambio toca solo `routes/health.py`, no la lógica de negocio:
  - `api-gateway`: Keycloak JWKS endpoint (HTTP cache 5s) — **critical**. Downstream `academic-service /health/live` — **non-critical** (degraded).
  - `identity-service`: **decisión documentada** (ver "Key decisions" abajo).
  - `academic-service`: `academic_main` DB — **critical**.
  - `evaluation-service`: ping a `academic_main` DB pese a ser skeleton — **critical**. Mantiene el patrón uniforme y prepara el servicio para cuando arranque.
  - `analytics-service`: `ctr_store` DB + `classifier_db` DB — **ambas critical** (cross-reads necesarios para los endpoints de progression/kappa/alerts). El servicio NO consume Redis hoy.
  - `tutor-service`: Redis (sessions + producer stream) — **critical**. Downstream `academic-service` (validación TP) y `ai-gateway` (LLM) con cache 5s — **non-critical** (degraded).
  - `classifier-service`: `classifier_db` DB + Redis (CTR consumer) — **ambas critical**.
  - `content-service`: `content_db` DB con probe extra `SELECT 1 FROM pg_extension WHERE extname='vector'` — **critical**. Sin pgvector el RAG no funciona.
  - `governance-service`: filesystem read de `{PROMPTS_REPO_PATH}/prompts/tutor/{default_prompt_version}/system.md` — **critical** (sin prompt no abre episodios).
  - `ai-gateway`: budget store Redis — **critical**. Probe `LLM_PROVIDER` resuelve (mock siempre `ok`, real prov = HTTP cache 5s) — **non-critical** (degraded).
  - `integrity-attestation-service`: filesystem write probe `os.access(attestation_dir, os.W_OK)` + private key file readable — **ambas critical**.
- **Status semantics estandarizadas** en `HealthResponse.status`:
  - `"ready"` = todos los critical OK + todos los non-critical OK → HTTP 200.
  - `"degraded"` = todos los critical OK + algún non-critical KO → HTTP 200 (k8s sigue ruteando tráfico).
  - `"error"` = algún critical KO → HTTP 503 (k8s marca NotReady, deja de rutear).
- **`check_http` con TTL cache de 5s** para mitigar slowdown en chequeos downstream encadenados (evita que la probe de `tutor-service` espere 2s × 2 dependencias × cada 5s).
- **NO se cambia `ctr-service`** — refactor para que use el helper compartido es **explicit non-goal** (separate change para no mezclar scope).
- **NO se introduce `/livez` vs `/readyz`** — se mantiene el split actual (`/health/live` simple + `/health/ready` con checks). El alias `/health` sigue apuntando a readiness.

## Capabilities

### New Capabilities

- `service-readiness`: Contrato uniforme de readiness para los 12 servicios FastAPI del monorepo. Define el shape del `HealthResponse` (con `checks: dict[str, CheckResult]` granular), las semantics de `status` (`ready`/`degraded`/`error`), el mapping a HTTP status codes (200/200/503), y la matriz de dependencias críticas vs no-críticas por servicio. Cubre tanto el endpoint público como el helper compartido en `packages/observability`.

### Modified Capabilities

(ninguna — no hay specs preexistentes en `openspec/specs/` y el contrato del `HealthResponse` actual queda BC-compatible: `checks` solo pasa de `{}` a poblado.)

## Impact

- **Código tocado** (≈11 archivos `routes/health.py` + 1 helper nuevo + tests):
  - Nuevo: `packages/observability/src/platform_observability/health.py` (~150 LOC).
  - Modificado: `apps/{api-gateway,identity-service,academic-service,evaluation-service,analytics-service,tutor-service,classifier-service,content-service,governance-service,ai-gateway,integrity-attestation-service}/src/*/routes/health.py` (~30-50 LOC c/u, casi toda la lógica vive en el helper).
  - Tests nuevos: `packages/observability/tests/unit/test_health.py` (mocks de DB/Redis/HTTP failure modes) + un test de readiness por servicio que valida el shape y el status code (cuenta como mínimo de regresión, no E2E real contra DB).
- **Sin migraciones**, sin cambios de contrato externo (frontends no consumen `/health`), sin cambios en ROUTE_MAP del `api-gateway` (los `/health` no se exponen vía gateway, los pega kubelet directo al pod).
- **Helm chart sin cambios**: las probes ya apuntan a `/health/live` (siempre 200) y `/health/ready` (ahora retorna 503 cuando hay falla) — exactamente lo que k8s espera.
- **Riesgo 1 — slowdown de probe**: chequeos downstream HTTP encadenados pueden timeoutear la probe (configurada `periodSeconds: 5` en helm). Mitigación: `check_http` usa TTL cache 5s y `non-critical` degrada en vez de fallar; `_DEP_TIMEOUT_SEC = 2.0` heredado del CTR limita cualquier check.
- **Riesgo 2 — cold-start latency**: ~50ms extra al boot por chequeos paralelos en `asyncio.gather`. Aceptable: los `initialDelaySeconds` de helm son 5s/15s.
- **Riesgo 3 — falsos positivos en dev local**: si un dev levanta solo `academic-service` sin Postgres, ahora el endpoint devuelve 503 en vez de 200. Esto es **deseado** — `make check-health` actualmente da falso positivo y CLAUDE.md lo documenta como gotcha. Mitigación: el script `scripts/check-health.sh` se actualiza para parsear `status` además de status code.
- **Acceptance criteria** (validado en specs/tasks):
  - `make check-health` retorna JSON con `checks` poblado por cada servicio.
  - Matar Postgres → servicios afectados retornan `status: error` + HTTP 503 dentro de 10s (≤ 2× `periodSeconds`).
  - Matar Redis → servicios Redis-dependientes retornan `degraded` (cache-only) o `error` (event-bus dependent).
  - Decisiones de `evaluation-service` e `identity-service` documentadas en spec + design.
  - Tests unitarios del helper cubren los 3 estados (ready/degraded/error) y los timeouts de cada check.
- **Decisión clave 1 — `evaluation-service`**: agregar real check de Postgres (no skeleton-passthrough). Razón: el patrón uniforme vale más que la "honestidad" del skeleton; cuando arranque el desarrollo del servicio ya tiene el health correcto. El servicio ya tiene `academic_main` declarado en `.env.example`, el ping es trivial.
- **Decisión clave 2 — `identity-service`**: agregar Keycloak liveness check (HTTP a `{KEYCLOAK_URL}/realms/{realm}` cache 5s) — **critical**. Razón: aunque el servicio sea `/health` only by-design (auth via gateway + Casbin descentralizado, NO es skeleton), el chequeo de Keycloak detecta el caso "Keycloak caído" que afecta a TODA la auth de la plataforma. Costo marginal cero, valor operacional alto.
- **Decisión clave 3 — Helper en `packages/observability`**: ubicación correcta porque es transversal y ya tiene `setup_observability()` análogo (mismo patrón "una import line por servicio"). Alternativa descartada: `packages/platform-ops` (es para privacy/CII/alerts — dominio pedagógico, no infra).
- **Out-of-scope explícito**:
  - Refactor de `ctr-service` para usar el helper compartido — separate change.
  - Split `/livez` vs `/readyz` — defer (helm ya distingue `live`/`ready` vía paths).
  - Métricas Prometheus derivadas de los checks (`ctr_episodes_integrity_compromised_total` ya existe; el resto lo cubre Epic 4 — Grafana dashboards).
  - Health checks de los 8 workers CTR (no son HTTP services — corren `consume_partition()` en loop). Su liveness se cubre por k8s restart policy + el lock de partición.
