## ADDED Requirements

### Requirement: Endpoint `POST /api/v1/tareas-practicas/generate` en academic-service

El academic-service SHALL exponer `POST /api/v1/tareas-practicas/generate` que recibe `{ materia_id, descripcion_nl, dificultad?, contexto? }` y retorna `{ enunciado, inicial_codigo, rubrica, test_cases }` como borrador editable. El endpoint SHALL requerir rol `docente`, `docente_admin` o `superadmin`. El borrador SHALL NO persistirse — el docente edita en frontend y dispara el `POST /api/v1/tareas-practicas` (creación) o `PATCH` (edición) tradicional.

#### Scenario: Docente genera borrador

- **WHEN** un docente autenticado pega `POST /api/v1/tareas-practicas/generate` con `materia_id` válido y descripción NL
- **THEN** academic-service SHALL llamar al `ai-gateway` con `feature="tp_generator"`, `tenant_id`, `materia_id`, `prompt_version="tp_generator/v1.0.0"`
- **AND** el response SHALL incluir borrador con los 4 campos esperados, validados por schema

#### Scenario: Estudiante intenta generar TP

- **WHEN** un estudiante pega el endpoint
- **THEN** Casbin SHALL rechazar con `403 Forbidden`

### Requirement: Audit log structlog `tp_generated_by_ai`

El academic-service SHALL emitir audit log structlog `tp_generated_by_ai` por cada invocación exitosa, con campos: `tenant_id`, `user_id`, `materia_id`, `prompt_version`, `tokens_input`, `tokens_output`, `latency_ms`, `provider_used` (resuelto por BYOK). Este log SHALL ser queryable via Loki para auditoría doctoral.

#### Scenario: Audit log emitido en generación exitosa

- **WHEN** la generación retorna 200
- **THEN** el log structlog SHALL emitirse antes del response con todos los campos completos

#### Scenario: No audit log en errores antes del LLM

- **WHEN** la generación falla en validación de input (ej. `materia_id` inexistente)
- **THEN** el log `tp_generated_by_ai` SHALL NO emitirse (no se llamó al LLM)
- **AND** un log de error standard SHALL emitirse con la causa

### Requirement: TP generada por IA marcable explícitamente

La TP creada a partir de un borrador IA SHALL almacenarse con flag `created_via_ai=true` (columna nueva en `tareas_practicas`). Esto permite análisis cuantitativo del impacto de la asistencia IA en la tesis (qué porcentaje de TPs del piloto fueron asistidas).

#### Scenario: TP creada desde borrador asistido

- **WHEN** el docente publica una TP cuyo enunciado/test_cases vienen del endpoint `generate`
- **THEN** el frontend SHALL incluir `created_via_ai=true` en el `POST /api/v1/tareas-practicas`
- **AND** la TP persistida SHALL tener el flag

### Requirement: Prompt versionado para TP-gen vive en `ai-native-prompts/`

El prompt del generador SHALL persistirse en `ai-native-prompts/prompts/tp_generator/v1.0.0/system.md` con metadata en `ai-native-prompts/manifest.yaml`. El academic-service SHALL leer el prompt vía `governance-service` (mismo patrón que tutor-service) — NO hardcoded en código.

#### Scenario: Bumping prompt no requiere redeploy

- **WHEN** se agrega `ai-native-prompts/prompts/tp_generator/v1.1.0/system.md` y se actualiza el manifest
- **THEN** academic-service SHALL leer la nueva versión sin restart si el cache TTL expira (default 5 min)
