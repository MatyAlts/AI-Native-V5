## Context

El piloto UNSL tiene el núcleo AI-Native funcional pre-defensa pero opera con **claves LLM globales por env var** (un solo proveedor por entorno) y le faltan cuatro piezas pedagógicas (sandbox de tests, reflexión metacognitiva, generación asistida de TPs, UI institucional de gobernanza). Esta epic cierra el loop AI-Native sin mover invariantes doctorales: CTR append-only SHA-256 (ADR-010), RLS multi-tenant (ADR-001), reproducibilidad bit-a-bit del classifier (ADR-003), `ai-gateway` como único proxy a LLMs.

**Stakeholders**:
- **Doctorando**: defensa (necesita demo institucional creíble — no "el sysadmin rota la key").
- **Docentes UNSL**: TP-gen + sandbox + reflexión.
- **Admin institucional**: BYOK + governance UI cross-comisión.
- **Comité doctoral**: trazabilidad de uso de IA en TPs (`created_via_ai`) y exclusión de reflexión de features (preserva `classifier_config_hash`).

**Constraints (no negociables)**:
- **Reproducibilidad bit-a-bit**: ni reflexión ni resultados de tests hidden pueden entrar al classifier. Verificable por `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py`.
- **CTR append-only**: nuevos eventos (`tests_ejecutados`, `reflexion_completada`, `tp_generated_by_ai`) se appendean — nunca mutan eventos previos.
- **`ai-gateway` único proxy**: ni tutor-service ni academic-service llaman SDKs de LLM directo. Gemini y Mistral entran como adapters dentro del gateway.
- **RLS por tenant** en toda tabla nueva con `tenant_id`. Verificado por `make check-rls` (gate de CI).
- **Privacy**: el contenido textual de la reflexión vive en el evento CTR pero el export académico lo redacta por default — opt-in vía `--include-reflections`.

## Goals / Non-Goals

**Goals**:

1. Admin institucional configura BYOK keys de Anthropic/Gemini/Mistral con scope `tenant|facultad|materia` desde web-admin.
2. Resolver jerárquico `materia → facultad → tenant → env fallback` decide la key efectiva en runtime.
3. Alumno corre tests Python sobre su código en Pyodide (cliente). Tests hidden quedan diferidos a piloto-2.
4. Alumno responde reflexión metacognitiva opcional al cierre del episodio. Modal no-bloqueante.
5. Docente genera borrador de TP con IA (academic-service caller, prompt versionado), edita y publica con flag `created_via_ai`.
6. Admin lee eventos de gobernanza cross-comisión con filtros facultad/materia/período.
7. Métricas BYOK + pedagógicas exportadas via OTLP, dashboard Grafana provisionado.

**Non-Goals (deferidos a piloto-2 con ADR redactado o stub)**:

- Sandbox server-side (`sandbox-service`) con tests hidden ejecutados fuera del cliente. Hoy solo Pyodide.
- Workflow "marcar evento como revisado" en governance UI (mutación + tabla `governance_event_reviews`).
- Editar reflexión post-envío (CTR es append-only — modelo es: respondés una vez o nunca).
- KMS / Vault para `BYOK_MASTER_KEY` (en piloto-1: env var; rotación por runbook).
- BYOK para OpenAI activo (env var existe pero adapter queda inactivo).
- Re-clasificación retroactiva con BYOK histórico — el classifier reproducible siempre usa el state del momento del episodio.
- Análisis de homogeneización de TPs generadas por IA (deuda pedagógica declarable, no técnica).

## Decisions

### D1 — Sandbox: Pyodide-only en piloto-1 (ADR-033)

Tests públicos corren client-side en Pyodide; tests hidden se almacenan en `tareas_practicas.test_cases JSONB` pero **no se envían al cliente** (filtrado en `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden={bool}` por rol). El backend NO ejecuta tests en piloto-1 — los hidden son metadata de docente para review manual o validación final delegada.

**Alternativa descartada**: híbrido Pyodide + subprocess server-side. Requiere `sandbox-service` nuevo (puerto 8013), container isolation (gVisor o equivalente para evitar escape via `os.system`), y operacionaliza una superficie de seguridad innecesaria pre-defensa. Si los docentes piden ejecución real de hidden, se desbloquea en piloto-2 con ADR específico de isolation.

**Trade-off aceptado**: el alumno con dev tools puede ver el código de tests públicos (no es secreto — sirven de spec). Tests hidden quedan opacos al cliente porque el endpoint los filtra; el alumno NO puede ejecutarlos.

### D2 — Reflexión: no-bloqueante + solo CTR (sin tabla `reflections`) (ADR-035)

El modal aparece post-cierre del episodio, es opcional y se puede saltar. El contenido textual viaja como payload del evento CTR `reflexion_completada` (append-only — un episodio cerrado acepta eventos posteriores; el chain_hash continúa).

**Sin tabla separada**: el exploration consideraba `reflections` en `academic_main`, pero el spec final cierra que el evento CTR es suficiente. Las queries del docente ("ver reflexiones de mis alumnos") se hacen vía analytics-service contra `ctr_store` (mismo patrón que `progression`).

**Privacy**: el alumno escribe texto libre — puede meter su nombre o info identificable. El export académico anonimizado redacta los 3 campos textuales por default; investigador con consentimiento explícito usa `--include-reflections` (audit log structlog `reflections_exported_with_consent`).

**Anti-regresión clave**: el classifier IGNORA todo evento `reflexion_completada`. Test nuevo en `apps/classifier-service/tests/unit/` que verifica que dos episodios idénticos (uno con reflexión, otro sin) producen el mismo `classifier_config_hash` y mismas features.

**Alternativa descartada**: reflexión bloqueante. Garantiza dato 100% pero produce respuestas basura por presión UX. Calidad > completitud para análisis longitudinal.

### D3 — TP-gen IA: caller es academic-service (ADR-036)

`academic-service` es dueño del dominio TP — agregar el endpoint ahí mantiene el árbol de dependencias limpio. Internamente: `academic-service → governance-service` (resuelve prompt activo `tp_generator/v1.0.0`) → `ai-gateway` (con `materia_id` en payload para resolución BYOK) → response como borrador. **El borrador NO se persiste**: el docente lo edita en frontend y dispara `POST /api/v1/tareas-practicas` tradicional con `created_via_ai=true`.

**Alternativa descartada**: caller en `governance-service`. Mezcla dominios (governance es dueño de prompts, no de TPs).

**Audit log**: structlog `tp_generated_by_ai` con `tenant_id`, `user_id`, `materia_id`, `prompt_version`, `tokens_input/output`, `latency_ms`, `provider_used`. Queryable via Loki para defensa doctoral. **No es evento CTR** — el CTR es del alumno; esto es gobernanza académica, va a structlog (mismo patrón que `kappa_computed`).

### D4 — Governance UI: solo lectura, sin mutaciones (ADR-037)

La página `/governance-events` del web-admin reusa el endpoint existente `/api/v1/analytics/cohort/{id}/adversarial-events` extendido con query params opcionales `facultad_id`, `materia_id`, `periodo_id` (sin breaking change — todos opcionales). Sin tabla nueva. Sin workflow "marcar revisado" (deferido).

**Cardinality**: a nivel facultad pueden ser miles de eventos por período. Pagination cursor-based (mismo patrón que `ProgressionView`). Export CSV con headers ASCII (cp1252-safe — ver gotcha de Windows en CLAUDE.md).

### D5 — BYOK storage: DB encriptada AES-GCM + master key env var (ADR-038)

Tabla `byok_keys` en `academic_main` (no proliferar bases lógicas; RLS ya está armado). Encriptación AES-GCM via helper compartido `packages/platform-ops/src/platform_ops/crypto.py` que usa `cryptography` lib. Master key en env var `BYOK_MASTER_KEY` (32 bytes base64).

**Por qué DB y no K8s SealedSecrets**: en UNSL no hay sysadmin dedicado al piloto. Que el admin academico rote keys desde la web es el req crítico de UX para defensa. SealedSecrets requiere kubectl/CLI — barrera de adopción.

**Master key rotation**: procedimiento operacional documentado en `docs/pilot/runbook.md` (no ADR). Steps: (1) generar nueva master, (2) leer todas las keys con la vieja master, (3) re-encriptar con la nueva, (4) commit DB transaction, (5) rotar env var, (6) restart ai-gateway. Downtime aceptable (~30s) en ventana coordinada.

**Alternativa descartada**: Vault/KMS. Infra extra para piloto-1. Migración a Vault en piloto-2 si compliance UNSL lo requiere.

### D6 — BYOK scope: multi-provider simultáneo por scope (ADR-039)

UNIQUE `(tenant_id, scope_type, scope_id, provider)` — una facultad PUEDE tener key Anthropic Y key Gemini activas a la vez. La elección entre providers la hace el caller (tutor-service usa Anthropic; classifier puede usar Gemini si quisiera — hoy ambos usan Anthropic, decisión per-feature).

**Por qué multi-provider y no "una por scope"**: el exploration recomendaba "una activa por scope" pero la realidad operacional es que features distintas tienen requirements distintos (latencia, costo, calidad). Que el admin pueda configurar Mistral para classifier (barato + rápido) y Anthropic para tutor (calidad pedagógica) es valor real.

**Resolver jerárquico** (ADR-040 cubre la propagación cross-service de `materia_id`):

```
Request al ai-gateway con (tenant_id, materia_id, provider, feature)
  ↓
1. Lookup byok_keys con (tenant_id, scope_type=materia, scope_id=materia_id, provider) WHERE revoked_at IS NULL
   ├─ HIT → desencriptar con BYOK_MASTER_KEY → usar
   └─ MISS ↓
2. Derivar facultad_id de materia_id (cache Redis `materia:{id}:facultad_id` TTL 1h)
   Lookup (tenant_id, scope_type=facultad, scope_id=facultad_id, provider)
   ├─ HIT → usar
   └─ MISS ↓
3. Lookup (tenant_id, scope_type=tenant, scope_id=NULL, provider)
   ├─ HIT → usar
   └─ MISS ↓
4. Env var legacy (ej. ANTHROPIC_API_KEY)
   ├─ HIT → usar (modo dev / fallback)
   └─ MISS → 503 "no provider available for {tenant}/{materia}/{provider}"
```

**Cache invalidation**: la jerarquía cambia raro (re-organización de planes de estudio). TTL de 1h es aceptable. Trigger Postgres opcional sobre `materias` que invalida el cache si la columna `plan_id` cambia (deferido si no hace falta).

### D7 — Budget per-key (ADR-038 cubre)

Cada key tiene `monthly_budget_usd` opcional. Si nulo → sin límite. Si seteado, hard-stop al alcanzarlo (tabla `byok_keys_usage` agrega tokens y costo por mes). Métrica `byok_budget_exceeded_total{key_id}` se incrementa por request rechazado.

**Pricing per-model**: tabla en config del `ai-gateway` (`packages/contracts/src/platform_contracts/ai_gateway/pricing.py`). Hardcoded para piloto-1 — pricing real del provider se actualiza con un PR. Soft fail: si no encontramos pricing del modelo usado, asumimos costo 0 y emitimos warning structlog `pricing_missing_for_model`.

### D8 — `materia_id` propagation cross-service (ADR-040, BREAKING para callers internos)

Todos los callers del `ai-gateway` (tutor-service, classifier-service, content-service) suman `materia_id` al payload. Hoy mandan solo `feature` + `tenant_id`. El cambio es BREAKING para callers internos pero **no afecta el contrato externo del gateway con frontends** (los frontends no pegan al gateway directo).

**Rollout**: en una sola release. El `materia_id` es opcional en el schema del gateway durante el periodo de migración (todos los callers lo agregan en el mismo PR atómico). Si el gateway recibe payload sin `materia_id` en runtime → fallback a scope=tenant (no se rompe, queda métrica `byok_key_resolution_total{resolved_scope="tenant_fallback_no_materia"}`).

## Risks / Trade-offs

**[Riesgo R1]** Master key compromise → todas las BYOK keys quedan expuestas.
**Mitigación**: master key vive solo en env var del ai-gateway pod (Helm secret). Acceso al pod requiere kubectl + RBAC. Audit log de accesos al pod via Loki. Rotación recomendada anual o tras incidente.

**[Riesgo R2]** Pricing-per-model desactualizado → cobramos mal a la facultad.
**Mitigación**: tabla de pricing con `last_updated_at`; warning structlog si > 90d sin update. Documentar en runbook que cada cambio de pricing del provider requiere PR.

**[Riesgo R3]** Pyodide tarda en cargar (~5-10s primer load) → UX pobre del sandbox.
**Mitigación**: lazy load via `import("pyodide")` solo cuando el alumno entra a `EpisodePage`. Spinner explícito "cargando entorno Python". Cache del browser cubre subsiguientes loads.

**[Riesgo R4]** Reflexiones con datos PII → leak en analytics queries.
**Mitigación**: el contenido vive en CTR (no en analytics). Endpoints de analytics que listan reflexiones agregan a nivel "número de reflexiones por comisión" — no exponen contenido sin pasar por export con `--include-reflections`. Test anti-regresión que valida que `GET /api/v1/analytics/.../reflections` no devuelve campos textuales.

**[Riesgo R5]** TP-gen produce TPs de baja calidad pedagógica → docente pierde tiempo editando.
**Mitigación**: el prompt versionado en `tp_generator/v1.0.0/system.md` itera con feedback de docentes. La metric `tp_generated_by_ai_total{materia_id}` mide adopción; si cae a 0 después de probar, sabemos que el prompt no sirve. Versión bumpeable sin redeploy.

**[Riesgo R6]** BYOK mal configurado → facultad sin key → tutor-service falla → episodios no avanzan.
**Mitigación**: fallback a env var del gateway (modo legacy). Health check del ai-gateway expone `byok_resolver_healthy` con conteo de tenants/facultades sin key configurada. Alerta Grafana si > 0 tenants sin key Y env fallback no seteado.

**[Riesgo R7]** Resolver lookup agrega latencia (~5-20ms por request) → degrada SSE del tutor.
**Mitigación**: cache Redis de la decisión final `resolved:{tenant_id}:{materia_id}:{provider}` TTL 5min. Histogram `byok_key_resolution_duration_seconds` con SLO p99 < 50ms. Si supera, considerar prefetch en background del tutor session.

**[Riesgo R8]** materia_id propagation rompe tests existentes (mocks del ai-gateway no esperan el campo).
**Mitigación**: `materia_id` opcional en el schema durante la transición. Tests viejos siguen pasando. Tests nuevos verifican que el campo llegue end-to-end. PR atómico que actualiza los 3 callers + gateway en simultáneo.

**[Trade-off T1]** No hay sandbox server-side en piloto-1 → tests hidden quedan como metadata sin ejecutar. **Aceptado**: el docente puede correr los tests hidden manualmente sobre los repos entregados, o validarlos en piloto-2 cuando se construya `sandbox-service`. La tesis no depende de ejecución automática de tests hidden.

**[Trade-off T2]** Reflexión opcional → tasa de respuesta esperada 60-70%. **Aceptado**: calidad > completitud. El análisis longitudinal del piloto puede correlacionar "respondieron reflexión" con "qué N-level alcanzaron" — la opcionalidad ES un dato.

**[Trade-off T3]** BYOK requiere admin con conocimiento de qué provider/modelo elegir. **Aceptado**: la página web-admin tiene defaults inteligentes (Anthropic + claude-sonnet-4-6) y tooltips explicativos. Para piloto-1 alcanza.

## Migration Plan

### Fase 1 — BYOK foundation (bloqueante para Fase 3)

**Steps**:
1. Migración Alembic en `academic_main`: tabla `byok_keys` + `byok_keys_usage` + RLS policies. `make check-rls` verifica.
2. Helper `crypto.py` en `packages/platform-ops` con tests unitarios (encrypt/decrypt + tampering detection).
3. Adapters Gemini + Mistral en `ai-gateway/providers/`. Tests con responses fixturadas.
4. Resolver jerárquico en `ai-gateway` con cache Redis + métricas. Tests de los 5 caminos (materia/facultad/tenant/env/none).
5. Endpoints CRUD + rotate + revoke + test + usage en `ai-gateway` (rutas `/api/v1/byok/*`). Casbin policies `byok_key:CRUD` para superadmin/docente_admin.
6. ROUTE_MAP del api-gateway: agregar `/api/v1/byok` → ai-gateway.
7. Propagación `materia_id` cross-service (PR atómico): tutor-service + classifier-service + content-service + ai-gateway schema.
8. UI BYOK admin en web-admin con HelpButton + PageContainer.
9. Smoke test: admin crea key → tutor-service la usa.

**Rollback**: feature flag `BYOK_ENABLED=false` desactiva el resolver y fuerza fallback a env var. Migración Alembic reversible (downgrade drops tablas).

### Fase 2 — Sandbox + Reflexión + Governance UI (paralelo)

Cada uno es independiente. Tres PRs en paralelo:

- **Sandbox**: migración test_cases JSONB → endpoint filter-by-role → web-teacher editor → web-student Pyodide → evento CTR `tests_ejecutados`.
- **Reflexión**: endpoint POST reflection → modal web-student → evento CTR `reflexion_completada` → exclusión classifier (test anti-regresión) → export redact por default.
- **Governance UI**: extender endpoint adversarial-events con filtros → página web-admin → CSV export → HelpButton.

**Rollback**: feature flags `SANDBOX_ENABLED`, `REFLECTION_MODAL_ENABLED`, `GOVERNANCE_UI_ENABLED` independientes. Migración Alembic reversible.

### Fase 3 — TP-gen IA (depende de Fase 1 BYOK)

1. Prompt en `ai-native-prompts/prompts/tp_generator/v1.0.0/system.md` + manifest update.
2. Endpoint `POST /api/v1/tareas-practicas/generate` en academic-service.
3. Audit log structlog `tp_generated_by_ai`.
4. Wizard en web-teacher.
5. Flag `created_via_ai` en tabla.

**Rollback**: feature flag `TP_GEN_ENABLED=false` oculta el wizard del frontend. Endpoint queda inactivo pero presente.

### Fase 4 — Métricas + Dashboards

Instrumentación de las 8 métricas nuevas + dashboard Grafana provisionado. No bloquea features pero es gate de observabilidad para defensa.

## Open Questions

1. **Pricing per-model**: ¿Hardcoded en `packages/contracts/.../pricing.py` o tabla DB editable por admin? Recomendación implícita: hardcoded en piloto-1 (PR para actualizar). Si admin quiere editar pricing en runtime, sube a piloto-2 con ADR.
2. **Rate limiting per-BYOK-key**: hoy el budget es por mes en USD. ¿Hace falta también rate limit (req/min)? Provider lo aplica naturalmente con 429. **Resolución por defecto**: confiar en el rate limit del provider; si UNSL lo pide, agregar en piloto-2.
3. **Visibilidad del costo por la facultad**: ¿el web-admin muestra costo acumulado a la facultad-admin, o solo al superadmin? Recomendación: solo superadmin en piloto-1 (privacidad inter-facultad). Endpoint usage filtra por scope_type permitido por rol.
4. **Migración futura a Vault/KMS**: el ADR-038 declara env var como decisión piloto-1. ¿Cuándo se gatilla la migración? Criterio cuantificable: si UNSL/compliance pide auditoría de master key access > 1x/año, o si más de 50 keys activas, migrar a Vault.
5. **Reflexión: ¿el docente las puede ver agregadas o nominales?** Recomendación: agregadas (medias y nubes de palabras por comisión). Nominal solo en export con consentimiento. Endpoint analytics nuevo se redacta junto con la implementación.
6. **TP-gen: ¿el alumno puede ver `created_via_ai=true`?** Decisión pedagógica: **sí** — transparencia del uso de IA es valor. Frontend muestra badge "Generada con IA" en `EpisodePage`. Confirmar con director de tesis antes de implementar.
