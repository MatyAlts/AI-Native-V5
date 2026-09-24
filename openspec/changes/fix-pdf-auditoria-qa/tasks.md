# Tasks — fix-pdf-auditoria-qa

Cada tarea se cierra con: test que falla sin el cambio y pasa con él (o, para UI
pura, verificación manual descrita). Marcar [x] al completar.

## Lote 0 — ya hecho (commit d4ce2a1)
- [x] BUG-11 · etiqueta del motor real en la sugerencia de corrección
- [x] BUG-16 · texto honesto al pasar sólo los tests públicos
- [x] BUG-05 · versión del prompt en el pie de auditoría (bump v1.5.0)

## Lote 1 — UX del formulario de TP (docente)
- [x] BUG-18 · `formatApiError` puro que traduce el 422 de FastAPI a mensaje por
      campo; usarlo en el submit del form de TP. Nunca mostrar "[object Object]".
      Test: unit de `formatApiError` (422 array, detail string, error genérico).
- [x] BUG-03 · auto-scroll al mensaje de error del modal de TP cuando se setea
      `formError` (respetar prefers-reduced-motion). Verificación manual.

## Lote 2 — analítica y correcciones (docente)
- [x] BUG-14 · "Balance general" no debe afirmar una mayoría desde un ratio neto;
      texto que diga lo que mide + piso de N como en Cuartiles. Test del texto por rama.
- [x] BUG-12 · "Devolver al estudiante" visible sin tener que apretar "Cancelar"
      tras calificar (salir de reediting al calificar OK, o renombrar el botón).

## Lote 3 — formulario y estado (docente)
- [x] BUG-01 · "Nuevo TP" no debe arrastrar datos del TP anterior (key/remount o
      reset al abrir). Test: abrir crear dos veces → segundo form vacío.
- [x] BUG-02 · el Código de un TP: o inmutable (input disabled en edición) o
      editable de verdad (agregarlo al schema del academic-service). Decidir y cerrar.

## Lote 4 — Mejora 2 · reapertura con código previo
- [x] REAPERTURA · al reabrir un ejercicio cerrado, el episodio nuevo abre con el
      código del último episodio cerrado del mismo (alumno, tarea, ejercicio_orden),
      igual que la pausa. Fix en el read path del CTR (get_episode_state).
      Test: reabrir con código X → el episodio nuevo trae X, no el scaffold.

## Lote 5 — Mejora 3 · retroalimentación completa
- [x] RUBRICA-AUTOCOMPLETE · al aplicar la corrección con IA, autocompletar los
      puntajes por criterio (no sólo la nota final).
- [x] BUG-19 · el desglose por criterio se persiste en la devolución y el alumno
      no ve "0 / NaN" (leer puntaje_max con fallback). Test del render de criterios.

## Lote 6 — pie de auditoría vivo
- [x] BUG-08 · pasar el episodeId real (y classifierHash) al AuditFooter para que
      el poll a /audit/.../verify corra y el pie deje de estar muerto.

## Cosméticos (si sobra)
- [x] BUG-04 · "Tu episodio:" sin valor colgando en Vencidas del alumno.
- [x] BUG-20 · contador de cabecera de Evolución por estudiante vs el detalle.
