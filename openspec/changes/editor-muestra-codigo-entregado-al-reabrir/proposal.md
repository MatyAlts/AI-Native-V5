## Why

Un alumno reportó en producción (2026-10-23): *"TP devuelto con feedback: cuando pongo siguiente episodio no se desbloquea, queda en el mismo ejercicio que puse finalizar episodio."* Con una TP devuelta, cerrar un ejercicio reabierto **sin escribir nada** no lo marca como completado, el siguiente queda bloqueado y la pantalla no dice por qué.

Este change hereda el diagnóstico del change descartado `tp-devuelta-ejercicio-no-se-completa` (2026-10-24, nunca implementado), **con una corrección importante** que apareció al releer el código:

1. **Confirmado — el guard.** Al cerrar, `markEjercicioCompletedOnce` (`apps/web-student/src/pages/EpisodePage.tsx:826-875`) sale sin marcar si no hay borrador local para `(entregaId, orden)` (guard `hayCodigo`, `:860-863`, el de BUG-1). El borrador sólo lo escribe `onEditDebounced` cuando el alumno tipea (`:1091-1113`) y `clearArtefactoDrafts` lo borra al entregar (`apps/web-student/src/components/ExerciseListView.tsx:320`). Los tres caminos de cierre (`handleClose` `:764`, "Siguiente ejercicio" `:915`, cierre del `ReflectionModal` `:1608`) pasan por el mismo guard.
2. **Corregido — el editor NO siempre abre vacío.** El change viejo afirmaba que al reabrir el editor mostraba el scaffold. Pero desde el PR #95 (2026-09-24) existe **REAPERTURA** (`apps/tutor-service/src/tutor_service/routes/episodes.py:498-526`): si el episodio nuevo no tiene código, `GET /episodes/{id}` siembra `last_code_snapshot` con el último código del episodio **cerrado** más reciente del mismo alumno + TP + ejercicio (`ctr-service` `GET /episodes/closed-match`, `routes/events.py:159-205`). Sólo lectura, no emite eventos. O sea: **el alumno ve su código, no toca nada porque estaba bien, cierra… y el guard no lo marca.** El bug es el guard, no la siembra.
3. **Huecos reales de la siembra actual:**
   - **Cadena cortada**: si el alumno reabre, cierra sin editar, y vuelve a reabrir, `closed-match` devuelve el episodio más reciente (el vacío) y `_last_code_from_events` da `None` → el editor cae al scaffold/placeholder.
   - **Evidencia más débil**: REAPERTURA usa el último snapshot que llegó al CTR (fire-and-forget); lo sellado al entregar viene del borrador local. Pueden diferir si un POST de `edicion_codigo` falló.
4. **Confirmado — "marcar igual" no alcanza.** Sin un borrador, el PATCH pisa `episode_id` con el del episodio nuevo y en la re-entrega `recuperarArtefactos` (`ExerciseListView.tsx:102-145`) no encuentra snapshot → 422 *"Falta el código de los ejercicios: [N]"* (BUG-1 corrido al submit).

## What Changes

- **El editor del ejercicio reabierto muestra el código entregado** cuando no hay nada mejor: nuevo candidato `codigoEntregado` en la cascada pura (`apps/web-student/src/lib/cascadaCodigo.ts`), **después** del borrador local y del snapshot (que incluye REAPERTURA) y **antes** de los scaffolds del docente. Sale de `GET /entregas/{id}/artefacto` (endpoint que **ya existe** en `main`, `entregas.py:420`), fila del mismo `orden`/`ejercicio_id`. Se pide sólo si los dos primeros candidatos están vacíos. Cierra la cadena cortada.
- **Cerrar sin editar completa el ejercicio** cuando el editor muestra código propio del alumno (origen `snapshot` o `codigo-entregado`) y no hubo edición en este episodio: ese código se guarda como borrador local y se marca el ejercicio, como si lo hubiera tipeado. La re-entrega manda ese mismo código.
- **BUG-1 intacto**: si el editor muestra scaffold o placeholder, o el alumno editó y dejó vacío, el ejercicio **no** se marca (como hoy).
- **Sólo `apps/web-student`.** Sin backend, sin migraciones, **sin eventos CTR nuevos ni cambios de emisión**. No se reabre ningún episodio cerrado. No se toca REAPERTURA ni `closed-match`.

## Dependencias

- **Con `publicar-nota-y-pedir-correccion`**: este change **sirve solo**. Sin aquél, arregla el caso de hoy (devolución total: el alumno puede cerrar sin cambios los ejercicios que estaban bien). Con aquél, el caso queda acotado a los ejercicios que el docente sí reabrió y el alumno cierra sin cambiar, y a "Volver a abrir" en `draft`. Orden recomendado: aquél primero, éste después; pero no hay dependencia técnica.
- **Con el PR #122** (`feat/alumno-mis-trabajos-corregidos`, **abierto** al 2026-10-27): agrega `getEntregaArtefacto` a `apps/web-student/src/lib/api.ts`. Si #122 se mergea antes del apply, se reusa. Si no, se copia **idéntica** (mismo texto: el conflicto al mergear el segundo es trivial y queda una sola copia). Ver design D4.

## Capabilities

### New Capabilities
- (ninguna)

### Modified Capabilities
- `student-exercise-flow`: el ejercicio reabierto abre con el código ya entregado cuando no hay código propio más fresco; cerrarlo sin cambios lo completa con ese código; un ejercicio sin código propio sigue sin completarse.

## Impact

- `apps/web-student/src/lib/cascadaCodigo.ts` (candidato y origen nuevos), `src/pages/EpisodePage.tsx` (hidratación, `siembraRef`, `huboEdicionRef`, guard), `src/lib/api.ts` (`getEntregaArtefacto`). Tests en `apps/web-student/tests/`.
- **Tesis**: el instrumento no cambia (ver design "Tesis: qué NO se toca"). **Matiz**: en los casos de cadena cortada, el primer `edicion_codigo` del episodio va a llevar en su `snapshot` el código entregado en vez del scaffold, y `diff_chars` se mide contra él. Es exactamente lo que REAPERTURA ya hace en producción desde el 24/09 en el caso común; esto sólo cubre el hueco. **Avisar a Cortez** junto con el aviso del otro change.
- Gobernanza: MEDIO. TDD estricto.
