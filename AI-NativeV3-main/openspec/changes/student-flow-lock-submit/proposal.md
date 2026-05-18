## Why

El web-student hoy trata cada TP como un bloque monolítico: el alumno abre un episodio, interactúa con el tutor, y cierra. No hay flujo de ejercicios individuales, no hay concepto de "entregar" la TP, no hay bloqueo de sesión (el alumno puede navegar libremente sin consecuencia), y no hay vista de notas. Esto hace que la experiencia del alumno sea una demo de chat, no un flujo académico real de trabajo práctico → entrega → corrección → nota.

Con los backends de ejercicios (`tp-entregas-correccion`) y el tutor enriquecido (`tutor-context-rag-rubrica`) resueltos, este epic cierra el loop del alumno de punta a punta.

## What Changes

- **Flujo ejercicio por ejercicio**: dentro de una TP, el alumno ve la lista de ejercicios y trabaja uno por uno. Cada ejercicio abre su propio episodio con el tutor. El progreso se muestra visualmente (completado / en progreso / pendiente).
- **Consigna + criterios visibles por ejercicio**: cada ejercicio muestra su enunciado propio y los criterios de evaluación públicos de la rúbrica (los `is_public=true` del test_cases y los criterios de la rúbrica marcados como visibles).
- **Session lock**: al iniciar un ejercicio, el sistema emite warning si el alumno intenta navegar fuera (similar al `beforeunload` existente pero extendido). Eventos `focus`/`blur` del tab se registran como telemetría en el CTR para trazabilidad de atención.
- **Botón de entrega**: cuando todos los ejercicios están completados (o el alumno decide entregar lo que tiene), un botón "Entregar TP" crea la entrega en evaluation-service (`POST /api/v1/entregas`). Confirmación explícita antes de submit (acción irreversible).
- **Vista post-entrega**: después de entregar, el alumno ve el estado de su entrega (submitted → graded → returned). Cuando está corregida, ve nota por criterio, nota final, y feedback del docente.
- **Integración con tutor enriquecido**: cada ejercicio pasa su contexto específico (enunciado + rúbrica + material RAG de la materia) al tutor vía el flujo de `tutor-context-rag-rubrica`.

## Capabilities

### New Capabilities
- `student-exercise-navigation`: Navegación ejercicio por ejercicio dentro de una TP. Lista visual de ejercicios con estado, transición entre ejercicios, apertura de episodio por ejercicio. Incluye barra de progreso y marcado de ejercicio completado.
- `session-lock`: Detección de navegación fuera del ejercicio activo con warning modal. Registro de eventos `focus`/`blur` del tab como telemetría CTR. Extiende el patrón `beforeunload` existente.
- `tp-submission-flow`: Flujo de entrega de TP desde web-student. Validación de ejercicios completados, confirmación pre-submit, creación de entrega en evaluation-service, vista de estado post-entrega.
- `student-grades-view`: Vista de notas del alumno. Estado de entrega, nota por criterio de rúbrica, nota final ponderada, feedback del docente. Accesible desde la lista de TPs de la materia.

### Modified Capabilities
(ninguna — las capabilities del student flow son todas nuevas; los backends de entregas y corrección vienen del epic `tp-entregas-correccion`)

## Impact

- **web-student**: Rediseño mayor del flujo post-selección de TP. Nueva navegación de ejercicios, extensión de EpisodePage para contexto de ejercicio, nueva página de entrega, nueva vista de notas. Estimación: 5-8 componentes nuevos.
- **tutor-service**: Cambio menor — el `open_episode` recibe opcionalmente `ejercicio_orden` para vincular el episodio al ejercicio dentro de la TP. El contexto de rúbrica se filtra al ejercicio específico.
- **evaluation-service**: Consumido via API — los endpoints de entregas y calificaciones vienen del epic `tp-entregas-correccion`. Sin cambios adicionales.
- **packages/contracts**: Posible nuevo evento CTR `focus_blur_detected` para telemetría de session lock (o extensión de payload existente).
- **api-gateway**: ROUTE_MAP para evaluation-service (si no fue agregado por el epic de entregas).
