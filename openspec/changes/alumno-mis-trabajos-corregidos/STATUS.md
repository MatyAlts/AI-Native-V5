# STATUS — alumno-mis-trabajos-corregidos

Estado: implementado (frontend-only, web-student). Falta 6.2 (prueba local con el stack, la corre Neyén).

## Baseline (antes de tocar nada, Node 26)
- `pnpm test`: 62 archivos, 668 tests, **0 rojos**, exit 0 (sin pipes). No hubo rojos ambientales de localStorage.
- `tsc --noEmit`: exit 0.
- `biome check src`: 18 errores, **todos de formato (CRLF), preexistentes** (incluye `index.css`). Ninguno en archivos nuevos.

## Después
- `pnpm test`: 65 archivos, **696 tests (+28)**, 0 rojos, exit 0.
- `tsc --noEmit`: exit 0. `biome check src`: los mismos 18 de formato, 0 de lint/organizeImports.
- Decisiones: D1-b, D2-a (solo "Ejercicio N", no se piden títulos), D3-a. La vista monta `GradeDetailView` SIN modificarlo y le suma debajo el bloque de código.

## Garantía de sólo lectura (4.1/4.2/4.3)
- Test real sobre el log de `fetch`: todas las requests son GET y ninguna matchea `/events`, `/close`, `/abandoned`, `/resume`, `/message`, `/reflection`, `classify`.
- Se verificó que el test no es tautológico: se inyectó a propósito un POST a `/episodes/zz/events/x` en la vista y el test rojo apareció; se revirtió.
- Eventos de pestaña (`visibilitychange`, `blur`, `pagehide`, `beforeunload`): cero requests.
- grep de imports prohibidos (`openEpisode|closeEpisode|resumeEpisode|emit*|sendMessage|classifyEpisode|createOrGetEntrega|submitEntrega|markEjercicioCompleted|reabrirEjercicio|CodeEditor|ExerciseListView`) en `TrabajoCorregidoView.tsx` y `trabajoCorregido.ts`: **vacío** (exit 1).

## 6.2 — Prueba local (para Neyén)
1. Levantar el stack local como indica `ai-native-tech/` (gateway con `DEV_TRUST_HEADERS=true`, evaluation, academic, tutor, ctr con workers) y `make dev`.
2. Con `seed-3-comisiones`, tener una entrega del alumno `b1b1b1b1-0001-0001-0001-000000000001` en estado calificada **con código guardado**: entregar un TP de varios ejercicios desde web-student y calificarlo desde web-teacher.
3. ANTES de mirar, en la base `ctr_store` anotar:
   - `SELECT count(*) FROM events;`
   - `SELECT id, events_count, last_chain_hash FROM episodes ORDER BY created_at DESC LIMIT 20;`
4. En web-student: Mis notas, click en la fila del TP. Debe verse nota, criterios y el código de cada ejercicio ("Ejercicio 1, 2, ..."). Apretar "Descargar" en cada uno y abrir el archivo: el cuerpo es el código entregado y la charla va comentada al pie.
5. En el navegador, F12, pestaña Network: todas las requests de la vista deben ser GET (ninguna POST).
6. DESPUÉS repetir las dos consultas del paso 3. Esperado: el mismo `count(*)` y los mismos `events_count` y `last_chain_hash`.
7. Archivar la TP desde web-teacher y repetir el paso 4: la fila sigue y el código se ve igual.
8. Devolver la entrega, reabrir un ejercicio en web-student y escribir algo sin re-entregar: la vista de Mis notas sigue mostrando el código corregido, no el nuevo.
Anotar el resultado acá abajo cuando se corra.

## Sin verificar
- Navegador real / stack completo / gateway (`/artefacto` por ROUTE_MAP): solo cubierto por tests con fetch mockeado. Se confirma en 6.2.
- El endpoint `/artefacto` fue pensado para el docente; si alguien lo restringe, estos tests no lo ven.
