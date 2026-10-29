## Why

Hoy "Devolver al estudiante" (`POST /entregas/{id}/return`, `apps/evaluation-service/src/evaluation_service/routes/entregas.py:751-815`) hace **dos cosas pegadas**: deja la entrega en `returned` **y reabre TODOS los ejercicios** (`_reabrir_ejercicios`, `entregas.py:821`). Combinado con el lock secuencial del alumno (`apps/web-student/src/components/ExerciseListView.tsx:349-353`, `isLocked`: el N se habilita sólo si el N-1 está completado), una TP de 5 ejercicios donde el docente objetó **uno** obliga al alumno a rehacer los cinco, en orden.

Hay un segundo problema que apareció al investigar, y es de honestidad del producto: **los textos de ayuda del docente prometen algo que el sistema no hace.** Dicen que "Calificar y devolver son dos pasos separados a propósito: podés cerrar las notas de toda la comisión y recién después liberarlas" (`apps/web-teacher/src/tour/vistas.tsx:329-335`, `onboarding/docenteOnboarding.tsx:131-133`) y que "Devuelta es la que el alumno ya puede leer" (`utils/helpContent.tsx:654-662`). **Falso**: el alumno ve la nota y el feedback apenas el docente califica, en `graded`, sin devolución:

- backend: `GET /entregas/{id}/calificacion` sólo exige ser el dueño (`entregas.py:725-748`, `_assert_can_read` en `:1270`), no mira el estado;
- web-student: `GradeDetailView.tsx:34` carga la nota con `graded` **o** `returned`; `ExerciseListView.tsx:445-452` muestra "Calificada… Ver calificación →" en `graded`; `TareaSelector.tsx:124` y `:637` la ponen en "listo" con botón de ver nota; `MisNotasPage.tsx` la agrupa en `conNota`.

Decisión del dueño (Neyén, 2026-10-27): separar en **dos acciones del docente**: **Publicar nota** (el alumno ve nota y feedback; la TP queda cerrada, no se reabre nada) y **Pedir corrección** (opcional: el docente tilda qué ejercicios reabrir y sólo esos se reabren).

## What Changes

- **"Publicar nota" es la calificación que ya existe.** No hay estado nuevo: `graded` ya significa "nota visible para el alumno" (ver arriba). El botón "Calificar" pasa a llamarse **"Publicar nota"** ("Publicar y siguiente" en la cola) y los tres textos de ayuda dejan de prometer la liberación diferida. Ver design D1 (y la alternativa de ocultar la nota hasta publicar, que queda como pregunta abierta).
- **"Pedir corrección" reemplaza a "Devolver al estudiante".** Abre una lista de los ejercicios de la TP con checkbox; el docente tilda al menos uno y confirma. `POST /entregas/{id}/return` acepta un body **opcional** `{"ordenes": [2, 4]}`:
  - con `ordenes`: sólo esos ejercicios pasan a `completado=false` y quedan marcados `reabierto_por_docente=true` en `ejercicio_estados`; los demás quedan **intactos** (`completado=true`, mismo `episode_id`, mismo código sellado);
  - sin body (clientes viejos, o la TP monolítica): comportamiento de hoy, se reabren todos. **Backward compatible.**
- **Re-entrega parcial**: al re-entregar una devolución parcial, el backend **conserva por sí mismo** el artefacto sellado de cada ejercicio no reabierto (mismo código, mismo `sha256`, mismo `episode_id`) y sólo exige del cliente el código de los reabiertos. El cliente no puede pisar el código de un ejercicio que el docente no reabrió. Las marcas `reabierto_por_docente` se limpian en el submit.
- **El alumno no puede tocar lo que el docente no reabrió**: en una devolución parcial, el `PATCH /entregas/{id}/ejercicio/{orden}` sobre un ejercicio no reabierto responde 409, y el botón "Volver a abrir" no aparece en esos ejercicios.
- **Lock secuencial sólo entre pendientes**: un ejercicio no completado se habilita si **todos** los anteriores están completados. Los no reabiertos cuentan como hechos, así que con "corregí el 2 y el 4" el alumno entra directo al 2, y el 4 se habilita cuando cierra el 2.
- **El alumno ve qué le pidieron corregir**: badge "A corregir" en los ejercicios reabiertos por el docente.
- **Sin migración**: la marca vive en el JSONB `ejercicio_estados`. Las entregas `returned` que ya existen en producción (todas con TODOS los ejercicios reabiertos y sin la marca) **se dejan como están** y se siguen comportando exactamente como hoy.

## Dependencia con `editor-muestra-codigo-entregado-al-reabrir`

Este change **no depende** del otro. Se complementan: éste reduce cuántos ejercicios se reabren; el otro hace que, al abrir uno reabierto, el editor muestre lo entregado y que cerrarlo sin cambios lo complete. Con éste aplicado y el otro no, los ejercicios no reabiertos ya no sufren el bug de "cerrar sin escribir no completa" (no hay que abrirlos), pero los reabiertos sí. Orden recomendado de apply: este primero (ver design, "Orden de apply").

## Capabilities

### New Capabilities
- (ninguna)

### Modified Capabilities
- `correccion-grading`: la devolución pasa a ser "pedir corrección" con lista opcional de ejercicios; la re-entrega parcial conserva los artefactos no reabiertos; la vista docente cambia el rótulo de calificar a "Publicar nota".
- `student-exercise-flow`: el lock secuencial pasa a regir sólo entre ejercicios pendientes; en una devolución parcial el alumno no puede reabrir ni marcar ejercicios no reabiertos y ve cuáles le pidieron corregir.

## Impact

- **Backend** (`apps/evaluation-service`): `routes/entregas.py` (`return_entrega`, `_reabrir_ejercicios`, `submit_entrega`, `_persistir_artefactos`, `mark_ejercicio_completado`), `schemas/entrega.py` (`EjercicioEstadoSchema.reabierto_por_docente`, body nuevo `ReturnEntregaBody`). Sin migración Alembic.
- **web-teacher**: `views/CorreccionesView.tsx` (rótulo "Publicar nota", modal "Pedir corrección"), `lib/api.ts` (`devolverEntrega` con `ordenes`), `tour/vistas.tsx:329`, `utils/helpContent.tsx:654`, `onboarding/docenteOnboarding.tsx:131`.
- **web-student**: `components/ExerciseListView.tsx` (lock, "Volver a abrir", badge), `lib/api.ts` (`EjercicioEstado.reabierto_por_docente`), función pura nueva para el lock.
- **Tesis**: nada del instrumento cambia (CTR, classifier, prompts, contratos: ver design "Tesis: qué NO se toca"). **Matiz de comportamiento**: con devoluciones parciales hay menos re-entregas de ejercicios que estaban bien → menos segundos intentos en los datos (menos episodios nuevos por ejercicio no objetado). El instrumento mide igual; cambia la población de intentos. **Hay que avisarle a Cortez.**
- **Gobernanza**: MEDIO (lógica de negocio de entregas). TDD estricto.
