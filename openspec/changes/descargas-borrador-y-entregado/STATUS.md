# STATUS — descargas-borrador-y-entregado

Base: `origin/main` 5cf07fc (PR #122 ya mergeado; `getEntregaArtefacto` en `apps/web-student/src/lib/api.ts` y `archivoDeDescarga` en `src/utils/trabajoCorregido.ts` existen, se reutilizan sin duplicar).

## Línea base (web-student, antes de tocar nada)
- vitest: 66 archivos, 703 tests, todos verdes
- tsc --noEmit: limpio
- biome check src: 1 error, `src/index.css` format (falso positivo CRLF conocido)

## Final
- vitest: 68 archivos, 727 tests, todos verdes (+24: 11 `descargas.test.ts`, 12 `ExerciseListViewDescargas.test.tsx`, 1 en `TrabajoCorregidoView.test.tsx`)
- tsc --noEmit: limpio
- biome check src: igual que la base (sólo `index.css`)

## TDD
- RED visto: `descargas.test.ts` rojo por import inexistente; `ExerciseListViewDescargas` 10 de 12 rojos (los 2 verdes son de comportamiento ya existente: el borrador sigue bajando el snapshot, y el aviso de error ya existía); `TrabajoCorregidoView` rótulo rojo.
- Negativos probados rojos: forzando `entregado: true` y `borrador: completado` en `botonesDeDescarga` fallan 6 tests ("no aparece"). Restaurado, verde.
- Solo lectura (3.6): el test afirma que al click las únicas requests son `GET /entregas/{id}/artefacto` y `GET /episodes/{id}`; antes del click no se pidió el artefacto (lectura perezosa). Nota: el "rojo agregando una llamada extra" no se hizo a mano; el `toEqual` exacto sobre la lista de URLs lo cubre por construcción.
- `Entrega.legacy?: boolean` agregado al tipo (el backend ya lo devuelve en `EntregaOut`): necesario para la regla D2 de legacy.

## Tesis
`git diff origin/main --stat -- ai-native-prompts apps/classifier-service apps/ctr-service packages/contracts apps/tutor-service apps/evaluation-service` → vacío.

## Pendiente
- 5.3 prueba local con stack: sin correr (ver `prueba-local.md`).
- 5.4 deuda de `openspec/specs/student-exercise-flow/spec.md` (`## ADDED Requirements` en el main spec): `openspec validate --strict` la sigue marcando; no se tocó, bloquea el archive, no el apply.
