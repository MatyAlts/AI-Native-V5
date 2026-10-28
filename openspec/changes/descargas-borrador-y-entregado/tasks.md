Gobernanza BAJO, TDD estricto: cada grupo es RED (test que falla por la razón correcta) → GREEN (mínimo código) → TRIANGULAR → REFACTOR. Cada test negativo ("no aparece el botón") se prueba rojo forzando la condición y se anota en `STATUS.md`.

- Frontend: `cd apps/web-student && pnpm test` (bajo Node 26 los rojos de `localStorage` locales son falsos: anotarlos, no arreglarlos), `pnpm exec tsc --noEmit`, `pnpm exec biome check src`.

## 1. Línea base y dependencia

- [x] 1.1 Verificar la base (design D5): si #122 está mergeado, rama desde `main`; si no, desde `origin/feat/alumno-mis-trabajos-corregidos`. Confirmar que existen `getEntregaArtefacto` en `apps/web-student/src/lib/api.ts` y `archivoDeDescarga` en `src/utils/trabajoCorregido.ts`. Verificación: anotado en `STATUS.md` con el hash de la base.
- [x] 1.2 Crear `STATUS.md`. Correr `pnpm test`, `tsc` y `biome` en web-student y anotar números y rojos preexistentes. Verificación: números en `STATUS.md`.

## 2. Lógica pura: rótulos y visibilidad

- [x] 2.1 RED: `apps/web-student/tests/descargas.test.ts` para `rotuloDescarga(tipo, language)`: `("borrador","python")` → "Descargar borrador (.py)"; `("entregado","java")` → "Descargar lo entregado (.java)"; `language` desconocido o nulo → `.py`. Verificación: rojo por import inexistente.
- [x] 2.2 GREEN: `apps/web-student/src/utils/descargas.ts` con `rotuloDescarga`. Verificación: verde.
- [x] 2.3 RED: tests de `botonesDeDescarga({estado, legacy, submittedAt, completado})` con las seis filas de la tabla de design D2. Verificación: rojo.
- [x] 2.4 GREEN + TRIANGULAR: implementarla; sumar el caso `returned` con `submittedAt=null` (dato inconsistente) → sin "entregado". Verificación: verde.

## 3. Pantalla de la TP (`ExerciseListView.tsx`)

- [x] 3.1 RED: en `apps/web-student/tests/ExerciseListView.test.tsx` (o `ExerciseListViewDescargas.test.tsx` nuevo): en `draft` con el 1 completado aparece `ejercicio-descargar-1` con texto "Descargar borrador (.py)" y no aparece `ejercicio-descargar-entregado-1`. Verificación: rojo por el rótulo viejo.
- [x] 3.2 GREEN: usar `rotuloDescarga` y `botonesDeDescarga` en la fila. Los tests existentes del botón (ADE-02) se actualizan sólo en el rótulo. Verificación: verde.
- [x] 3.3 RED: `graded` → aparece "Descargar lo entregado (.py)" y no el borrador; `returned` con ejercicios sin completar → aparece "lo entregado"; `returned` con el 2 re-completado → los dos; `legacy` `graded` → sólo borrador. Probar rojo cada "no aparece". Verificación: rojo.
- [x] 3.4 GREEN: botón `ejercicio-descargar-entregado-{orden}`; al click `getEntregaArtefacto(entrega.id)`, artefacto del `orden`, `archivoDeDescarga` (charla del `artefacto.episode_id`), blob + `a.download`. Spinner y aviso por `orden` y tipo (design D3). Verificación: verde; el test afirma que el contenido descargado es el `codigo` del artefacto y no el `last_code_snapshot`.
- [x] 3.5 TRIANGULAR: artefacto ausente para ese `orden` → aviso con palabras, nada descargado; `getEntregaArtefacto` falla → aviso en `descarga-error`, los otros botones siguen; charla falla → descarga igual + aviso; artefacto Java → archivo `.java`. Verificación: verde.
- [x] 3.6 Sólo lectura: el test de 3.4 afirma que las únicas llamadas de red al descargar son `GET /entregas/{id}/artefacto` y `GET /episodes/{id}` (ningún POST/PATCH). Probar rojo agregando a mano una llamada extra. Verificación: verde.

## 4. Mis notas y ayuda

- [x] 4.1 RED→GREEN: en `apps/web-student/tests/TrabajoCorregidoView.test.tsx` el botón dice "Descargar lo entregado (.py)" / "(.java)"; cambiar `TrabajoCorregidoView.tsx` para usar `rotuloDescarga("entregado", artefacto.language)`. Verificación: verde.
- [x] 4.2 Ayuda: en `apps/web-student/src/utils/helpContent.tsx` (sin tildes, regla del help system), una línea que explica "borrador = lo que tenes ahora en el editor; lo entregado = lo que vio tu docente". Si hay test que ancle el texto, actualizarlo. Verificación: `pnpm test` verde.

## 5. Chequeos finales

- [x] 5.1 Tesis: `git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/evaluation-service` → **vacío** (si la base es la rama de #122, comparar contra esa base). Verificación: salida pegada en `STATUS.md`.
- [x] 5.2 Suites web-student completas, `tsc`, `biome` contra la línea base de 1.2. Verificación: sin rojos nuevos; números en `STATUS.md`.
- [x] 5.3 Correr la "Prueba local reproducible" de `design.md` (pasos 1–8) y anotar el resultado por paso en `STATUS.md`.
- [ ] 5.4 Deuda preexistente que bloquea el archive (no el apply): `openspec/specs/student-exercise-flow/spec.md` arranca con `## ADDED Requirements` en vez de `## Purpose` + `## Requirements`. Si `publicar-nota-y-pedir-correccion` (su tarea 7.5) no lo corrigió todavía, corregir sólo esos encabezados antes de `/opsx:archive`. Verificación: `openspec validate descargas-borrador-y-entregado --strict` sin "Archive would refuse".
