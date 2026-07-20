## Why

El panel del alumno hoy trata cada TP como un bloque monolítico que abre un episodio (sesión con el tutor). No hay concepto de ejercicios individuales, entregas, corrección docente ni calificación. El docente ve la traza CTR pero no puede corregir ni devolver notas. Esto rompe el flujo pedagógico real de una cátedra universitaria donde las TPs tienen múltiples ejercicios, se entregan, se corrigen con rúbrica y el alumno ve su nota.

La traza de analytics del docente (progresión, evolución longitudinal, niveles N1-N4) debe alimentarse de esta actividad real del alumno haciendo ejercicios — no de episodios sueltos sin contexto de entrega.

## What Changes

- **Ejercicios como entidades dentro de una TP**: `TareaPractica.ejercicios` como JSONB array ordenado, cada uno con título, enunciado, código inicial y test cases propios.
- **Modelo de Entrega (Submission)**: nueva entidad que agrupa el trabajo del alumno sobre una TP completa, con estado `draft → submitted → graded → returned`.
- **Flujo secuencial del alumno**: el alumno completa ejercicios uno por uno (cada uno abre un episodio), y cuando todos están completos puede entregar la TP.
- **Modelo de Calificación (Grading)**: el docente corrige entregas usando la rúbrica de la TP, asigna puntaje por criterio y feedback.
- **Vista de corrección en web-teacher**: nueva página donde el docente ve entregas pendientes, el código de cada ejercicio, la traza CTR asociada, y corrige con rúbrica.
- **Vista de nota en web-student**: el alumno ve el estado de su entrega y, cuando está corregida, la nota y el feedback del docente.
- **Eventos CTR nuevos**: `tp_entregada` y `tp_calificada` para trazabilidad completa de la cadena entrega→corrección.
- **Analytics basados en entregas**: la progresión del docente refleja el trabajo real del alumno (ejercicios completados, entregas calificadas, notas).

## Capabilities

### New Capabilities
- `tp-ejercicios`: Ejercicios como sub-entidades dentro de TareaPractica. Estructura JSONB con orden, título, enunciado, código inicial, test cases y peso por ejercicio. CRUD desde web-teacher y web-admin.
- `entregas-submission`: Modelo de entrega del alumno. Agrupa episodios por ejercicio bajo una TP. Estados draft/submitted/graded/returned. Endpoints REST para crear, listar, submit. Evento CTR `tp_entregada`.
- `correccion-grading`: Corrección docente con rúbrica estructurada. Puntaje por criterio, feedback general, nota final calculada. Endpoint REST para calificar. Evento CTR `tp_calificada`. Vista de corrección en web-teacher.
- `student-grades-view`: Vista de notas del alumno en web-student. Estado de entregas, nota cuando está corregida, feedback del docente por criterio.
- `student-exercise-flow`: Flujo secuencial del alumno: ve ejercicios de la TP, hace uno por uno (cada uno = un episodio), marca como completado, entrega cuando todos están listos.

### Modified Capabilities
- `academic-comisiones`: Las TPs dentro de una comisión ahora tienen ejercicios internos y entregas asociadas. El modelo TareaPractica se extiende.

## Impact

- **academic-service**: Extensión del modelo `TareaPractica` con campo `ejercicios` JSONB. Nuevos endpoints para entregas (`/api/v1/entregas`).
- **evaluation-service**: Activación del servicio esqueleto. Nuevos modelos `Entrega`, `Calificacion`. Nueva DB o extensión de `academic_main`. Endpoints de corrección.
- **tutor-service**: Los episodios ahora se vinculan opcionalmente a un ejercicio dentro de una TP (campo `ejercicio_orden` en el evento `episodio_abierto`).
- **web-student**: Rediseño del flujo de TP — vista de ejercicios secuenciales, estado por ejercicio, botón de entrega, vista de nota.
- **web-teacher**: Nueva sección "Entregas" en sidebar. Vista de corrección con rúbrica interactiva. Analytics de progresión basados en entregas y notas.
- **api-gateway**: Nuevas entradas en ROUTE_MAP para evaluation-service.
- **CTR**: 2 nuevos event types (`tp_entregada`, `tp_calificada`). El classifier y labeler deben ignorarlos o tratarlos como meta-eventos.
- **packages/contracts**: Nuevos schemas Pydantic para los eventos CTR de entrega y calificación.
