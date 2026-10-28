# El alumno se queda con su trabajo corregido

## Why

Un alumno entrega un TP, el docente lo corrige, y **lo que el alumno hizo deja de
estar a mano**. Con #107 recuperó la nota y la devolución ("Mis notas"), pero no su
código: el único botón de descarga que existe (#95) vive en `ExerciseListView` y
sólo aparece mientras el ejercicio está `completado` — y una reapertura lo
des-marca y, al abrir el episodio nuevo, pisa el `episode_id` de la entrega.

Se decidió: **una vista de sólo lectura, "Mis trabajos corregidos"**, donde el
alumno ve por TP su nota y la devolución por criterio, y por ejercicio el código
que entregó, con un botón "Descargar" que reusa el util de #95.

## Lo que se verificó contra el código (2026-10-20)

| Supuesto de las notas del 16/10 | Contra el código |
|---|---|
| "Nota por ejercicio" | **No existe.** La `Calificacion` es por **entrega** (TP): `nota_final`, `feedback_general`, `detalle_criterios` (`evaluation-service/models/entregas.py:162-177`). La vista muestra nota y criterios **por TP**, y código **por ejercicio**. |
| El código final sale del episodio | Hay una fuente mejor: `GET /api/v1/entregas/{id}/artefacto` (`routes/entregas.py:420-459`) devuelve **el código que el alumno entregó**, sellado con hash en el submit, uno por ejercicio, y el dueño lo puede leer. Cada artefacto guarda **su propio `episode_id`** — no lo pisa la reapertura. |
| Reusar `ExerciseListView` | **No se puede.** Al montar llama `createOrGetEntrega`, que es un **POST**. Esta vista no lo monta. |
| Reusar el detalle de #107 | Sí: `GradeDetailView` sólo hace `GET /calificacion`. La lista de "Mis notas" (`MisNotasPage.tsx`) ya trae las entregas con nota, incluidas las de TPs archivadas. |

## What Changes

- **Frontend (web-student), nuevo**: la vista del trabajo corregido de una entrega
  `graded`/`returned` — encabezado del TP con nota + devolución por criterio
  (reusando `GradeDetailView` o su contenido) y, debajo, un bloque por ejercicio
  con el código entregado y un botón "Descargar (.py/.java)".
- **Frontend, nuevo cliente**: `getEntregaArtefacto(entregaId)` en `lib/api.ts`
  contra el endpoint que **ya existe**. No hay endpoint nuevo.
- **Descarga**: reusa `buildEpisodioSourceFile` (`utils/episodioDownload.ts`) sin
  cambiar su contrato. El código viene del artefacto; la charla con el tutor, del
  episodio que el **artefacto** nombra (`GET /api/v1/episodes/{id}`, dueño-o-nada).
- **Backend: ninguno.** Si la decisión abierta D2 se resuelve por el lado del
  backend, sería un campo opcional en un GET existente — nunca un write.

## Restricciones duras (no negociables)

1. **No altera los resultados de la tesis ni del paper.** Estrictamente sólo
   lectura: cero eventos nuevos al CTR, cero escrituras a la cadena, no abre ni
   crea episodios, no toca clasificación N4, analytics ni nada que el paper
   consuma. Ver y descargar **no emite telemetría al CTR**. El `design.md` lista
   cada llamada que hace la vista, con archivo:línea, y por qué ninguna escribe.
2. **v1 muestra sólo el ÚLTIMO intento por ejercicio** (el que está sellado en
   los artefactos de la entrega). Los intentos previos a una reapertura quedan
   **fuera de alcance**.
3. **Frontend-only.** Si algo de backend resultara inevitable, sería un GET sin
   efectos laterales y con justificación escrita.
4. **TDD estricto** en el apply: test rojo primero, con vitest de web-student.
5. **Prueba local reproducible**: una tarea describe cómo verificarlo a mano.
6. **Gobernanza MEDIUM**: las decisiones abiertas van abajo, no se toman calladas.

## Decisiones tomadas (Neyén, 2026-10-20)

- **D1 = (b)**: la fila de "Mis notas" (#107) abre el trabajo completo. No hay ruta nueva.
- **D2 = (a)**: se muestra "Ejercicio N", sólo frontend. Mínimo de código tocado: ni siquiera se piden los títulos.
- **D3 = (a)**: entregas viejas sin código guardado lo dicen con palabras, sin descarga.
- Sólo el último intento por ejercicio; los previos a una reapertura quedan fuera.

## Decisiones abiertas (historial — ya resueltas arriba)

**D1. ¿Dónde vive la vista?**
Hoy "Mis notas" ya lista las entregas con nota por comisión (TPs archivadas
incluidas, picker de comisión, aviso del límite de 50) y abre `GradeDetailView`.
- (a) **Ruta nueva** `/mis-trabajos-corregidos` con su propia lista. Dos pantallas
  con la misma lista de entregas, que van a derivar por separado.
- (b) **Una sola puerta**: la fila de "Mis notas" abre el trabajo corregido
  completo (nota + criterios + código + descarga) en vez de sólo la nota.
- **Recomendado: (b).** Mismo dato, una lista, cero duplicación; el título de la
  vista de detalle es "Tu trabajo corregido". (a) se puede sumar después con un
  archivo de ruta, porque el componente se diseña independiente de dónde se monte.

**D2. El título de cada ejercicio en un TP archivado.**
El artefacto trae `ejercicio_id` y `orden`, no el título. El título sale de
`GET /tareas-practicas/{id}/ejercicios`, que **le da 404 al alumno si la TP no
está `published`** (`academic-service/routes/tareas_practicas.py:648`).
- (a) Frontend-only: pedir los títulos; si falla, mostrar "Ejercicio N". En un TP
  archivado el alumno ve "Ejercicio 1, 2, 3" con su código.
- (b) Backend: sumar `ejercicio_titulo` opcional a `ArtefactoOut` con un batch
  (mismo patrón que `tarea_titulo` en #107). GET existente, sin efectos laterales.
- **Recomendado: (a) en v1**, y (b) como change aparte si el "Ejercicio N" molesta.

**D3. Entregas `legacy` (sin artefactos guardados).**
Las entregas anteriores a que se persistiera el código no tienen artefactos.
- (a) Decirlo con palabras: "Esta entrega es anterior a que la plataforma
  guardara el código entregado". Sin descarga.
- (b) Caer al último snapshot del episodio de `ejercicio_estados`.
- **Recomendado: (a).** El `episode_id` de `ejercicio_estados` puede apuntar al
  intento posterior a una reapertura; mostrarlo como "lo corregido" mentiría.

## Non-goals (trabajo futuro)

- **Intentos anteriores a una reapertura.** El episodio viejo sigue existiendo y
  firmado, pero listarlos pide decidir cómo se presentan N intentos. Change aparte.
- El enunciado de un TP archivado (camino (B) de #107, toca control de acceso).
- Una entrega `returned` que el alumno **ya re-entregó** (`submitted`): pasa a
  "sin corregir" y su corrección vieja no se muestra con el código nuevo —
  mezclarlos atribuiría la nota a un código que el docente no vio.
- Descargar todo el TP en un zip.

## Capabilities

### New Capabilities
- `student-corrected-work`: el alumno ve y descarga, en sólo lectura, su trabajo
  corregido — nota y devolución por criterio por TP, y código entregado por
  ejercicio — sin emitir eventos ni escribir nada.

### Modified Capabilities
- Ninguna. `student-grades-view` no cambia de comportamiento: se reusa su
  detalle, no se redefine.

## Impact

- `apps/web-student/src/lib/api.ts` — cliente `getEntregaArtefacto` + tipos.
- `apps/web-student/src/components/` — componente nuevo del trabajo corregido.
- `apps/web-student/src/pages/MisNotasPage.tsx` — si D1 = (b), el `selected`
  monta el componente nuevo en lugar de `GradeDetailView` pelado.
- `apps/web-student/src/utils/episodioDownload.ts` — se reusa sin cambios.
- `apps/web-student/tests/` — tests nuevos (vitest).
- Backend, CTR, tutor-service, analytics, classifier: **sin cambios**.
