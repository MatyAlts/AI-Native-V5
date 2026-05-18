# Exploration — AI-Native completion + BYOK multi-provider

**Estado**: explore (NO hay proposal/specs/design todavía)
**Fecha**: 2026-04-30
**Topic key engram (futuro)**: `sdd/ai-native-completion-and-byok/explore`

## Resumen ejecutivo

Cinco sub-cambios que **cierran el loop AI-Native** del piloto sin tocar invariantes doctorales (CTR append-only SHA-256, RLS multi-tenant, reproducibilidad bit-a-bit, `ai-gateway` único proxy a LLMs):

1. **Sandbox + test cases automáticos** (`web-student`) — el alumno valida su código con assertions definidas por el docente
2. **Reflexión post-entrega** (`web-student`) — cuestionario metacognitivo opcional al cierre del episodio
3. **Generación asistida de TPs con IA** (`web-teacher`) — docente describe en NL → AI propone borrador → docente edita y publica
4. **Governance events con UI institucional** (`web-admin`) — auditoría cross-comisión de intentos adversos y eventos de gobernanza
5. **BYOK multi-provider con scope facultad/materia** (`web-admin` + `ai-gateway`) — admin configura keys de Gemini/Anthropic/Mistral con resolución jerárquica

El #5 es el más complejo y bloqueante para que el #3 sea utilizable en producción institucional. El orden de implementación sugerido invierte tu lista original.

---

## Hallazgos del código actual (resumen)

| Punto | Estado real | Implicación para el explore |
|---|---|---|
| `ai-gateway` provider/key | Env vars globales (`anthropic_api_key`, `openai_api_key`); `MockProvider` o `AnthropicProvider` hardcoded por `get_provider()` | El BYOK no es greenfield: hay que reemplazar `get_provider()` por un resolver con scope |
| `tenant_secrets.py` (platform-ops) | Resolver `(tenant_id, provider)` con K8s mount pattern `/etc/platform/llm-keys/{tenant_id}/{provider}.key` ya existe — pero **el ai-gateway aún NO lo usa** | El resolver de BYOK con scope debería extender este patrón, NO empezar de cero |
| `TareaPractica` columnas | 13 columnas operativas (`enunciado`, `inicial_codigo`, `rubrica` JSONB, etc.). **No hay `test_cases`** | Hay que agregar columna nueva. Decision: ¿columna JSONB en TP/Template, o tabla separada? |
| `EpisodioCerrado` flow | `POST /api/v1/episodes/{id}/close` con `reason`. Emite evento al CTR + borra sesión Redis. **No hay hook post-close** | Reflexión va como evento side-channel `reflexion_completada`, NO como mutación del payload `EpisodioCerrado` |
| Adversarial events | Endpoint `/api/v1/analytics/cohort/{id}/adversarial-events` ya existe en `analytics-service` con `aggregate_adversarial_events()` | Web-admin reusa el patrón, agrega filtros institucionales (facultad/materia/período) |
| Encriptación at-rest | **NO HAY** helper AES-GCM/Fernet en `packages/`. `tenant_secrets.py` lee plaintext de filesystem | Si BYOK guarda en DB, hay que sumar `cryptography` lib + helper compartido. Si seguimos con K8s SealedSecrets, no hace falta — pero la UX de admin se complica |
| Jerarquía Facultad | `Materia → Plan → Carrera → Facultad` (3 JOINs). `Materia` NO tiene `facultad_id` denormalizado | El resolver del BYOK necesita cache (Redis: `materia:{id}:facultad_id`) o columna denormalizada |
| Payload AI-gateway | Solo recibe `feature` (tutor/classifier) + `tenant_id`. **No recibe `materia_id`** | Cambio cross-servicio: todos los callers (tutor-service, classifier-service) tienen que propagar `materia_id` |

---

## Sub-cambio 1 — Sandbox con test cases automáticos

### Decisión arquitectónica clave (*)

**Sandbox client-side (Pyodide) vs server-side (subprocess Python)**.

| Dimensión | Pyodide (client) | Subprocess (server) |
|---|---|---|
| Latencia | ~0ms (ya cargado) | ~200-500ms por exec |
| Costo infra | $0 | requiere worker pool + cgroups + isolation |
| Test cases "hidden" | **Imposible** — el código del test se manda al cliente | Trivial — el test corre server-side |
| Bibliotecas Python avanzadas (pandas, numpy) | Sí, vía `micropip` | Sí, nativamente |
| Detección de uso de imports prohibidos | Cliente lo puede bypassear | Auditable |
| Trazabilidad CTR | Igual (el evento se emite desde el cliente igual) | Auditable centralmente |

**Recomendación**: **híbrido**. Tests "públicos" (visibles al alumno, sirven de spec) corren en Pyodide. Tests "hidden" (validación final, ocultos al alumno) corren server-side en un nuevo `sandbox-service` (puerto 8013). El docente marca por test si es público o hidden.

Esto requiere ADR — es una decisión que afecta seguridad académica.

### Endpoints

- `POST /api/v1/episodes/{id}/run-tests` (web-student → tutor-service o sandbox-service nuevo)
  - Body: `{ code: string }`
  - Response: `{ test_results: [{ id, name, public, passed, output, expected, error_message }] }`
  - Internamente: corre tests públicos en cliente (Pyodide ya tiene el código), y los hidden vía subprocess
- `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden={bool}` — filtrado por rol; estudiante nunca ve `include_hidden=true`

### Tablas / migraciones

**Opción A** — columna JSONB en `tareas_practicas` (y `tareas_practicas_templates`):
```
test_cases JSONB DEFAULT '[]'::jsonb
-- shape: [{ id, name, type, code, expected, public, weight }]
```

**Opción B** — tabla separada `test_cases`:
```
test_cases (
  id UUID PK,
  tarea_id UUID FK tareas_practicas(id),
  name TEXT,
  type ENUM('stdin_stdout', 'pytest_assert'),
  code TEXT,                  -- o stdin si type=stdin_stdout
  expected TEXT,              -- o expected_stdout
  is_public BOOLEAN,
  weight INT,
  created_at TIMESTAMP,
  tenant_id UUID              -- RLS obligatoria (ADR-001)
)
```

**Recomendación**: **Opción A** (JSONB). Versioning de TP ya copia toda la estructura — esto va con el flujo. Si después se necesita query individual de test cases (ej. metricas de "qué test rompe más"), migración a tabla separada es directa.

### Eventos CTR nuevos

- **`tests_ejecutados`** (N3 o N4 según labeler):
  ```json
  {
    "test_count_total": 5,
    "test_count_passed": 3,
    "test_count_failed": 2,
    "tests_publicos": 3,
    "tests_hidden": 2,
    "chunks_used_hash": "...",  // propagado del último prompt_enviado
    "ejecucion_ms": 124
  }
  ```
  - Decision: ¿la lista detallada de tests va al payload o solo conteos? Recomiendo **solo conteos** — la lista expandiría mucho el evento y la tesis no la necesita para análisis longitudinal.

### ADRs a redactar

- **ADR-033**: Sandbox híbrido Pyodide + subprocess server-side. Justificación: tests hidden requieren server-side; tests públicos no necesitan latencia de red.
- **ADR-034**: Decisión columna JSONB vs tabla — incluir el threshold a partir del cual migra a tabla.

### Riesgos / open questions

- ¿El subprocess server-side requiere container isolation (gVisor/firecracker)? Subprocess pelado en Python tiene escape via `import os; os.system(...)` aunque limites RAM/CPU. Decisión de seguridad real.
- ¿Cómo se versiona el cambio de `test_cases` después de TP `published`? Hoy `published` = inmutable. ¿Editar test_cases bumpea versión o se permite hot-fix?
- Flaky tests (timing-dependent) — ¿hay seed determinístico para tests random?

### Esfuerzo

**M** si solo Pyodide cliente. **L** si se hace híbrido + nuevo `sandbox-service`. Recomiendo arrancar con Pyodide-only (M) y hacer el servidor en una segunda iteración cuando se confirme que los profesores piden tests hidden.

---

## Sub-cambio 2 — Reflexión post-entrega

### Decisión arquitectónica clave (*)

**Bloqueante vs no-bloqueante al cierre**.

- **Bloqueante**: el modal aparece y no se puede salir hasta completar. Garantiza dato 100% pero tiene coste UX (alumno frustrado puede dejar respuestas basura).
- **No-bloqueante**: aparece pero se puede cerrar. Tasa de respuesta menor, pero respuestas más sinceras.

**Recomendación**: **no-bloqueante con recordatorio**. El modal aparece post-cierre, el alumno lo puede saltar; el `web-student` muestra un recordatorio "te faltan N reflexiones" en su home si hay episodios cerrados sin reflexión. La tasa de respuesta esperada cae al 60-70%, pero la calidad sube.

Esto es decisión pedagógica + análisis estadístico — va en ADR.

### Endpoints

- `POST /api/v1/episodes/{id}/reflection`
  - Body: `{ difficulty_perception: 1-5, strategy: string, ai_usage: string, what_would_change: string, confidence: 1-5 }`
  - Response: `{ reflection_id, episode_id, created_at }`
  - Idempotente por `(episode_id, student_id)` — UNIQUE constraint
- `GET /api/v1/episodes/{id}/reflection` (alumno propio + docente de la comisión)
- `GET /api/v1/students/me/pending-reflections` (web-student home)

### Tablas / migraciones

DB destino: **`academic_main`** (no `ctr_store` — la reflexión es metadata pedagógica, no evento auditable inmutable).

```sql
CREATE TABLE reflections (
  id UUID PRIMARY KEY,
  episode_id UUID NOT NULL,
  student_pseudonym UUID NOT NULL,
  tenant_id UUID NOT NULL,
  difficulty_perception SMALLINT CHECK (difficulty_perception BETWEEN 1 AND 5),
  strategy TEXT,
  ai_usage TEXT,
  what_would_change TEXT,
  confidence SMALLINT CHECK (confidence BETWEEN 1 AND 5),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (episode_id, student_pseudonym)
);
-- RLS policy: tenant_id-aware (ADR-001)
-- INDEX (student_pseudonym, created_at) para query "mis reflexiones"
```

### Eventos CTR

**`reflexion_completada`** (N-level a definir — probablemente N2):
```json
{
  "reflection_id": "uuid",
  "episode_id": "uuid",
  "completed_within_seconds": 145,  // delta entre EpisodioCerrado y POST reflection
  "all_fields_filled": true
}
```

NO se mete el contenido de la reflexión al CTR — la reflexión es texto libre del alumno; meterla rompe pseudonimización (alumno puede escribir su nombre en `strategy`). El CTR registra solo metadata booleana + timing.

### ADRs a redactar

- **ADR-035**: Reflexión post-entrega — diseño no-bloqueante + decisión de almacenar contenido en `academic_main` (no `ctr_store`) por privacidad.

### Riesgos / open questions

- ¿La reflexión es input opcional al clasificador N4? Si lo es, **rompe reproducibilidad** (mismo episodio re-clasificado con/sin reflexión da output distinto). Recomendación: **NO meter al classifier** — quedarse con la reflexión como metadato auxiliar para análisis longitudinal del docente, no para el clasificador.
- ¿Editable después? Recomiendo: **sí dentro de 24h** del cierre, después no. UPDATE solo de los 5 campos, nunca DELETE. `updated_at` separado de `created_at` para auditoría.
- ¿El docente puede ver las reflexiones nominales o solo agregadas? Decision pedagógica + privacidad — recomiendo **agregadas** (medias por comisión) para evitar profile-by-profile.

### Esfuerzo

**S**. Modal + tabla + 2-3 endpoints + RLS policy + 1 evento CTR.

---

## Sub-cambio 3 — Generación asistida de TPs con IA

### Decisión arquitectónica clave (*)

**¿Quién es el caller del ai-gateway aquí?**

- **Opción A**: `academic-service` agrega endpoint `POST /api/v1/tareas-practicas/generate` que internamente llama al `ai-gateway`. Pro: el dominio "TP" es de academic-service. Contra: academic-service nunca llamó al ai-gateway antes; agrega dependencia.
- **Opción B**: nuevo flujo en `governance-service` que ya gestiona prompts versionados. `POST /api/v1/governance/generate-tp` y devuelve el borrador. El frontend lo guarda llamando a academic-service.

**Recomendación**: **Opción A**. El TP es academic — academic-service es el dueño. El prompt versionado vive en `ai-native-prompts/` con `kind=tp_generator`, version semántica, hash SHA-256. El governance-service es el dueño de prompts; academic-service consulta governance para resolver el prompt activo.

### Endpoints

- `POST /api/v1/tareas-practicas/generate` (web-teacher → api-gateway → academic-service)
  - Body: `{ description: string, materia_id, periodo_id, difficulty: enum, num_exercises: int, language: 'python' }`
  - Response: `{ draft_id, enunciado_md, test_cases: [...], rubrica_jsonb, prompt_version, prompt_hash, generated_at, generated_with: { provider, model } }`
  - Internamente: academic-service → governance-service (resuelve prompt vigente) → ai-gateway (envía con `materia_id` para resolución BYOK) → guarda como TP `estado=draft` con flag `generated_by_ai=true`
- `POST /api/v1/tareas-practicas/{draft_id}/regenerate-section`
  - Body: `{ section: 'enunciado' | 'test_cases' | 'rubrica' }`
  - Para regenerar partes sin perder lo demás
- `POST /api/v1/tareas-practicas/{draft_id}/publish` (ya existe — solo agregar validación de `generated_by_ai → reviewed_by`)

### Tablas / migraciones

Modificación a `tareas_practicas`:
```sql
ALTER TABLE tareas_practicas
  ADD COLUMN generated_by_ai BOOLEAN DEFAULT FALSE,
  ADD COLUMN ai_generation_metadata JSONB,  -- prompt_version, prompt_hash, provider, model, cost_tokens
  ADD COLUMN reviewed_by UUID REFERENCES usuarios(id);  -- docente que aprobó al publicar
```

### Eventos CTR

**`tp_generado_con_ia`** (NO es N1-N4 — es evento de gobernanza académica, no cognitivo del alumno):
```json
{
  "tarea_id": "uuid",
  "docente_id": "uuid",
  "materia_id": "uuid",
  "prompt_version": "1.0.0",
  "prompt_hash": "sha256...",
  "ai_provider": "anthropic",
  "ai_model": "claude-sonnet-4-6",
  "tokens_used": 1234,
  "approved": false  // se setea true al hacer publish
}
```

Decision: ¿este evento va al CTR del estudiante (no, no hay estudiante) o a un audit log separado? El CTR está modelado para el alumno. **Recomendación**: agregar al `governance-service` un audit log de eventos académicos (separado del CTR estudiantil), append-only pero no requiere chain hash criptográfica.

### ADRs a redactar

- **ADR-036**: Generación de TPs asistida — qué servicio es dueño, formato del prompt, audit log académico separado del CTR.
- **ADR-037**: Audit log académico (`governance.academic_events` o similar) — append-only, RLS, sin chain hash. Para eventos de docentes/admins que no deben mezclarse con CTR del alumno.

### Riesgos / open questions

- ¿Cómo se versiona el prompt? Hoy `governance-service` ya tiene `PromptLoader.active_configs()` con manifiesto YAML. **Reutilizar el patrón** del prompt del tutor (`tutor/v1.0.0/system.md`) → agregar `tp_generator/v1.0.0/system.md`.
- ¿Hay risk de "homogeneización" de TPs? Si todos los docentes usan IA, los TPs se parecen. **No es un problema técnico** pero conviene declararlo en el ADR como deuda pedagógica a observar.
- Cost tracking — ¿quién paga los tokens de generación? El BYOK del sub-cambio 5 lo resuelve naturalmente (cada facultad/materia paga lo suyo).

### Esfuerzo

**M**. Depende fuertemente de #5 — si BYOK no está, el flow de "generar con qué API key" queda abierto.

---

## Sub-cambio 4 — Governance events con UI institucional

### Decisión arquitectónica clave (*)

**¿Endpoints en `governance-service` o `analytics-service`?**

- `governance-service`: dueño del dominio (define qué es "evento de gobernanza"), pero hoy NO tiene endpoints query — solo gestiona prompts.
- `analytics-service`: ya tiene `aggregate_adversarial_events()` con la proyección y filtros. Patrón ya probado.

**Recomendación**: **analytics-service**. Reúsa el patrón existente, agrega endpoints con filtros institucionales. El dominio de "qué es un evento de gobernanza" lo define el labeler/clasificador, no el servicio de query.

### Endpoints

Nuevos en `analytics-service`:
- `GET /api/v1/analytics/governance/events`
  - Query params: `facultad_id?`, `materia_id?`, `periodo_id?`, `comision_id?`, `severity_min?`, `severity_max?`, `category?`, `from?`, `to?`, `student_pseudonym?`, `cursor?`, `limit=50`
  - Response: `{ events: [...], total, cursor_next, aggregations: { by_severity, by_category, by_facultad } }`
  - Paginación cursor-based (los current endpoints no paginan — esto es nuevo)
- `GET /api/v1/analytics/governance/summary`
  - Para KPI cards del web-admin: total / 7d / by_severity / top_categorias

### Tablas / migraciones

**Ninguna** — todo se computa sobre el CTR existente (eventos `intento_adverso_detectado` ya van al CTR). Lo único que se agrega es proyección/cache en analytics-service si la performance lo requiere.

### Eventos CTR nuevos

**Ninguno**. Reusa los existentes.

### ADRs a redactar

- **ADR-038**: UI institucional de governance events — scope (solo lectura, sin "marcar como revisado") + paginación cursor-based + decisión de NO crear tabla nueva.

### Riesgos / open questions

- ¿Performance? Hoy el endpoint per-comisión no pagina; cross-comisión puede ser 10x-100x más datos. Cursor-based + índice sobre `(tenant_id, event_type, ts)` debería bastar.
- ¿"Marcar como revisado"? Si el admin necesita workflow ("vi este evento, lo escalé a docente"), ya no es solo lectura — necesita tabla nueva `governance_event_reviews`. **Recomendación**: arrancar con solo lectura, evaluar después de la defensa.

### Esfuerzo

**S-M**. Endpoints de query + página nueva en web-admin con filtros + tabla paginada. La complejidad real está en el frontend (filtros compuestos + paginación cursor).

---

## Sub-cambio 5 — BYOK multi-provider con scope facultad/materia

Este es el más complejo y bloqueante. Lo desgloso fino.

### Decisión arquitectónica clave (*) — múltiples

**1. ¿Dónde se guardan las keys?**

| Opción | Pro | Contra |
|---|---|---|
| **A.** DB encriptada (`ai_api_keys` table) | UX admin nativa (formulario web), rotación on-line, audit log automático | Requiere helper crypto + master key management (¿KMS? ¿env var?) |
| **B.** K8s SealedSecrets / mount filesystem | Reusa `tenant_secrets.py` existente, security industrial | UX horrible (admin tiene que pedirle al sysadmin que rote). En piloto UNSL no hay sysadmin dedicado |
| **C.** Híbrido: DB con referencia a secret externo | Best-of-both, pero más complejo | Requiere infra adicional |

**Recomendación**: **A**, con el master key en env var (`BYOK_MASTER_KEY` 32 bytes) en piloto, migrable a Vault/KMS post-piloto. Documentar en ADR que la rotación del master key requiere re-cifrado de todas las keys → procedimiento operacional documentado.

**2. ¿Qué providers soportar?**

- Mistral, Anthropic, Gemini (los que pediste)
- ¿OpenAI? Ya hay env var declarada, parece soportado pero no usado
- **Recomendación**: empezar con **Anthropic + Gemini + Mistral**. Dejar OpenAI como flag inactiva. Cada provider implementa la interfaz `LLMProvider` (ya existe parcial en `ai-gateway/providers/base.py`).

**3. ¿Resolución de scope?**

```
Request al ai-gateway con (tenant_id, materia_id, feature)
   │
   ▼
1. Buscar key con scope=materia, scope_id=materia_id (active, no revoked)
   ├─ HIT → usar
   └─ MISS ↓
2. Buscar key con scope=facultad, scope_id=facultad_id_de_la_materia (active)
   ├─ HIT → usar
   └─ MISS ↓
3. Buscar key con scope=tenant (=universidad), scope_id=tenant_id (fallback)
   ├─ HIT → usar
   └─ MISS ↓
4. Fallback global: env var del ai-gateway (modo legacy / dev)
   └─ MISS → 503 "no api key configured for this scope"
```

Esto requiere que el `ai-gateway` reciba `materia_id` en cada request — cambio cross-servicio (tutor-service, classifier-service, eventualmente academic-service).

**4. ¿Multi-provider activo simultáneo?**

¿Una facultad puede tener una key Anthropic Y una key Gemini activas a la vez? Si sí, ¿cómo se elige cuál usar?

**Recomendación**: **una key activa por (scope, scope_id)**. Si hay key Anthropic activa para Facultad de Ingeniería, ese es el provider de toda la facultad. Si una materia quiere Gemini, override a nivel materia. Esto simplifica mucho el modelo (no hay "elegir entre providers configurados") y es lo que la institución espera (decisión política a nivel facultad).

UNIQUE constraint: `(scope_type, scope_id, status='active')` — solo una activa por scope.

**5. ¿Budget?**

Hoy budget es por `(tenant_id, feature)` mensual en Redis. Con BYOK, cada scope paga su API key — el budget cambia de "limit del LLM compartido" a "limit informativo del consumo de cada facultad/materia".

**Recomendación**: budget se mantiene **por scope** (mismo modelo, distinto granularity): `budget_limit_usd_per_month` opcional por key. Si nulo → sin límite. Si seteado, hard-stop al alcanzarlo.

**6. ¿Validación al guardar?**

Cuando el admin agrega una key, ¿se valida con un test request al provider?

**Recomendación**: **sí**, con un request mínimo (1 token de output) al endpoint del provider. Si falla → no se guarda. Si es válido → guarda + marca `validated_at`. Re-validación periódica (cron diario) marca `validation_failed_at` si una key revocada por el provider sigue en DB.

### Endpoints

Nuevos en `ai-gateway` (o nuevo `byok-service` — *ver decisión 7 abajo*):

- `POST /api/v1/byok/keys` (admin only)
  - Body: `{ provider, scope_type: 'tenant'|'facultad'|'materia', scope_id, api_key, budget_limit_usd_per_month?, model_default? }`
  - Response: `{ key_id, validated, validated_at, fingerprint }` (NUNCA devuelve la key plaintext)
- `GET /api/v1/byok/keys?scope_type=&scope_id=` (admin only)
  - Lista keys (sin plaintext, solo metadata + fingerprint últimos 4 chars)
- `POST /api/v1/byok/keys/{id}/rotate` — sustituye plaintext, mantiene metadata
- `POST /api/v1/byok/keys/{id}/revoke` — marca `revoked_at`, no borra
- `GET /api/v1/byok/keys/{id}/usage` — consumo del mes actual
- `POST /api/v1/byok/keys/{id}/test` — re-validación manual

**7. ¿Servicio nuevo o dentro de ai-gateway?**

- Dentro de ai-gateway: simple, todo el dominio de "keys para LLMs" en un lugar
- Nuevo `byok-service` (puerto 8013): separación clara, BYOK podría escalar (ej. a otros tipos de keys: SMTP, etc.)

**Recomendación**: **dentro de ai-gateway**. El BYOK es específico de LLM keys — no es un dominio reutilizable. Separar agrega overhead de network sin beneficio claro.

### Tablas / migraciones

DB destino: **nueva `byok_db`** O dentro de `academic_main` (el ai-gateway hoy no tiene DB propia que veo).

```sql
-- Nueva DB lógica recomendada: ai_gateway_db (o pegado a academic_main si no se quiere proliferar bases)
CREATE TYPE byok_scope AS ENUM ('tenant', 'facultad', 'materia');
CREATE TYPE byok_provider AS ENUM ('anthropic', 'gemini', 'mistral', 'openai');

CREATE TABLE ai_api_keys (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  scope_type byok_scope NOT NULL,
  scope_id UUID NOT NULL,            -- tenant_id si scope=tenant; facultad_id si scope=facultad; materia_id si scope=materia
  provider byok_provider NOT NULL,
  api_key_ciphertext BYTEA NOT NULL, -- AES-GCM
  api_key_nonce BYTEA NOT NULL,
  api_key_fingerprint TEXT NOT NULL, -- últimos 4 chars en plaintext, para mostrar en UI
  model_default TEXT,                -- ej. 'claude-sonnet-4-6', 'gemini-2.0-flash'
  budget_limit_usd_per_month DECIMAL(10,2),
  validated_at TIMESTAMPTZ,
  validation_failed_at TIMESTAMPTZ,
  created_by UUID NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  revoked_by UUID
);

-- UNIQUE: solo una key activa por (scope_type, scope_id, provider)
CREATE UNIQUE INDEX uq_ai_api_keys_active
  ON ai_api_keys (scope_type, scope_id, provider)
  WHERE revoked_at IS NULL;

-- RLS: tenant_id-aware (ADR-001)
-- Index para resolver: (scope_type, scope_id, provider) WHERE revoked_at IS NULL
```

Adicional: tabla de **usage tracking**:
```sql
CREATE TABLE ai_api_keys_usage (
  key_id UUID NOT NULL,
  yyyymm INT NOT NULL,                -- 202604 para abril 2026
  tokens_input BIGINT DEFAULT 0,
  tokens_output BIGINT DEFAULT 0,
  cost_usd DECIMAL(10,4) DEFAULT 0,
  request_count INT DEFAULT 0,
  PRIMARY KEY (key_id, yyyymm)
);
```

**Cache materia → facultad**: Redis con `materia:{id}:facultad_id` TTL 1h. Invalidación al cambiar la jerarquía (raro). Alternativa: columna denormalizada `facultad_id` en `materias` — más simple, requiere mantener consistencia con triggers.

### Eventos CTR

Probablemente **ninguno** — esto es admin/gobernanza, no flujo del alumno. Audit log académico (sub-cambio #3 ADR-037) cubre esto:

**`api_key_creada`**, **`api_key_rotada`**, **`api_key_revocada`** — al audit log académico, no al CTR.

### Cambios cross-servicio

**Esto es el bloqueante de esfuerzo**. Hoy:
- `tutor-service` → `ai-gateway`: solo manda `feature`, `tenant_id` en header
- `classifier-service` → `ai-gateway`: igual

Después del cambio:
- Todo caller manda `materia_id` en el contexto del request al ai-gateway
- `tutor-service` ya tiene `materia_id` (vía episode → tarea → comision → materia)
- `classifier-service` igual
- Si el ai-gateway no recibe `materia_id` (modo dev/legacy) → fallback a scope=tenant

### ADRs a redactar

- **ADR-039**: BYOK multi-provider con scope jerárquico — almacenamiento en DB encriptada, master key management, política de fallback.
- **ADR-040**: Resolución scope materia→facultad — cache vs denormalización, política de invalidación.
- **ADR-041**: Multi-provider — política de "una key activa por scope" + interfaz `LLMProvider`.

### Riesgos / open questions

- **Master key rotation**: si `BYOK_MASTER_KEY` cambia, hay que re-cifrar todas las keys. ¿Procedimiento? ¿Downtime? ADR debe documentar.
- **Validación al guardar**: ¿qué pasa si Anthropic está caído al momento de guardar? ¿Se acepta como `validation_pending`? Recomendación: sí, con re-validación cada 5 min hasta éxito o expirar a 24h.
- **Cost tracking**: el costo real viene del provider response. Hay que parsear `usage` de cada API. Tres parsers distintos (Anthropic, Gemini, Mistral). Mantenibilidad.
- **Fallback dev**: ¿el modo `LLM_PROVIDER=mock` sigue funcionando? Sí — el resolver detecta `mock` antes del lookup de DB.
- **GDPR/LOPD**: las API keys son datos de la institución, no del usuario. Bajo riesgo legal, pero documentar en ADR.
- **Pricing por modelo**: Gemini y Mistral tienen pricing distinto a Anthropic — tabla de pricing por (provider, model) en config.

### Esfuerzo

**XL**. Justifica épica propia o sub-épica destacada dentro de la grande:
- Encriptación + helper compartido: M
- Tabla + migración + RLS: S
- Resolver con scope: M
- Propagación `materia_id` cross-servicio: M
- Adapters Gemini + Mistral: M (Anthropic ya existe)
- UI admin (CRUD + validación + usage): M
- Tests + ADRs: M

Total: ~3-4 semanas con 1 dev full-time. Con la base actual (ai-gateway ya tiene Anthropic adapter + budget tracking + tenant_secrets pattern), bajan a ~2 semanas.

---

## Cross-cutting — orden de implementación

```
                    ┌─────────────────────────┐
                    │  #5 BYOK (XL)           │  ← bloqueante para uso real de #3
                    │  - ai-gateway resolver  │
                    │  - encriptación         │
                    │  - propagación materia  │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       ┌────────────┐    ┌────────────┐     ┌────────────┐
       │ #1 Sandbox │    │ #2 Reflex  │     │ #4 Govern  │
       │ (M)        │    │ (S)        │     │ UI (S-M)   │
       │ - Pyodide  │    │ - modal    │     │ - filtros  │
       │ - JSONB    │    │ - tabla    │     │ - paginate │
       │ - eventos  │    │ - evento   │     │ - reusa    │
       └────────────┘    └────────────┘     │   CTR      │
            │                                └────────────┘
            │
            └─ paralelo a:
                                ┌────────────────────────┐
                                │ #3 Gen TPs IA (M)      │
                                │ - depende de #5 (BYOK) │
                                │ - prompt versionado    │
                                │ - audit log académico  │
                                └────────────────────────┘
```

**Orden propuesto**:

1. **Fase 1 — BYOK (#5)**: bloqueante. Sin esto, #3 no es publishable a producción institucional. Empezar acá aunque sea XL.
2. **Fase 2 — Sandbox (#1) + Reflexión (#2) + Governance UI (#4)** en paralelo. Independientes entre sí, no dependen de #5.
3. **Fase 3 — Gen TPs IA (#3)**: una vez BYOK está, esto es directo.

**Inversión vs el orden de tu mensaje original**: vos dijiste arrancar con #1. Entiendo el atractivo (es el más visible para el alumno), pero **#5 es el que destraba el resto**. Sin BYOK, #3 está cojo y la demo institucional muestra "el admin tiene que pedirle al sysadmin que rote la key" — mala UX para defensa.

Si el tiempo es ajustado y hay que cortar, la prioridad cae así:
- **Must**: #5 (BYOK), #1 (Sandbox), #2 (Reflexión)
- **Should**: #4 (Governance UI)
- **Could**: #3 (Gen TPs IA) — el docente puede armar TPs a mano hasta que se priorice

---

## Open questions consolidadas

Las marcadas con (*) son las que más impactan diseño y conviene cerrar antes del proposal:

1. **(*)** Sandbox: ¿solo Pyodide o híbrido con server-side? Afecta si nace `sandbox-service` nuevo o no.
2. **(*)** Reflexión: ¿bloqueante o no-bloqueante al cierre? Afecta UX y tasa de respuesta.
3. **(*)** TP gen IA: ¿caller es academic-service o governance-service? Afecta árbol de dependencias.
4. **(*)** Governance UI: ¿solo lectura o con workflow "marcar como revisado"? Afecta si hay tabla nueva.
5. **(*)** BYOK storage: DB encriptada vs K8s SealedSecrets. Afecta UX admin y master key management.
6. **(*)** BYOK scope: una key activa por scope, o multi-provider simultáneo. Afecta modelo de datos.
7. **(*)** BYOK: budget per-key o sigue per-(tenant, feature)? Afecta granularidad de tracking.
8. Test cases hidden: ¿el docente puede marcar un test como hidden? ¿qué hace el classifier con el resultado de un test hidden?
9. Reflexión como input al classifier: NO recomiendo (rompe reproducibilidad). Confirmar.
10. Master key rotation: procedimiento operacional. ¿En el ADR o en runbook?
11. ¿`materia_id` se propaga a TODOS los callers del ai-gateway o solo los nuevos? Migración cross-servicio.
12. Pricing per-model: tabla en config del ai-gateway o en governance-service?

---

## Próximos pasos sugeridos

1. **Vos decidís** las 7 (*) — son decisiones de producto/arquitectura que requieren tu input antes de seguir.
2. Una vez cerradas → `opsx:propose` con scope acotado a la fase 1 (BYOK) primero, las otras 4 fases en proposals separados o sub-proposals dentro de un epic mayor.
3. ADRs a redactar primero (antes del proposal final): **ADR-039 (BYOK)**, **ADR-033 (sandbox híbrido)**, **ADR-035 (reflexión privacy)**. Los otros ADRs pueden ir después con el design.
4. Si querés un solo epic gigante: este `ai-native-completion-and-byok` con 5 sub-cambios. Si preferís cinco epics chicas: `byok-multiprovider`, `sandbox-test-cases`, `reflection-postclose`, `governance-ui-admin`, `tp-generator-ai`.

Mi recomendación: **5 epics chicas**. Más fáciles de revisar, mergear, y presentar al comité. Esta exploración queda como "north star" que las une.
