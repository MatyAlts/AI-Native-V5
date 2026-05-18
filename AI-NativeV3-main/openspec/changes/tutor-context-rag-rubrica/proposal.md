## Why

El tutor socrático ya hace retrieval al content-service y formatea los chunks como contexto RAG en el prompt, pero hoy el content-service tiene la DB vacía (nunca se subió material real) y el tutor NO inyecta la rúbrica del ejercicio en el contexto. Resultado: el tutor guía al alumno basándose solo en el enunciado, sin saber qué criterios de evaluación aplican ni qué material de referencia es relevante.

Con el epic `rag-scoped-materias` resuelto (materiales reales subidos por materia) y `tp-entregas-correccion` (rúbricas por ejercicio), este epic conecta las piezas: el tutor recibe contexto RAG real + rúbrica del ejercicio actual para guiar pedagógicamente hacia los criterios de evaluación sin revelarlos explícitamente.

## What Changes

- **Inyección de rúbrica en el contexto del tutor**: `tutor_core.py` lee la rúbrica de la TP (o del ejercicio específico si aplica el flujo de ejercicios) y la incluye en el prompt como sección separada. La rúbrica le permite al tutor orientar las preguntas socráticas hacia los criterios que el alumno necesita cubrir.
- **Prompt template actualizado**: `ai-native-prompts/prompts/tutor/v1.0.0/system.md` (o nueva versión `v1.1.0`) incluye secciones explícitas para `{{rag_context}}` y `{{rubrica_context}}` con instrucciones de cómo usarlos pedagógicamente (guiar sin revelar criterios).
- **`chunks_used_hash` poblado con datos reales**: el campo ya se propaga correctamente en eventos CTR `prompt_enviado` y `tutor_respondio`. Con material real en el content-service, el hash pasa de ser vacío a tener valor auditado.
- **Governance-service resuelve el prompt con placeholders**: el template devuelto por governance incluye los placeholders que el tutor-service rellena con el contexto concreto del turno.

## Capabilities

### New Capabilities
- `tutor-rubric-context`: Inyección de la rúbrica de la TP/ejercicio actual en el contexto del tutor. El tutor-service resuelve la rúbrica via academic-service y la formatea como sección del prompt. Incluye instrucciones pedagógicas para guiar sin revelar.
- `tutor-prompt-template-v1.1`: Nueva versión del prompt del tutor con secciones explícitas para contexto RAG y rúbrica. Versionado en `ai-native-prompts/prompts/tutor/`. El manifest.yaml se actualiza para apuntar a la versión activa.

### Modified Capabilities
(ninguna — el RAG retrieval ya existe en tutor-service, solo se enriquece el contexto)

## Impact

- **tutor-service**: `tutor_core.py` agrega llamada a academic-service para obtener rúbrica de la TP, formatea y concatena al contexto. El `_format_rag_context()` existente no cambia — se agrega `_format_rubric_context()`.
- **governance-service**: Template del prompt actualizado con placeholders de rúbrica. Sin cambios de lógica — solo contenido del prompt versionado.
- **ai-native-prompts/**: Nueva versión del prompt (`v1.1.0` o bump de `v1.0.0`). Actualizar `manifest.yaml` y `tutor-service/config.py:default_prompt_version` en sync.
- **academic-service**: Sin cambios de endpoints — el tutor ya llama `GET /api/v1/tareas-practicas/{id}` que devuelve `rubrica`. Si el flujo de ejercicios está activo (epic `tp-entregas-correccion`), se necesita un campo `rubrica` por ejercicio accesible por el mismo endpoint.
- **content-service**: Sin cambios — el retrieve ya funciona. Este epic depende de que haya material real subido (epic `rag-scoped-materias`).
- **CTR**: Sin nuevos event types. `chunks_used_hash` ya se propaga — pasa de valor vacío a hash real.
