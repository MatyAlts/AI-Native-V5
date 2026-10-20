# Tareas — alumno-mis-trabajos-corregidos

Frontend-only (`apps/web-student`). TDD estricto: cada tarea arranca con el test
**rojo** y se corre para verlo fallar antes de escribir código. Runner: vitest
(`cd apps/web-student && pnpm test`). **El CI no corre vitest**: la verificación
es local. Bajo **Node 26** los rojos de `localStorage` son falsos — se anotan en
el baseline, no se arreglan.

Asume las decisiones recomendadas del proposal (D1-b, D2-a, D3-a). Donde una
elección distinta cambie la tarea, está marcado.

## 0. Red de seguridad

- [x] 0.1 Correr `pnpm test` y `pnpm exec tsc --noEmit` en `apps/web-student` y anotar el baseline con el **exit code real** (sin pipes: `pnpm test | tail` devuelve el código de `tail`). Verificación: el número de verdes/rojos queda escrito en el `STATUS.md` de la change, separando los rojos ambientales de `localStorage` (Node 26). Si algo falla ya, no se arregla: se anota como pre-existente.
- [x] 0.2 Confirmar que `GradeDetailView.test.tsx`, `MisNotasPage.test.tsx` y `episodioDownload.test.ts` están en verde — son la red de lo que se reusa. Verificación: los tres pasan solos (`pnpm test -- tests/GradeDetailView.test.tsx` etc.).

## 1. Cliente del artefacto

- [x] 1.1 RED: test en `tests/getEntregaArtefacto.test.ts` que mockea `fetch` y afirma que `getEntregaArtefacto(id)` hace **GET** a `/api/v1/entregas/{id}/artefacto` y devuelve `artefactos` tipados (`orden, ejercicio_id, episode_id, codigo, language, sha256`). Verificación: falla porque la función no existe.
- [x] 1.2 GREEN: `getEntregaArtefacto` + tipos `EntregaArtefacto`/`Artefacto` en `src/lib/api.ts`, espejando `EntregaArtefactoOut` (`evaluation-service/schemas/entrega.py:82-105`). Verificación: 1.1 pasa.
- [x] 1.3 TRIANGULAR: un 404 tira un error distinguible (con `status`) de un 500 — la vista los muestra distinto. Verificación: test de los dos casos en verde.

## 2. Lógica pura (`src/utils/trabajoCorregido.ts`)

- [x] 2.1 RED → GREEN: `esTrabajoCorregido(entrega)` — `true` para `graded`/`returned`, `false` para `draft`/`submitted`. Verificación: test con los cuatro estados.
- [x] 2.2 RED → GREEN: `ejerciciosDelTrabajo(artefactos, titulos?)` — ordena por `orden`; usa el título si viene en el mapa por `ejercicio_id`, si no "Ejercicio N". Triangular: artefactos desordenados; sin títulos (TP archivada); títulos parciales; lista vacía (legacy). Verificación: los cuatro casos en verde.
- [x] 2.3 RED → GREEN: `archivoDeDescarga(artefacto, messages | null, meta)` — delega en `buildEpisodioSourceFile` **sin cambiar su contrato**; el cuerpo es exactamente `artefacto.codigo`; extensión por `artefacto.language`; con `messages = null` arma el archivo sin charla. Triangular: Python vs Java; con y sin charla. Verificación: tests en verde y `episodioDownload.test.ts` sigue en verde sin tocarlo.
- [x] 2.4 REFACTOR: nombres y duplicación, tests verdes después de cada paso.

## 3. La vista `TrabajoCorregidoView`

- [x] 3.1 RED: test de render con `fetch` mockeado — una entrega `graded` con 3 artefactos muestra título del TP, nota, devolución, criterios y tres bloques de código en orden. Verificación: falla porque el componente no existe.
- [x] 3.2 GREEN: `src/components/TrabajoCorregidoView.tsx`. El bloque de calificación reusa el render de `GradeDetailView` (extraer `CalificacionDetalle` presentacional, **sin cambiar lo que `GradeDetailView` muestra**; si la extracción resulta invasiva, montar `GradeDetailView` tal cual). Código en `<pre>` de sólo lectura, **no** `CodeEditor`. Verificación: 3.1 pasa y `GradeDetailView.test.tsx` sigue verde.
- [x] 3.3 TRIANGULAR estados, uno por test: `returned` (cartel con palabras); legacy sin artefactos (mensaje de D3-a, sin botones de descarga, nota visible); falla el artefacto (mensaje distinto del legacy); 404 del artefacto (no disponible); título no resoluble → "Ejercicio N"; cargando → skeleton. Verificación: los seis en verde.
- [x] 3.4 RED → GREEN: botón "Descargar (.py/.java)" por ejercicio. Al click pide `getEpisodeState(artefacto.episode_id)` — **no** el `episode_id` de `ejercicio_estados` — arma con `archivoDeDescarga` y descarga con Blob + `<a download>`. Triangular: la charla falla → se descarga igual el código y se avisa; error en el ejercicio 2 no deshabilita los demás; spinner sólo en SU botón. Verificación: tests en verde, afirmando el `episode_id` pedido y el contenido del Blob.
- [x] 3.5 Accesibilidad: test que recorre con teclado (Tab/Enter) volver y cada "Descargar", con foco visible; la nota tiene texto, no sólo color. Verificación: test en verde.

## 4. Garantía de sólo lectura (restricción dura 1)

- [x] 4.1 RED → GREEN: test de integración que monta la vista, descarga **todos** los ejercicios, y afirma sobre el log de `fetch` que (a) todas las requests son `GET` y (b) ninguna URL matchea `/events/`, `/close`, `/abandoned`, `/resume`, `/message`, `/reflection`, `classify` ni es `POST /api/v1/entregas`. Para verlo rojo primero: hacerlo correr contra un stub que emite un POST y confirmar que falla. Verificación: verde contra la vista real.
- [x] 4.2 Test: montar la vista, disparar `visibilitychange` y `beforeunload` → cero requests. Verificación: en verde.
- [x] 4.3 `grep` de imports en `TrabajoCorregidoView.tsx` y `trabajoCorregido.ts`: ninguno importa `openEpisode`, `closeEpisode`, `resumeEpisode`, `emit*`, `sendMessage`, `classifyEpisode`, `createOrGetEntrega`, `submitEntrega`, `markEjercicioCompleted`, `reabrirEjercicio`, `CodeEditor` ni `ExerciseListView`. Verificación: el grep devuelve vacío y queda pegado en el `STATUS.md`.

## 5. Montaje (D1)

- [x] 5.1 RED → GREEN (D1-b): en `MisNotasPage.test.tsx`, click en una fila `graded`/`returned` monta `TrabajoCorregidoView`; una fila `submitted` sigue montando `GradeDetailView`. Cambio en `src/pages/MisNotasPage.tsx:278-280`. Verificación: tests nuevos y los existentes de "Mis notas" en verde.
  - *Si D1 = (a)*: en su lugar, `src/routes/mis-trabajos-corregidos.tsx` + link en `routes/index.tsx` junto al de "Mis notas", reusando `agruparEntregas().conNota`; `routeTree.gen.ts` lo regenera el plugin, no se edita a mano.
- [x] 5.2 Ayuda in-app: si la vista es una página nueva, `HelpButton`/`helpContent` según `.claude/skills/help-system-content/SKILL.md`; si es el detalle de "Mis notas", actualizar la entry existente para mencionar el código y la descarga. Verificación: test o grep de la key.

## 6. Cierre

- [x] 6.1 Suite completa `pnpm test` + `pnpm exec tsc --noEmit` + `pnpm biome check src` (ojo: `index.css` en rojo por CRLF en local es falso positivo). Verificación: mismo baseline de 0.1 más los tests nuevos en verde; cualquier rojo nuevo explicado.
- [ ] 6.2 (PENDIENTE — la corre Neyén, pasos en STATUS.md) Prueba local reproducible (Neyén la corre solo). Verificación: los pasos de abajo dan lo esperado y el resultado queda en el `STATUS.md`.
  1. Levantar el stack local según `ai-native-tech/` (gateway con `DEV_TRUST_HEADERS=true`, evaluation, academic, tutor, ctr con workers) y `make dev`.
  2. Con `seed-3-comisiones`, tener una entrega del alumno `b1b1b1b1-0001-…` en `graded` **con artefactos** (entregar un TP multi-ejercicio desde la app y calificarlo desde web-teacher).
  3. **Antes de mirar**: anotar `SELECT count(*) FROM events;` en `ctr_store` y `SELECT id, events_count, last_chain_hash FROM episodes WHERE id IN (<episode_id de los artefactos>);`.
  4. En web-student: Mis notas → la fila del TP → ver nota, criterios y el código de cada ejercicio. Descargar cada uno y abrir el archivo: el cuerpo es el código entregado; la charla va comentada al pie.
  5. En DevTools → Network: todas las requests de la vista son `GET`.
  6. **Después**: repetir las consultas del paso 3. Esperado: **mismo** `count(*)`, mismos `events_count` y `last_chain_hash`.
  7. Archivar la TP desde web-teacher y repetir el paso 4: sigue visible (con "Ejercicio N" si los títulos no resuelven).
  8. Devolver la entrega, reabrir un ejercicio en el web-student y escribir algo sin re-entregar: la vista sigue mostrando el código **corregido**, no el nuevo.
- [x] 6.3 Actualizar `STATUS.md` de la change con baseline, resultado de la suite, salida del grep de 4.3 y resultado de 6.2; y la ayuda in-app si cambió el texto. Verificación: archivo presente con los cuatro bloques.
