# ADR-036 — TP-gen IA: caller es `academic-service` + audit log structlog

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: ia, generacion, audit, prompts
- **Epic**: ai-native-completion-and-byok / Sec 11

## Contexto y problema

El docente quiere generar borradores de TPs en lenguaje natural. Quien
debe ser el **caller** del `ai-gateway`?

Opciones:
- A. `academic-service` — dueno del dominio TP.
- B. `governance-service` — dueno de los prompts.
- C. Frontend pega directo al `ai-gateway` con su propio token.

## Drivers de la decisión

- **Single source of identity**: el `ai-gateway` autentica callers via
  `X-Caller` header. Cada servicio es un caller distinto con su propio
  budget y audit. Frontend NO es caller del ai-gateway (defense in depth —
  frontends NO deben llamar LLMs directamente, ya cubierto por
  invariante "ai-gateway unico proxy" del CLAUDE.md).
- **Domain-driven boundaries**: la TP es entidad de academic-service. El
  endpoint `/generate` devuelve un dato del dominio TP — debe vivir donde
  vive el resto del CRUD.
- **Auditabilidad doctoral**: el comite necesita ver que TPs del piloto
  involucraron IA en su autoria. Audit log queryable via Loki es lo
  esperable.

## Decisión

**A — caller es `academic-service`**.

Flujo:
1. Frontend pega `POST /api/v1/tareas-practicas/generate` (academic-service).
2. academic-service consulta `governance-service` para resolver el prompt
   activo (`tp_generator/v1.0.0`).
3. academic-service pega al `ai-gateway` con `X-Caller="academic-service"`,
   `feature="tp_generator"`, `materia_id` (ADR-040) en el payload.
4. Parse del JSON estructurado del LLM → response al frontend como borrador.
5. **Audit log structlog** `tp_generated_by_ai` con `tenant_id`, `user_id`,
   `materia_id`, `prompt_version`, `tokens_input`, `tokens_output`,
   `latency_ms`, `provider_used`, `model_used`. Queryable via Loki.

El borrador **NO se persiste** en este endpoint — el docente edita en
frontend y dispara `POST /api/v1/tareas-practicas` tradicional con
`created_via_ai=true` (columna nueva, ADR-034).

## Consecuencias

### Positivas

- Domain boundaries limpios. governance-service solo resuelve prompts;
  academic-service decide cuando llamarlos.
- Audit log unificado en Loki bajo el caller `academic-service` —
  trazabilidad doctoral de TPs IA.
- Bumpear el prompt (`v1.0.0` → `v1.1.0`) NO requiere redeploy del
  academic-service: governance-service expone la version activa via
  manifest + cache TTL.

### Negativas / trade-offs

- Si el `governance-service` cae, el endpoint `/generate` falla con 502.
  Aceptable — es feature opt-in.
- El parser del JSON estructurado del LLM puede fallar (LLM devuelve
  malformed). Manejado con HTTP 502 + structlog del content preview.

## `created_via_ai` en `tareas_practicas`

Columna BOOLEAN agregada por la misma migracion que `test_cases`
(`20260504_0001_add_test_cases_and_created_via_ai.py`). El frontend la
pasa a `true` al hacer `POST /tareas-practicas` despues de editar el
borrador del wizard. Permite analisis cuantitativo: "que % de TPs del
piloto tuvieron asistencia IA".

## Referencias

- Endpoint: `apps/academic-service/.../routes/tareas_practicas.py::generate_tarea_practica`
- Prompt: `ai-native-prompts/prompts/tp_generator/v1.0.0/system.md`
- Cliente AI: `apps/academic-service/.../services/ai_clients.py`
- ADR-040 — `materia_id` propagation cross-service.
