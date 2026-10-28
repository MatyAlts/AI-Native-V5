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
- 5.3 prueba local con stack: CORRIDA el 2026-10-28 (ver abajo).
- 5.4 deuda de `openspec/specs/student-exercise-flow/spec.md` (`## ADDED Requirements` en el main spec): `openspec validate --strict` la sigue marcando; no se tocó, bloquea el archive, no el apply.

## Prueba local 5.3 (2026-10-28, Playwright + chromium, stack local, TP SMK-PE92D 2 ejercicios Python)
- Paso 3 borrador: ejercicio completado muestra SOLO 'Descargar borrador (.py)'; el archivo dice `print("v1")`. OK
- Paso 4 entregada: cada ejercicio muestra SOLO 'Descargar lo entregado (.py)'; bajan `print("v1")` y `print("dos")`. OK
- Paso 5 devuelta (calificar+devolver hechos por API, no por UI docente): ambos ejercicios sin completar muestran 'Descargar lo entregado'. OK
- Paso 6: ejercicio 1 reabierto, `print("v2")`, cerrado sin entregar: aparecen los DOS botones; borrador baja v2, entregado baja v1. OK
- Paso 7 Mis notas: rotulo 'Descargar lo entregado (.py)', baja `print("v1")`/`print("dos")`. OK
- Paso 8 CTR: los cambios de conteo en ctr_store (edicion_codigo +3, episodio_abierto +1, episodio_cerrado +3) vienen de los episodios que se trabajaron; repetir descargas (Mis notas x2) no movio ningun event_type. Sin event_type nuevo. OK
- Capturas: `capturas-prs-128-130/128-0*.png`.
