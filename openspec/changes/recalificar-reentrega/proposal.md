## Why

Los tutores reciben `409 "Esta entrega ya tiene una calificacion"` al calificar en web-teacher en "bastantes" entregas. Causa: al devolver un TP (`graded -> returned`) la `Calificacion` queda; cuando el alumno re-entrega (`returned -> submitted`) la entrega queda `submitted` CON la calificación vieja (caso NB-4). El panel sólo trata como "ya calificada" a `graded`/`returned`, así que muestra el form normal y hace `POST /calificar`, que responde 409. El backend ya tiene el camino correcto (`PATCH /{id}/calificacion`); el hueco es del front.

## What Changes

- web-teacher detecta la re-entrega (`submitted` + calificación existente) y al guardar usa `PATCH /calificacion` en vez de `POST /calificar`; la entrega termina `graded`.
- El panel muestra un aviso "Re-entrega — nota anterior: X" (con el feedback anterior como referencia). El form arranca vacío.
- Si el `POST /calificar` igual responde 409 (datos viejos, carrera), el front reintenta con `PATCH` en vez de mostrar el error crudo.
- Primera calificación (`submitted` sin calificación), `graded` y `returned`: sin cambios.
- Sin cambios de backend, esquema de DB, contratos CTR ni app del estudiante.

## Capabilities

### New Capabilities
(ninguna)

### Modified Capabilities
- `correccion-grading`: se agrega el requisito de calificar una re-entrega desde el panel del docente sin 409.

## Impact

- `apps/web-teacher/src/views/CorreccionesView.tsx` (GradingFormView).
- `apps/web-teacher/tests/CorreccionesView.test.tsx`.
