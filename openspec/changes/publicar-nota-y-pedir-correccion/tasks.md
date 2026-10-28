Gobernanza MEDIO, TDD estricto: cada grupo es RED (test que falla por la razón correcta) → GREEN (mínimo código) → TRIANGULAR → REFACTOR. Cada test negativo (409/422/"no cambia") se prueba rojo quitando su guard y se anota en `STATUS.md`.

- Python, desde la raíz del repo: `uv run pytest apps/evaluation-service -q` (scope del servicio; no usar `make test-fast`). Rojos ambientales conocidos: memoria "Los rojos de Python son ambientales".
- Frontend: `cd apps/web-student && pnpm test` y `cd apps/web-teacher && pnpm test` (el CI corre vitest; bajo Node 26 los rojos de `localStorage` locales son falsos: anotarlos, no arreglarlos).

## 1. Línea base

- [x] 1.1 Crear `STATUS.md` del change. Correr `uv run pytest apps/evaluation-service -q`, `pnpm test` en web-student y web-teacher, `pnpm exec tsc --noEmit` y `pnpm exec biome check src` en los dos frontends; anotar números y rojos preexistentes. Verificación: los números quedan en `STATUS.md`.

## 2. Backend — `ordenes_a_corregir` y el esquema (pura)

- [x] 2.1 RED: en `apps/evaluation-service/tests/unit/test_pedir_correccion.py`, tests de la función pura `ordenes_a_corregir(estados)`: sin marcas → todos los `orden`; con marcas en 2 y 4 → `{2, 4}`; lista vacía → vacío. Verificación: rojo por import inexistente.
- [x] 2.2 GREEN: implementarla en `routes/entregas.py` (o `services/`), y sumar `reabierto_por_docente: bool = False` a `EjercicioEstadoSchema` (`schemas/entrega.py`). Test extra: un dict legacy sin la clave deserializa con `False`. Verificación: verde.

## 3. Backend — `POST /return` con `ordenes`

- [x] 3.1 RED: `_reabrir_ejercicios(estados, ordenes)` con `ordenes=[2]` sobre 3 ejercicios completados → sólo el 2 queda `completado=False`, `completed_at=None`, `reabierto_por_docente=True`; 1 y 3 intactos (incluido `episode_id`); copia profunda. Verificación: rojo.
- [x] 3.2 GREEN + compat: con `ordenes=None` reabre todos y los marca (los 5 tests existentes de `tests/unit/test_devolucion_reabre_ejercicios.py` siguen verdes). Verificación: verde.
- [x] 3.3 RED→GREEN: `ReturnEntregaBody` opcional en el endpoint; 422 para lista vacía, duplicados y `orden` inexistente (cada uno probado rojo sin su validación); 409 si no está `graded` (sin cambio). Log structlog `tp_correccion_pedida` con `ordenes` y `parcial` (no CTR). Verificación: verde + notas en `STATUS.md`.

## 4. Backend — re-entrega parcial y PATCH

- [x] 4.1 RED: submit de una entrega `returned` con marcas en el 2, mandando código sólo del 2 → 201/200, artefactos de 1 y 3 con el mismo `codigo`, `sha256` y `episode_id` de antes; `artefacto_sha256` recalculado; ninguna marca queda. Verificación: rojo por 422 "Falta el código de los ejercicios: [1, 3]".
- [x] 4.2 GREEN: en `submit_entrega`, faltantes sólo sobre `ordenes_a_corregir` (+ no reabiertos sin artefacto previo); copiar artefactos previos de los no reabiertos dentro de `_persistir_artefactos`. Las marcas **no** se limpian en el submit: `_reabrir_ejercicios` las reescribe (`true`/`false`) en cada devolución (D4, 28/10); web-student usa `devolucionParcialVigente` (sólo `returned`). Verificación: verde.
- [x] 4.3 TRIANGULAR: (a) el cliente manda código distinto para 1 y 3 → se conserva el sellado; (b) devolución legacy sin marcas → exige todos como hoy (probar rojo quitando la rama legacy); (c) entrega legacy sin artefactos previos + devolución parcial → exige el código de los no reabiertos al cliente. Verificación: verde.
- [x] 4.4 RED→GREEN: `PATCH /ejercicio/{orden}` en `returned` parcial sobre un `orden` no reabierto → 409 en los dos sentidos, sin cambios en la entrega; sobre el reabierto → 200 como hoy; en `draft` nada cambia. Probar rojo quitando el guard. Verificación: verde.
- [x] 4.5 Ciclo completo con re-calificación (PR #124): pedir corrección parcial → re-entrega → `PATCH /calificacion` → `graded` → pedir corrección de otro ejercicio → sólo ese queda reabierto. Verificación: verde. Si hay suite de integración con DB (`tests/integration/`), sumar un caso ahí también.

## 5. web-student

- [x] 5.1 RED: `apps/web-student/tests/estaBloqueado.test.ts` para la función pura de D6: avance normal; devolución "2 y 4" de 5 (2 libre, 4 bloqueado, 1/3/5 nunca bloqueados); devolución total; el caso `draft` con "Volver a abrir" del 1 (el 3 pendiente queda bloqueado). Verificación: rojo por import.
- [x] 5.2 GREEN: `apps/web-student/src/lib/estaBloqueado.ts` y reemplazar `isLocked` en `ExerciseListView.tsx:349`. `ExerciseListView.test.tsx` y `ExerciseListViewDevolucion.test.tsx` siguen verdes. Verificación: verde.
- [x] 5.3 RED→GREEN: en `ExerciseListViewDevolucion.test.tsx` (o archivo nuevo), devolución parcial: badge "A corregir" en el reabierto, sin "Volver a abrir" en los no reabiertos; legacy sin marcas: como hoy. Tipo `EjercicioEstado.reabierto_por_docente?: boolean` en `lib/api.ts`. Probar rojo el "sin Volver a abrir". Verificación: verde.

## 6. web-teacher

- [x] 6.1 RED: `apps/web-teacher/tests/CorreccionesView.test.tsx`: el botón de primera calificación dice "Publicar nota"; en `graded` aparece "Pedir corrección" (no "Devolver al estudiante"); el modal lista los ejercicios, "Confirmar" deshabilitado con cero tildados, y con 2 y 4 tildados hace `POST .../return` con body `{"ordenes":[2,4]}`. Verificación: rojo.
- [x] 6.2 GREEN: `devolverEntrega(entregaId, ordenes?, getToken?)` en `lib/api.ts` (sin `ordenes` → sin body, compat); modal con `Modal` de `@platform/ui`; en `returned`, mostrar qué ejercicios se pidieron (o "todos"). Verificación: verde.
- [x] 6.3 Textos: `tour/vistas.tsx:329-335`, `utils/helpContent.tsx:654-662`, `onboarding/docenteOnboarding.tsx:131-133` (sin tildes, regla del help system): "Publicar nota" = el alumno la ve al guardar; "Pedir corrección" = opcional, elegís ejercicios. Test: si existe un test que ancle el texto viejo, actualizarlo; agregar uno que afirme que ya no aparece "liberarlas". Verificación: verde.

## 7. Chequeos finales

- [x] 7.1 Tesis: `git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service` → **vacío**. Grep del diff: ningún `emit`/`ctr` nuevo. Verificación: salida pegada en `STATUS.md`.
- [x] 7.2 Suites completas contra la línea base de 1.1 (Python del servicio, vitest de los dos frontends, `tsc`, `biome`). Verificación: sin rojos nuevos; números en `STATUS.md`.
- [x] 7.3 Correr la "Prueba local reproducible" de `design.md` (pasos 1–10) y anotar el resultado por paso en `STATUS.md`.
- [x] 7.4 Redactar el aviso a Cortez (2–3 líneas en `STATUS.md`): devolución parcial = menos segundos intentos; corte temporal = fecha de deploy.
- [x] 7.5 Deuda preexistente que bloquea el archive (no el apply): `openspec/specs/correccion-grading/spec.md` y `openspec/specs/student-exercise-flow/spec.md` arrancan con `## ADDED Requirements` en vez de `## Purpose` + `## Requirements`, y `openspec validate` avisa que el archive rechazaría el delta. Corregir sólo esos encabezados (mecánico, sin tocar requisitos) antes de `/opsx:archive`. Verificación: `openspec validate publicar-nota-y-pedir-correccion --strict` sin los avisos "Archive would refuse".
