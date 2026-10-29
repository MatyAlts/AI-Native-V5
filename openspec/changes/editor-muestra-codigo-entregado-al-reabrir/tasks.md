Gobernanza MEDIO, TDD estricto (RED → GREEN → TRIANGULAR → REFACTOR). Todo corre desde `apps/web-student` con `pnpm test` (vitest; el CI lo corre). Bajo Node 26, los rojos de `localStorage` del baseline son ambientales: anotarlos en `STATUS.md`, no arreglarlos. Cada test negativo se prueba rojo quitando su condición y se anota.

Antes de empezar: `gh pr view 122 --json state`. Si está `MERGED`, rebasar sobre `main` y saltear 3.1 (reusar `getEntregaArtefacto`).

## 1. Línea base y reproducción

- [x] 1.1 Crear `STATUS.md`. Correr `pnpm test`, `pnpm exec tsc --noEmit`, `pnpm exec biome check src` y anotar números y rojos preexistentes (CRLF de biome incluidos). Verificación: números en `STATUS.md`.
- [x] 1.2 (NO hecha con UI: sin navegador; el RED de `TpDevueltaCerrarSinEditar.test.tsx` reproduce el bloqueo contra el guard viejo, ver STATUS.md) Reproducción manual ANTES del fix con los pasos 1–7 de "Prueba local" de `design.md`. Anotar qué mostró el editor en el paso 6 (esperado por código: el código previo, vía REAPERTURA) y en el paso 7 (esperado: scaffold/placeholder, cadena cortada), y si el ej. 2 quedó bloqueado. Si el paso 6 NO reproduce el bloqueo, frenar y avisar: el diagnóstico está mal.

## 2. Cascada pura (`lib/cascadaCodigo.ts`)

- [x] 2.1 RED: en `tests/cascadaCodigo.test.ts`, `codigoEntregado` gana a los dos scaffolds y al placeholder (origen `"codigo-entregado"`); pierde contra `borradorLocal` y contra `snapshot`. Verificación: rojo (tipo/origen inexistente).
- [x] 2.2 GREEN: agregar el candidato y el origen. Los tests existentes de la cascada (incluido «LA regla: el arrastre no pisa al docente») siguen verdes. Verificación: verde.

## 3. Hidratación (`EpisodePage.tsx`)

- [x] 3.1 Agregar `getEntregaArtefacto` + tipos a `src/lib/api.ts`, **idénticos** al PR #122 (`git show origin/feat/alumno-mis-trabajos-corregidos:apps/web-student/src/lib/api.ts`). Verificación: `tsc --noEmit` exit 0 y el bloque sin diferencias contra esa rama.
- [x] 3.2 RED: `tests/ReaperturaSiembraCodigoEntregado.test.tsx` (andamiaje de `CerrarMarcaEjercicioCompletado.test.tsx` / `CodigoPrevioSiembra.test.tsx`): episodio con `last_code_snapshot: null`, sin borrador, artefacto con código para el mismo `orden`+`ejercicio_id` → el editor arranca con ese código. Verificación: rojo.
- [x] 3.3 GREEN: en la hidratación, si hay `ejercicioContext` y `borradorLocal` y `snapshot` vacíos, pedir el artefacto y pasar `codigoEntregado` a la cascada; guardar el resultado en `siembraRef`. Verificación: verde.
- [x] 3.4 TRIANGULAR: (a) con snapshot → 0 GET a `/artefacto`; (b) artefacto de otro `orden`/`ejercicio_id` → scaffold/placeholder (probar rojo quitando el match); (c) GET 500 / `legacy` / código vacío → scaffold/placeholder y la hidratación no falla; (d) TP monolítica → 0 GET. Verificación: verde.
- [x] 3.5 No-emisión: montar con origen `codigo-entregado`, esperar más que el debounce, flush → **0** `edicion_codigo`. Teclear una letra → 1 `edicion_codigo` con `diff_chars` = 1. Verificación: verde (protege la tesis).

## 4. Cierre sin editar (`markEjercicioCompletedOnce`)

- [x] 4.1 RED: en `tests/TpDevueltaCerrarSinEditar.test.tsx`, `localStorage` vacío, episodio con snapshot heredado (o código entregado), cerrar sin tipear → exactamente 1 PATCH `completado:true` con el `episode_id` actual. Repetir por "Siguiente ejercicio →" y por el cierre del `ReflectionModal`. Verificación: rojo por 0 PATCH (no por error de import/mock).
- [x] 4.2 GREEN: `huboEdicionRef` en `onEditDebounced`; paso 3 del guard de D2 (guardar borrador con la siembra y marcar). Comentario corto que apunte a este change y a BUG-1. `CerrarMarcaEjercicioCompletado.test.tsx` sigue verde. Verificación: verde.
- [x] 4.3 TRIANGULAR, cada negativo probado rojo: (a) BUG-1: siembra scaffold/placeholder → 0 PATCH; (b) editó y dejó vacío → 0 PATCH; (c) tipeó código → 1 PATCH con su borrador (precedencia intacta); (d) tras el cierre, `collectArtefactoDrafts(entregaId, [orden])` devuelve el código mostrado con el `episode_id` actual; (e) cerrar + "Siguiente ejercicio" → 1 PATCH total; (f) ese borrador NO siembra un episodio nuevo de otro `episode_id` (la cascada lo descarta). Verificación: verde + notas en `STATUS.md`.

## 5. Refactor

- [x] 5.1 Si la resolución del candidato en `EpisodePage` pasa de ~20 líneas, extraerla a una función chica en `src/lib/` sin cambiar comportamiento. Verificación: `pnpm test` verde tras cada paso.

## 6. Chequeos finales

- [x] 6.1 Tesis: `git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/web-student/src/components/CodeEditor.tsx apps/web-student/src/lib/edicionPendiente.ts` → **vacío**; y `git diff origin/main --stat` no toca nada fuera de `apps/web-student` y `openspec/`. Verificación: salida en `STATUS.md`.
- [x] 6.2 `pnpm test`, `tsc --noEmit`, `biome check src` contra la línea base. Verificación: sin rojos nuevos.
- [x] 6.3 (parcial: contrato `/artefacto` contra backend real + tests de componente; la UI real queda para un humano, ver prueba-local.md) Correr la "Prueba local reproducible" de `design.md` completa (pasos 1–11) y anotar resultado por paso, incluida la lista de `event_type` antes/después sin tipos nuevos.
- [x] 6.4 Sumar al aviso a Cortez (ver `publicar-nota-y-pedir-correccion` tarea 7.4) el matiz de D-Tesis: primer `edicion_codigo` de reaperturas con cadena cortada arranca del código entregado; cierres sin cambios cuentan como completados.
- [x] 6.5 Deuda que bloquea el archive (no el apply): el main spec `openspec/specs/student-exercise-flow/spec.md` arranca con `## ADDED Requirements`; si no lo arregló ya el otro change (su tarea 7.5), corregir el encabezado antes de `/opsx:archive`.
