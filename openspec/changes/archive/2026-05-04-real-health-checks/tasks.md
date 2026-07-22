## 1. Helper compartido + tests

- [x] 1.1 Crear `packages/observability/src/platform_observability/health.py` con la dataclass `CheckResult(ok: bool, latency_ms: int, error: str | None)`.
- [x] 1.2 Implementar `check_postgres(engine, timeout=2.0)` con `SELECT 1` envuelto en `asyncio.wait_for`. Capturar todas las exceptions y traducirlas a `CheckResult(ok=False, ...)`.
- [x] 1.3 Implementar `check_redis(redis_url, timeout=2.0)` con `client.ping()` envuelto en `asyncio.wait_for` + cleanup garantizado de conexión via `try/finally`.
- [x] 1.4 Implementar `check_http(url, timeout=2.0, expect_status=200, cache_ttl=5.0)` con `httpx.AsyncClient`. Cache in-memory `dict[str, tuple[CheckResult, float_expires_at]]` por proceso. Cache hit retorna sin pegar; cache miss/expiry pega y refresca.
- [x] 1.5 Implementar `assemble_readiness(service: str, version: str, checks: dict[str, CheckResult], critical: set[str]) -> tuple[HealthResponse, int]`. Calcula status según matriz de D3 (ready/200, degraded/200, error/503). Missing critical key cuenta como failure.
- [x] 1.6 Exportar todo desde `packages/observability/src/platform_observability/__init__.py` con `__all__` actualizado.
- [x] 1.7 Crear `packages/observability/tests/unit/test_health.py` con 4 grupos de tests (mocks de DB engine, Redis client, httpx, monotonic clock):
  - `check_postgres`: success, failure, timeout.
  - `check_redis`: success, failure, timeout, cleanup en failure.
  - `check_http`: success, failure, timeout, cache hit dentro TTL, cache miss post-TTL, status code mismatch.
  - `assemble_readiness`: ready, degraded, error, missing critical key, error precedence sobre degraded.
- [x] 1.8 Verificar `uv run pytest packages/observability/tests/unit/test_health.py -v` pasa local. Ejecutar `make lint typecheck` y resolver hallazgos del helper + tests.

## 2. Adopción del helper en `api-gateway` + `identity-service`

- [x] 2.1 Migrar `apps/api-gateway/src/api_gateway/routes/health.py`:
  - Critical: `check_http(KEYCLOAK_JWKS_URL, cache_ttl=5.0)` → key `keycloak_jwks`.
  - Non-critical: `check_http(f"{ACADEMIC_SERVICE_URL}/health/live", cache_ttl=5.0)` → key `academic_service`.
  - Llamar `assemble_readiness("api-gateway", VERSION, checks, critical={"keycloak_jwks"})`.
- [x] 2.2 Crear `apps/api-gateway/tests/unit/test_health_ready.py` con mock del helper validando shape + status code en los 3 estados.
- [x] 2.3 Migrar `apps/identity-service/src/identity_service/routes/health.py`:
  - Critical: `check_http(f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}", cache_ttl=5.0)` → key `keycloak`.
  - `assemble_readiness("identity-service", VERSION, checks, critical={"keycloak"})`.
- [x] 2.4 Crear `apps/identity-service/tests/unit/test_health_ready.py`. (Hecho en `apps/identity-service/tests/test_health.py` — el servicio no usa subdir `unit/`.)
- [x] 2.5 Smoke local: levantar `api-gateway` + `identity-service` con Keycloak corriendo → ambos retornan `status: "ready"`. Apagar Keycloak → ambos retornan `error` + 503. **Verificado**: con stack completa, ambos `ready`. Tras `docker stop platform-keycloak` + 6s, ambos retornan `status=error`, HTTP 503, con `keycloak_jwks`/`keycloak` failing por `All connection attempts failed`.

## 3. Adopción en `academic-service` + `evaluation-service` + `analytics-service`

- [x] 3.1 Migrar `apps/academic-service/src/academic_service/routes/health.py`:
  - Critical: `check_postgres(academic_engine)` → key `academic_main_db`.
  - `assemble_readiness("academic-service", VERSION, checks, critical={"academic_main_db"})`.
- [x] 3.2 Crear `apps/academic-service/tests/unit/test_health_ready.py`. (Hecho en `tests/test_health.py` — el servicio no usa subdir `unit/` para health.)
- [x] 3.3 Migrar `apps/evaluation-service/src/evaluation_service/routes/health.py` con el mismo patrón (critical: `academic_main_db`). Aunque el servicio sea skeleton, mantener simetría (D5).
- [x] 3.4 Crear `apps/evaluation-service/tests/unit/test_health_ready.py`. (Hecho en `tests/test_health.py`.)
- [x] 3.5 Migrar `apps/analytics-service/src/analytics_service/routes/health.py`:
  - Critical: `check_postgres(ctr_store_engine)` → `ctr_store_db`.
  - Critical: `check_postgres(classifier_db_engine)` → `classifier_db`.
  - `assemble_readiness("analytics-service", VERSION, checks, critical={"ctr_store_db", "classifier_db"})`.
  - **`analytics-service` no instancia hoy engines async para `ctr_store`/`classifier_db`** (lee cross-base via adaptadores _Real/_Stub). Crear los engines locales al módulo de health (lazy + cached) reusando `ctr_store_url`/`classifier_db_url` del config. Si la URL está vacía (modo dev stub), el check devuelve `ok=False` con error explícito y la route retorna `error` + 503 — comportamiento correcto: en dev sin DBs reales, analytics-service NO está ready.
  - **Sin chequeo de Redis**: el servicio NO depende de Redis hoy (sacado del spec, ver delta de proposal/spec).
- [x] 3.6 Crear `apps/analytics-service/tests/unit/test_health_ready.py`. (Hecho en `tests/test_health.py`.)
- [x] 3.7 Smoke local: stack completa con `make dev-bootstrap` → los 3 retornan `ready`. Stop Postgres → los 3 retornan `error` + 503 dentro de 10s. **Verificado**: tras `docker stop platform-postgres` + 3s, `academic-service`, `evaluation-service`, `analytics-service` (+ `classifier-service`, `content-service` del bloque 4) marcan `error` + 503 con sus DB checks failed. Recovery <5s tras `docker start`.

## 4. Adopción en `tutor-service` + `classifier-service` + `content-service`

- [x] 4.1 Migrar `apps/tutor-service/src/tutor_service/routes/health.py`:
  - Critical: `check_redis(REDIS_URL)` → `redis`.
  - Non-critical: `check_http(f"{ACADEMIC_SERVICE_URL}/health/live", cache_ttl=5.0)` → `academic_service`.
  - Non-critical: `check_http(f"{AI_GATEWAY_URL}/health/live", cache_ttl=5.0)` → `ai_gateway`.
  - `assemble_readiness("tutor-service", VERSION, checks, critical={"redis"})`.
- [x] 4.2 Crear `apps/tutor-service/tests/unit/test_health_ready.py` cubriendo `degraded` cuando alguna non-critical falla. (Hecho en `tests/test_health.py`.)
- [x] 4.3 Migrar `apps/classifier-service/src/classifier_service/routes/health.py`:
  - Critical: `check_postgres(classifier_engine)` → `classifier_db`.
  - Critical: `check_redis(REDIS_URL)` → `redis` (consumer del CTR stream).
  - `assemble_readiness("classifier-service", VERSION, checks, critical={"classifier_db", "redis"})`.
- [x] 4.4 Crear `apps/classifier-service/tests/unit/test_health_ready.py`. (Hecho en `tests/test_health.py`.)
- [x] 4.5 Migrar `apps/content-service/src/content_service/routes/health.py`:
  - Critical: `check_postgres(content_engine)` → `content_db`.
  - Critical: query custom `SELECT 1 FROM pg_extension WHERE extname='vector'` (envolver en helper local `_check_pgvector` reusando timeout pattern del helper) → `pgvector_extension`.
  - `assemble_readiness("content-service", VERSION, checks, critical={"content_db", "pgvector_extension"})`.
- [x] 4.6 Crear `apps/content-service/tests/unit/test_health_ready.py` con caso "DB up, pgvector missing → 503". (Hecho en `tests/test_health.py`.)
- [x] 4.7 Smoke local: los 3 retornan `ready` con stack completa. Validar `tutor-service` retorna `degraded` cuando `ai-gateway` está caído pero Redis y `academic-service` están up. **Verificado**: tras matar `uvicorn ai_gateway` + esperar 6s (TTL cache HTTP), `tutor-service` retorna `status=degraded`, HTTP 200, con `ai_gateway.ok=false` y `redis.ok=true`/`academic_service.ok=true`. Exactamente lo que D3 promete: non-critical KO no rompe rotación.

## 5. Adopción en `governance-service` + `ai-gateway` + `integrity-attestation-service`

- [x] 5.1 Migrar `apps/governance-service/src/governance_service/routes/health.py`:
  - Critical: helper local `_check_prompt_filesystem(prompts_repo_path, default_prompt_version)` que valida `os.path.isfile(...)` y `os.access(..., os.R_OK)` → `prompts_filesystem`.
  - `assemble_readiness("governance-service", VERSION, checks, critical={"prompts_filesystem"})`.
- [x] 5.2 Crear `apps/governance-service/tests/unit/test_health_ready.py` con caso "prompt missing → 503". (Hecho en `tests/test_health.py`.)
- [x] 5.3 Migrar `apps/ai-gateway/src/ai_gateway/routes/health.py`:
  - Critical: `check_redis(REDIS_URL)` → `redis` (budget store).
  - Non-critical: probe `LLM_PROVIDER`. Si `mock` → siempre `CheckResult(ok=True, latency_ms=0)`. Si `anthropic` con API key → OK; sin key → KO (degraded). NO pega al provider externo (no hay endpoint público de health).
  - `assemble_readiness("ai-gateway", VERSION, checks, critical={"redis"})`.
- [x] 5.4 Crear `apps/ai-gateway/tests/unit/test_health_ready.py` con caso `LLM_PROVIDER=mock` (siempre ready) + caso real provider down (degraded). (Hecho en `tests/test_health.py`.)
- [x] 5.5 Migrar `apps/integrity-attestation-service/src/integrity_attestation_service/routes/health.py`:
  - Critical: helper local `_check_dir_writable(attestation_dir)` con `os.access(..., os.W_OK)` → `attestation_dir_writable`.
  - Critical: helper local `_check_file_readable(private_key_path)` con `os.access(..., os.R_OK)` → `private_key_readable`.
  - `assemble_readiness("integrity-attestation-service", VERSION, checks, critical={"attestation_dir_writable", "private_key_readable"})`.
- [x] 5.6 Crear `apps/integrity-attestation-service/tests/unit/test_health_ready.py`. (Hecho en `tests/test_health.py`.)

## 6. Validación operacional

- [x] 6.1 Actualizar `scripts/check-health.sh` para parsear `status` field además del HTTP status code. Output incluye nombre del check que falló cuando hay `degraded`/`error`. Probar en stack completa. **Verificado**: 12/12 services reportan `[OK]` con stack ready.
- [x] 6.2 Correr `make check-health` con stack completa → los 12 servicios retornan 200 con `status: "ready"` y `checks` poblado.
- [x] 6.3 Smoke "Postgres down": `docker stop <postgres-container>` → verificar que `academic-service`, `evaluation-service`, `analytics-service`, `classifier-service`, `content-service` retornan `error` + 503 dentro de 10s. ✓ Los 5 con sus checks failed correctamente identificados.
- [x] 6.4 Smoke "Redis down": `docker stop <redis-container>` → verificar que `tutor-service`, `classifier-service`, `ai-gateway` retornan `error` + 503. ✓ Los 3 nuevos services migrados marcan error. (`ctr-service` legacy reporta HTTP 503 con su `status=degraded` propio — comportamiento pre-existente, no tocado.)
- [x] 6.5 Smoke "non-critical degradation": apagar `ai-gateway` → verificar que `tutor-service` retorna `degraded` + 200 con `checks["ai_gateway"].ok=False`. ✓
- [x] 6.6 Smoke "Keycloak down": apagar Keycloak → verificar `api-gateway` e `identity-service` retornan `error` + 503. ✓
- [x] 6.7 Verificar que `ctr-service` NO fue tocado: `git diff apps/ctr-service/src/ctr_service/routes/health.py` debe ser vacío. ✓ verificado, diff vacío.
- [ ] 6.8 Correr `make lint typecheck test` completo → todo verde.
- [x] 6.9 Actualizar la sección "Brechas conocidas" del CLAUDE.md (entrada "Health checks reales solo en ctr-service") para reflejar que ahora 12/12 services tienen health real, removiendo la referencia a OBJ-16.
