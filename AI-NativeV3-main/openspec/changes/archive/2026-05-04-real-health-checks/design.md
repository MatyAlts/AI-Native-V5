## Context

El piloto UNSL corre 12 servicios FastAPI en Kubernetes con `livenessProbe` (`/health/live`) y `readinessProbe` (`/health/ready`) wireadas en `infrastructure/helm/platform/templates/backend-services.yaml` (líneas 50-61). Hoy, 11 de los 12 endpoints `/health/ready` devuelven `200 {"status":"ready","checks":{}}` **hardcoded** desde `apps/<svc>/src/<svc_snake>/routes/health.py` (con un `# TODO: chequear dependencias reales` literal). Solo `ctr-service` chequea DB + Redis con timeout (`apps/ctr-service/src/ctr_service/routes/health.py:_check_db()` y `_check_redis()`).

Resultado operativo: un pod con Postgres caído o Redis muerto sigue marcado **Ready** y sigue recibiendo tráfico. K8s nunca lo saca de rotación. Para el piloto doctoral (4 meses, defensa cerca, comité busca historia operacional defendible), esto convierte fallas claras de infra en 500s opacos.

El contrato actual de `HealthResponse` (`packages/contracts`) ya tiene `checks: dict[str, ...]`. El cambio es: poblar ese dict con info real, mapear el agregado a HTTP status code apropiado, y hacerlo **una sola vez** en un helper compartido para que los 11 servicios lo consuman con ~30 LOC c/u en vez de re-implementar el patrón.

**Stakeholders:**
- Doctorando (Alberto Cortez): defensa pronto; necesita poder mostrar al comité que las probes son reales.
- Director de informática UNSL: opera el clúster en piloto; cualquier cambio en `/health` afecta sus alertas.
- Auditores externos del CTR: leen el runbook del piloto; "los servicios chequean sus deps" es claim que tiene que cerrar.

**Constraints:**
- BC-compatible obligatorio: `HealthResponse.checks` solo pasa de `{}` a poblado. Nada más cambia en el contrato.
- ROUTE_MAP del `api-gateway` no se toca: `/health/*` no se expone vía gateway, kubelet pega directo al pod.
- Helm chart no se toca: `periodSeconds: 5`, `timeoutSeconds: 3`, `failureThreshold: 3` ya existen — el helper tiene que respetar esos timings.
- `ctr-service` queda intocado (refactor a helper en separate change para no mezclar scope).

## Goals / Non-Goals

**Goals:**
- Los 11 servicios FastAPI sin health real consumen un único helper compartido (`packages/observability::health`) que les da `check_postgres`, `check_redis`, `check_http`, y `assemble_readiness`.
- `HealthResponse.checks: dict[str, CheckResult]` queda poblado con `{ok, latency_ms, error}` por dependencia.
- Status semantics estandarizadas: `ready`/`degraded`/`error` mapean a `200`/`200`/`503` respectivamente. K8s saca de rotación SOLO cuando hay critical KO.
- Per-service: matriz de dependencias críticas vs non-criticas explícita (definida en proposal).
- `make check-health` parsea tanto status code como `status` field (mejora colateral del script).
- Tests unitarios del helper cubren los 3 estados (ready/degraded/error) con mocks de DB/Redis/HTTP failure modes.

**Non-Goals:**
- Refactor de `ctr-service` para que use el helper (separate change — no mezclar scope que ya está estable).
- Split `/livez` vs `/readyz` (helm ya distingue `live`/`ready` vía paths; el contrato actual sirve).
- Métricas Prometheus derivadas de los checks (Epic 4 — Grafana dashboards — ya cerró ese frente).
- Health checks de los 8 workers CTR (no son HTTP services; corren `consume_partition()` en loop. Liveness vía k8s restart policy + lock de partición Redis).
- Cambiar `initialDelaySeconds`, `periodSeconds`, `failureThreshold` del helm.
- Validación end-to-end contra DB real en CI (los tests son unit con mocks; el smoke real lo cubre `make check-health` post-deploy).
- Health para frontends Vite (`web-*`): siguen siendo estáticos, no aplican.

## Decisions

### D1 — Ubicación del helper: `packages/observability/src/platform_observability/health.py`

**Decisión**: helper en `packages/observability`, no en `packages/platform-ops` ni en `packages/contracts`.

**Rationale**: `packages/observability` ya tiene `setup_observability()` que cada servicio llama con una import line en su `main.py`. El patrón "una import line para infra transversal" ya existe — replicarlo. `platform-ops` es para dominio pedagógico (privacy, CII, alerts), no infra. `contracts` solo tiene Pydantic models, no lógica async.

**Alternativas descartadas:**
- `packages/platform-ops`: dominio equivocado (es académico, no infra).
- `apps/<svc>/lib/health.py` por servicio: copia-pega que es exactamente lo que el helper resuelve.
- Standalone package `packages/health`: 1 archivo no justifica un workspace member.

### D2 — `CheckResult` con `(ok: bool, latency_ms: int, error: str | None)`

**Decisión**: dataclass simple. `latency_ms` siempre presente (incluso en error: hasta el timeout). `error` nullable, contiene la primera línea del exception message si `ok=False`.

**Rationale**: el patrón del CTR devuelve `dict[str, str]` con valores `"ok" | "<error>"` — pierde la latencia. Para Grafana dashboards y para debugging operacional vale más tener el timing. `latency_ms` como `int` (no `float`) porque la precisión sub-ms no aporta para health (timeouts de 2000ms).

**Alternativas descartadas:**
- `dict[str, str]` (patrón CTR actual): pierde latencia y obliga a parsear el string para distinguir tipo de error.
- `dict[str, Any]` con shape libre: rompe contrato y mypy strict.
- Pydantic model: overkill, no se serializa cross-service (vive intra-process).

### D3 — Status semantics: `ready`/`degraded`/`error` → 200/200/503

**Decisión**: `assemble_readiness(service, version, checks, critical: set[str])` calcula status así:

```
all critical OK + all non-critical OK    → "ready"     → 200
all critical OK + any non-critical KO    → "degraded"  → 200
any critical KO                          → "error"     → 503
```

**Rationale**: K8s readiness gate solo entiende 200 vs non-200. El proposal exige que k8s saque de rotación SOLO cuando una critical dep cae (caso "error"). Las non-critical que caen (ej. `tutor-service` ↔ `ai-gateway` en mock mode) NO deben sacar el pod de rotación — el servicio sigue funcional para los endpoints que no dependen de esa dep. El campo `status: "degraded"` da observabilidad humana sin afectar routing.

**Alternativas descartadas:**
- `degraded` → 503: rompe el funcionamiento del servicio cuando una dep no-crítica está caída.
- 4-estado (`ok`/`warning`/`degraded`/`error`): granularidad sin ROI defensible.
- Per-check criticality booleana en cada `CheckResult`: el helper terminaría conociendo qué es crítico y qué no, mezclando policy con mecanismo. La decisión de criticality es per-service, vive en `routes/health.py` de cada uno (en el `critical` set que pasa al `assemble_readiness`).

### D4 — TTL cache 5s para `check_http` (downstream HTTP checks)

**Decisión**: `check_http(url, timeout=2.0, expect_status=200, cache_ttl=5.0)` usa un dict in-memory `{url: (CheckResult, expires_at)}` por proceso. Si el cached result es fresh (`now < expires_at`), se devuelve sin pegar.

**Rationale**: `tutor-service` tiene 2 deps HTTP (academic-service + ai-gateway). Sin cache, cada probe (cada 5s) gasta 2 × hasta 2s = hasta 4s solo en HTTP — rompe el `timeoutSeconds: 3` del helm. Con cache 5s, en steady state cada probe pega 0 deps HTTP (todo en cache) y refresca solo cuando expira.

**Alternativas descartadas:**
- Sin cache: timeoutea la probe en cadenas downstream. Inviable.
- Cache global LRU vía `cachetools`: dep extra para 1 caso de uso. El dict simple alcanza.
- Cache de 1s o 10s: 5s es exactly `periodSeconds` — cada probe va a re-probar al menos una vez por ciclo.

### D5 — `evaluation-service` chequea Postgres pese a ser skeleton

**Decisión**: agregar real check de `academic_main` DB.

**Rationale**: el patrón uniforme vale más que la "honestidad" del skeleton. El servicio ya tiene `academic_main` declarado en `.env.example` y cuando alguien arranque su desarrollo (fase futura del piloto) ya tiene el health correcto. El costo marginal es 1 línea (`check_postgres(engine)`) — no se justifica romper la consistencia para ahorrar eso.

**Alternativas descartadas:**
- Skeleton-passthrough (`{"status":"ready","checks":{}}` hardcoded): rompe el invariante "todos los services con DB chequean DB", confunde a un dev futuro.
- Sacar `evaluation-service` del scope: contradice la simetría declarada en CLAUDE.md ("12 servicios activos").

### D6 — `identity-service` chequea Keycloak liveness via HTTP

**Decisión**: `check_http(f"{KEYCLOAK_URL}/realms/{realm}", cache_ttl=5.0)` — **critical**.

**Rationale**: aunque `identity-service` sea `/health` only by-design (auth via gateway + Casbin), si Keycloak cae afecta a TODA la auth de la plataforma. El servicio es el único point con ownership operacional sobre Keycloak (los demás solo consumen JWTs validados por gateway). Detectar el "Keycloak caído" desde el health del `identity-service` da una señal clara en dashboards. Costo: 1 chequeo HTTP cacheado, esencialmente gratis.

**Alternativas descartadas:**
- No chequear nada (mantener skeleton-passthrough): el servicio queda como "marca always-up" sin valor operacional.
- Mover el chequeo de Keycloak al `api-gateway`: el gateway ya lo chequea (JWKS endpoint en su lista de criticals). Tener doble cobertura es redundante pero útil — permite distinguir "gateway no llegó al JWKS" vs "Keycloak caído" con dos señales independientes.

### D7 — `content-service` chequea pgvector extension

**Decisión**: además de `SELECT 1`, chequea `SELECT 1 FROM pg_extension WHERE extname='vector'`. Falla → critical.

**Rationale**: el RAG del `content-service` es no-op sin pgvector. Detectar la extensión faltante en deploy temprano (vs descubrirlo cuando una query de retrieval falla) cierra una clase de bug típica en migraciones de DB. Es 1 query extra; vale la pena.

**Alternativas descartadas:**
- Solo `SELECT 1`: deja pasar el caso "DB up, pgvector missing" → falla silenciosa en runtime.
- Chequear todas las tablas de schema: overkill, las migraciones Alembic ya validan eso al boot.

### D8 — `governance-service` chequea filesystem read del prompt activo

**Decisión**: `os.path.isfile(f"{PROMPTS_REPO_PATH}/prompts/tutor/{default_prompt_version}/system.md")` — critical.

**Rationale**: si el prompt no es legible, `tutor-service` no puede abrir episodios (los `POST /api/v1/episodes` devuelven 500 — gotcha documentado en CLAUDE.md). Detectar prompt inaccesible al startup vs cuando el primer estudiante intenta abrir un episodio cierra una clase de bug operacional (montaje de PV faltante, permisos rotos).

**Alternativas descartadas:**
- Chequear todos los prompts del manifest: el `default_prompt_version` es el único que el tutor usa hoy.
- Re-leer el prompt y validarlo (parse YAML frontmatter): es trabajo que hace `PromptLoader`; duplicarlo en health complica.

### D9 — `integrity-attestation-service` chequea write+key, NO conectividad de stream

**Decisión**: 2 critical checks: `os.access(attestation_dir, os.W_OK)` + `os.access(private_key_path, os.R_OK)`. NO chequea Redis stream `attestation.requests`.

**Rationale**: el servicio es el sink de una cadena Ed25519 — si no puede escribir el JSONL ni leer la clave, está roto. La conectividad al stream NO es critical para readiness: el servicio puede arrancar sin Redis y el stream puede llenarse del lado del producer; cuando reconecta consume el backlog. K8s no debería sacar de rotación al sink por una caída temporal del bus.

**Alternativas descartadas:**
- Chequear Redis como critical: rompe el invariante "attestations son eventually consistent con SLO 24h" (RN-128).
- Chequear el último JSONL appended: side-effect en health, anti-pattern.

## Risks / Trade-offs

**[Riesgo 1] — Slowdown de probe en cadenas downstream HTTP**: si el cache se pierde (process restart) y todos los downstreams están lentos, la probe puede acercarse al `timeoutSeconds: 3` de helm.
→ **Mitigación**: `_DEP_TIMEOUT_SEC = 2.0` en cada `check_http` individual. `check_http` usa TTL cache 5s en steady state. `non-critical` HTTP failures degradan en vez de fallar (no rompen readiness). Dashboards Grafana ya muestran p95 latency de `/health/ready` (epic Grafana dashboards-provisioned cerró eso).

**[Riesgo 2] — Cold-start latency**: ~50ms extra al boot por chequeos paralelos en `asyncio.gather`.
→ **Mitigación**: aceptable. `initialDelaySeconds: 5` (liveness) y `15` (readiness) cubren con margen. Los chequeos corren paralelos, no secuenciales.

**[Riesgo 3] — Falsos positivos en dev local**: `make check-health` empieza a fallar para devs que arrancan solo un subset de servicios sin Postgres.
→ **Mitigación**: este NO es un bug — es comportamiento deseado y CLAUDE.md lo declara como gotcha. El script `scripts/check-health.sh` se actualiza para parsear `status` field además del status code, dando mensaje más claro ("Postgres caído" vs "service down").

**[Riesgo 4] — TTL cache desincroniza estado real**: dep recupera dentro del TTL window pero el cache reporta KO por hasta 5s.
→ **Mitigación**: 5s window es < `failureThreshold` × `periodSeconds` (3 × 5s = 15s) — k8s no actúa hasta 3 fallos consecutivos. Recovery se ve en la siguiente probe post-TTL.

**[Riesgo 5] — `keycloak` chequeo desde 2 servicios duplica carga**: `api-gateway` y `identity-service` ambos pegan a `{KEYCLOAK_URL}/realms/{realm}`.
→ **Mitigación**: con cache 5s y 2 services × 1 hit por TTL window = 2 hits cada 5s a Keycloak. Negligible vs cualquier carga real de auth. El valor de tener señales independientes (gateway path vs identity path) supera el costo.

**[Trade-off] — Helper compartido vs. patrón duplicado**: el helper centraliza ~150 LOC pero introduce un import path nuevo (`platform_observability.health`) que los 11 servicios deben adoptar. Si el helper tiene un bug, afecta a todos.
→ **Aceptado**: tests unitarios del helper cubren los 3 estados con mocks. La alternativa (duplicar el patrón en 11 archivos) es un anti-pattern documentado en SDD.

**[Trade-off] — `evaluation-service` skeleton chequea Postgres**: el servicio no usa la DB hoy; chequearla es "honestidad del skeleton" sacrificada por uniformidad.
→ **Aceptado**: el costo marginal es 1 línea, y cuando el servicio arranque ya tiene health correcto (ver D5).

**[Trade-off] — `ctr-service` queda fuera del refactor**: sigue con su `_check_db()` + `_check_redis()` propios, no consume el helper.
→ **Aceptado**: separate change deliberado. El CTR tiene su patrón validado y estable; mezclar refactor con la propagación a 11 services agranda blast radius sin necesidad.

## Migration Plan

**Fase 1 — Helper + tests (1 PR):**
1. Crear `packages/observability/src/platform_observability/health.py` con `CheckResult`, `check_postgres`, `check_redis`, `check_http`, `assemble_readiness`.
2. Crear `packages/observability/tests/unit/test_health.py` con mocks de DB/Redis/HTTP failure modes y los 3 estados.
3. Verificar que `make test` pase localmente y en CI.

**Fase 2 — Adopción por servicio (PRs por dominio, 4 PRs):**
- PR 2.1 — Plano académico: `api-gateway`, `identity-service`, `academic-service`, `evaluation-service`, `analytics-service`.
- PR 2.2 — Plano pedagógico: `tutor-service`, `classifier-service`, `content-service`.
- PR 2.3 — Plano governance/AI: `governance-service`, `ai-gateway`.
- PR 2.4 — Auditoría externa: `integrity-attestation-service`.

Cada PR:
1. Modifica `apps/<svc>/src/<svc_snake>/routes/health.py` para consumir el helper.
2. Agrega un test `apps/<svc>/tests/unit/test_health_ready.py` con mock del helper que valida shape + status code en los 3 estados.
3. Local smoke: `make dev-bootstrap && uv run uvicorn <svc>.main:app --port <port>` y `curl -s http://127.0.0.1:<port>/health/ready | jq`.

**Fase 3 — Smoke operativo:**
1. Actualizar `scripts/check-health.sh` para parsear `status` field además del status code.
2. Correr `make check-health` con la stack completa levantada — verificar todos retornan `status: "ready"` y `checks` poblado.
3. Test manual: `docker stop <postgres-container>` → verificar que los servicios afectados pasan a `status: "error"` + 503 dentro de 10s.

**Rollback:**
- Cada PR es independiente — si el helper tiene un bug que afecta a un servicio, revert ese PR específico (el endpoint vuelve al `{}` hardcoded).
- El helper en sí no se llama en hot path — solo desde `routes/health.py` cuando kubelet pega. Bug en helper no afecta tráfico de negocio.
- Si Fase 1 rompe CI: revert único, sin impacto en otros servicios (nadie consume el helper hasta Fase 2).

**No hay migración de DB, no hay cambio de contrato externo, no hay cambio de helm chart.**

## Open Questions

- **Cache TTL global vs per-URL**: el dict in-memory comparte TTL=5s para todas las URLs. Si en el futuro un downstream necesita TTL distinto (ej. `ai-gateway` con TTL=30s porque su provider HTTP es lento), refactorear. Por ahora 5s sirve para los 3 casos del piloto. **Resolución prevista**: dejar como está; revisar si emerge un caso operacional concreto.

- **`integrity-attestation-service` private key path**: el ADR-021 menciona que en piloto vive en infra institucional separada. El check de readability del key path asume que el path es absoluto y resuelve dentro del filesystem del pod. Si en piloto el key vive en un secret montado, el path cambia. **Resolución prevista**: el helper recibe el path por env var (`INTEGRITY_PRIVATE_KEY_PATH`); el deploy en infra institucional configura el path apropiado. Smoke del director de informática UNSL valida.

- **`make check-health` con un solo servicio caído**: hoy reporta exit 1 si cualquier servicio falla. Con health real, durante dev local con DB caída todos fallan — ¿el script debería distinguir "infra caída" vs "servicio individual crash"? **Resolución prevista**: out-of-scope para este change; abrir issue separado si emerge dolor.
