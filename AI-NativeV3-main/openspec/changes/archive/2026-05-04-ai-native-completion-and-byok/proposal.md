## Why

El piloto UNSL tiene el núcleo AI-Native funcional (tutor socrático + CTR + classifier N4 + RAG + guardrails Fase A) pero faltan cinco piezas para cerrar el loop pedagógico institucional: el alumno no puede auto-validar su código contra tests, no se captura su reflexión metacognitiva al cierre del episodio, el docente arma TPs a mano sin asistencia IA, el admin institucional no tiene UI para auditar gobernanza cross-comisión, y todas las llamadas LLM usan claves globales por env var (sin separación por facultad/materia ni UX de admin para BYOK). Sin BYOK la demo institucional muestra "el admin le pide al sysadmin que rote la key" — UX inaceptable para defensa doctoral.

## What Changes

Cinco sub-cambios integrados que cierran el loop AI-Native sin tocar invariantes doctorales (CTR append-only SHA-256, RLS multi-tenant, reproducibilidad bit-a-bit, `ai-gateway` único proxy a LLMs):

- **Sandbox con test cases automáticos** (`web-student`): el alumno ejecuta tests definidos por el docente sobre su código en Pyodide. Los tests se almacenan como JSONB en `tareas_practicas`/`tareas_practicas_templates` (Opción A del explore). Tests "públicos" (visibles al alumno) y "hidden" (validación final). **El classifier IGNORA resultados de tests hidden** — no entran a features (preserva análisis longitudinal de la tesis).
- **Reflexión metacognitiva post-entrega** (`web-student`): modal opcional al cerrar episodio con preguntas (qué aprendiste / qué dificultad encontraste / qué harías distinto). Evento side-channel `reflexion_completada` al CTR. **No-bloqueante** — `EpisodioCerrado` nunca espera la reflexión. **NO entra al classifier** (preserva reproducibilidad bit-a-bit).
- **Generación asistida de TPs con IA** (`web-teacher`): docente describe en NL el TP que quiere → llamada al `ai-gateway` con `materia_id` → borrador de `enunciado` + `inicial_codigo` + `rubrica` + `test_cases` propuestos → docente edita y publica. Caller es `academic-service`. Audit log structlog `tp_generated_by_ai`.
- **Governance events con UI institucional** (`web-admin`): página solo-lectura con filtros facultad/materia/período sobre el endpoint existente `/api/v1/analytics/cohort/{id}/adversarial-events`. Sin tabla nueva. Workflow "marcar revisado" deferido a piloto-2.
- **BREAKING — BYOK multi-provider con scope facultad/materia** (`web-admin` + `ai-gateway`): admin configura keys de Anthropic/Gemini/Mistral con resolución jerárquica `materia → facultad → tenant → env fallback`. Storage en DB encriptada AES-GCM con `BYOK_MASTER_KEY` env var. Multi-provider simultáneo por scope (UNIQUE `(tenant_id, scope_type, scope_id, provider)`). Budget per-key. **Cambio cross-servicio**: `materia_id` se propaga en TODAS las llamadas al `ai-gateway` (tutor-service, classifier-service, content-service).

## Capabilities

### New Capabilities

- `sandbox-test-cases`: Ejecución de tests automáticos sobre código del alumno en sandbox Pyodide. Tipos de test (públicos/hidden), exposición filtrada por rol, evento CTR `tests_ejecutados`, contrato classifier (hidden no entran a features).
- `reflection-post-close`: Captura no-bloqueante de reflexión metacognitiva post-cierre de episodio. Modal UX, evento `reflexion_completada`, exclusión explícita del classifier.
- `tp-generator-ai`: Borrador asistido de TareaPractica vía LLM. Endpoint en academic-service, propagación de `materia_id`, audit log, prompt versionado.
- `governance-ui-admin`: Vista institucional solo-lectura de eventos de gobernanza (intentos adversos agregados) con filtros multi-jerarquía.
- `byok-multiprovider`: Bring-your-own-key con scope tenant/facultad/materia, multi-provider simultáneo (Anthropic/Gemini/Mistral/OpenAI), encriptación at-rest AES-GCM, resolver jerárquico, budget per-key, audit log de uso. Endpoints CRUD + rotate + revoke + test + usage. Master key rotation procedimental (runbook, no ADR).

### Modified Capabilities

- `metrics-instrumentation-otlp`: agregar métricas `byok_key_usage_total{provider,scope_type,scope_id}`, `byok_key_resolution_duration_seconds`, `tests_ejecutados_total{result}`, `reflexion_completada_total`, `tp_generated_by_ai_total`. Sin cambio de cardinality budget — se respetan los labels permitidos del spec actual.

## Impact

**Código afectado**:
- `ai-gateway`: reemplazar `get_provider()` por resolver jerárquico; agregar adapters Gemini + Mistral; aceptar `materia_id` en payload; tabla pricing per-model en `packages/contracts`.
- `tutor-service`, `classifier-service`, `content-service`: propagar `materia_id` en todas las llamadas al `ai-gateway`.
- `academic-service`: nueva columna `test_cases JSONB` en `tareas_practicas` y `tareas_practicas_templates` (migración Alembic + RLS); endpoint TP-gen IA; bulk-import incluye `test_cases`.
- `web-student`: integración Pyodide para correr tests; modal de reflexión post-close; UI de feedback de tests (público vs hidden).
- `web-teacher`: UI de wizard TP-gen IA; editor de test cases (drag-drop público/hidden, weight, name).
- `web-admin`: página BYOK keys (CRUD + rotate + revoke + test + usage); página Governance Events.
- `packages/platform-ops`: nuevo `crypto.py` con AES-GCM helper compartido (master key vía env).
- `packages/contracts`: tabla pricing per-model, schemas BYOK, schemas test_cases, schemas reflection.

**Migraciones nuevas**:
- `academic_main`: `tareas_practicas.test_cases JSONB DEFAULT '[]'`, `tareas_practicas_templates.test_cases JSONB DEFAULT '[]'`, tabla `byok_keys` (encriptada), tabla `reflections` (RLS, opcional — alternativa: solo CTR).

**APIs nuevas / modificadas**:
- `POST /api/v1/episodes/{id}/run-tests` (web-student → tutor-service)
- `POST /api/v1/episodes/{id}/reflection` (web-student → tutor-service)
- `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden={bool}` (filtrado por rol)
- `POST /api/v1/tareas-practicas/generate` (web-teacher → academic-service)
- `POST /api/v1/byok/keys`, `GET /api/v1/byok/keys`, `POST /api/v1/byok/keys/{id}/{rotate,revoke,test}`, `GET /api/v1/byok/keys/{id}/usage` (web-admin → ai-gateway o byok-service)
- `ai-gateway` payload: agregar `materia_id` (BREAKING para callers internos)

**Dependencias nuevas**:
- `cryptography` (Python) en `packages/platform-ops` para AES-GCM.
- SDK Gemini (`google-generativeai`) y Mistral (`mistralai`) en `ai-gateway`.

**ADRs nuevos en este epic**: ADR-033 (sandbox Pyodide-only), ADR-034 (test_cases JSONB), ADR-035 (reflexión privacy + exclusión classifier), ADR-036 (TP-gen caller academic-service + audit), ADR-037 (governance UI scope read-only), ADR-038 (BYOK encriptación AES-GCM + master key env), ADR-039 (BYOK resolver jerárquico materia→facultad→tenant), ADR-040 (`materia_id` propagation cross-service en ai-gateway payload).

**Invariantes preservadas** (verificadas por tests existentes + nuevos):
- CTR append-only SHA-256 (los nuevos eventos `tests_ejecutados` / `reflexion_completada` / `tp_generated_by_ai` se appendean, nunca mutan).
- RLS multi-tenant — tabla `byok_keys` y `test_cases` JSONB con `tenant_id` + policy.
- Reproducibilidad bit-a-bit del classifier (`classifier_config_hash`) — reflexión y test hidden quedan EXCLUIDOS de features.
- `ai-gateway` único proxy — Gemini/Mistral entran como adapters, ningún servicio llama al SDK directo.
- Prompt versionado — TP-gen y reflexión usan prompts en `ai-native-prompts/` con `prompt_version` en el payload.

**Esfuerzo total estimado**: ~3 semanas full-time. BYOK destraba TP-gen; sandbox + reflection + governance UI van en paralelo a BYOK.
