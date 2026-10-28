## Why

Hay dos botones de descarga para el alumno y los dos dicen lo mismo, **"Descargar (.py)"**, pero bajan cosas distintas:

- **Pantalla de la TP** (`apps/web-student/src/components/ExerciseListView.tsx:561-572`, botón del PR #95): baja el código del **episodio vigente** del ejercicio (`getEpisodeState(...).last_code_snapshot`, `:240-255`). Es **el borrador**: lo último que el editor reportó, se haya entregado o no.
- **Mis notas → trabajo corregido** (`TrabajoCorregidoView.tsx`, PR #122 abierto, rama `feat/alumno-mis-trabajos-corregidos`): baja el **artefacto sellado** del submit (`GET /entregas/{id}/artefacto`, `getEntregaArtefacto`). Es **lo entregado**, lo que vio y corrigió el docente.

Mismo rótulo, contenido distinto: Neyén mismo los confundió (verificado el 23/10). Y el caso que más importa queda mal cubierto: con la TP **devuelta**, todos los ejercicios vuelven a `completado=false` (`routes/entregas.py:821-846`), así que el botón de la pantalla de la TP **desaparece** (sólo se muestra con `completed`, `ExerciseListView.tsx:561`) justo cuando el alumno necesita volver a ver lo que entregó para corregirlo.

Pedido de la lista de mejoras (mejora 4): *"dos botones de descarga, uno para el código en borrador y otro para la versión entregada y corregida"*.

## What Changes

- **Rótulos que dicen qué baja**: "Descargar borrador (.py/.java)" para el código del episodio y "Descargar lo entregado (.py/.java)" para el artefacto sellado. Aplica a las dos pantallas.
- **La pantalla de la TP ofrece también "lo entregado"** por ejercicio cuando la entrega ya se entregó alguna vez (`submitted_at` presente y no `legacy`): en `submitted`, `graded` y **`returned`**. Usa el mismo endpoint y la misma función de armado de archivo que la vista de #122. Sin backend nuevo.
- **"Borrador" sólo cuando hay borrador**: se muestra en ejercicios completados de una entrega editable (`draft` o `returned`), o de una entrega `legacy` (que no tiene artefacto sellado y hoy sólo tiene esta descarga). En `submitted`/`graded` no editable el borrador es, por construcción, lo mismo que lo entregado: mostrar los dos sería volver a la confusión.
- **Extensión**: no cambia la lógica. Borrador: `ejercicio.language ?? tarea.language ?? default` (como hoy). Lo entregado: `artefacto.language` (lo que quedó sellado).
- Ayuda contextual del alumno (`utils/helpContent.tsx`): una línea que explica la diferencia.

## Capabilities

### New Capabilities
- (ninguna)

### Modified Capabilities
- `student-exercise-flow`: la pantalla de la TP distingue la descarga del borrador de la descarga de lo entregado, con rótulos propios y reglas de cuándo aparece cada una; la vista de trabajo corregido usa el mismo rótulo para lo entregado.

## Impact

- **web-student únicamente**: `components/ExerciseListView.tsx`, `components/TrabajoCorregidoView.tsx` (existe sólo en #122), `utils/helpContent.tsx`, una función pura nueva en `utils/` para decidir qué botones mostrar. Tests en `apps/web-student/tests/`.
- **Backend**: ninguno. `GET /entregas/{id}/artefacto` ya existe en `main` y el alumno dueño lo puede leer (`routes/entregas.py:420-460`).
- **Dependencia**: PR #122 (aporta `getEntregaArtefacto`, `EntregaArtefacto`, `archivoDeDescarga` y la vista de trabajo corregido). Ver design D5.
- **Choque de archivo** con `publicar-nota-y-pedir-correccion` (toca `ExerciseListView.tsx`: lock, "Volver a abrir", badge): se aplica después y se rebasea.
- **Tesis**: nada. Sólo lecturas (`GET`), ninguna emisión al CTR. Ver design "Tesis: qué NO se toca".
- **Gobernanza**: BAJO (UI de sólo lectura). TDD estricto.
