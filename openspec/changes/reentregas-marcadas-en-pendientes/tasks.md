Gobernanza MEDIO, TDD estricto: cada grupo es RED (test que falla por la razón correcta) → GREEN (mínimo código) → TRIANGULAR → REFACTOR. Cada test negativo (`false`, "sin badge", "no recibe") se prueba rojo forzando la condición y se anota en `STATUS.md`. Checkpoint con Neyén al cerrar el grupo 3 (backend) antes de la UI.

- Python, desde la raíz del repo: `uv run pytest apps/evaluation-service -q` (scope del servicio; no usar `make test-fast`). Rojos ambientales conocidos: memoria "Los rojos de Python son ambientales".
- Frontend: `cd apps/web-teacher && pnpm test`, `pnpm exec tsc --noEmit`, `pnpm exec biome check src` (bajo Node 26 los rojos de `localStorage` locales son falsos).

## 1. Línea base

- [x] 1.1 Crear `STATUS.md`. Anotar si `publicar-nota-y-pedir-correccion` ya está aplicado/mergeado y qué se decidió de design D5 (A o B). Correr la suite de evaluation-service y la de web-teacher (+ `tsc`, `biome`); anotar números y rojos preexistentes. Verificación: números en `STATUS.md`.

## 2. Backend — `es_reentrega` en la respuesta

- [x] 2.1 RED: en `apps/evaluation-service/tests/unit/test_entrega_tp_metadata.py` (o `test_reentrega.py` nuevo), tests de `_entrega_out_con_tp`: `submitted` con nota en `notas_meta` → `es_reentrega=True`; `submitted` sin nota → `False`; `graded` con nota → `False`; `returned` con nota → `False`. Verificación: rojo por campo inexistente.
- [x] 2.2 GREEN: `es_reentrega: bool = False` en `EntregaOut` (`schemas/entrega.py`) y su cálculo en `_entrega_out_con_tp` (`routes/entregas.py`), sin consultas nuevas. Verificación: verde; los tests existentes de `nota_final`/`graded_at` siguen verdes.
- [x] 2.3 TRIANGULAR: `get_entrega` (lectura individual) también lo devuelve bien para una re-entrega. Verificación: verde.

## 3. Backend — filtro `reentrega` en el listado

- [x] 3.1 RED: test de `list_entregas` con `reentrega=True` sobre 3 entregas nuevas + 2 re-entregas → devuelve las 2; `reentrega=False` → las 3 nuevas (más las no-`submitted` que correspondan); sin parámetro → igual que hoy. Preferir `tests/integration/` con DB si la suite de integración corre en local (patrón de `test_tp_notas_metadata_db.py`); si no, unit con la condición SQL compilada. Verificación: rojo.
- [x] 3.2 GREEN: parámetro `reentrega: bool | None = None` en `list_entregas`, condición `estado == "submitted"` + `EXISTS` sobre `calificaciones` con `deleted_at IS NULL` (design D2), agregada sin tocar el aislamiento por comisión. Verificación: verde.
- [x] 3.3 TRIANGULAR: calificación con `deleted_at` seteado no cuenta; docente sin asignación a la comisión con `reentrega=true` no recibe nada (extender el patrón de `tests/test_scope_comision_calificacion.py`); `estado=graded&reentrega=true` → vacío. Probar rojo cada caso quitando su condición. Verificación: verde + notas en `STATUS.md`.
- [x] 3.4 Ciclo completo: entregar → calificar → devolver → re-entregar → aparece con `es_reentrega=True` → `PATCH /calificacion` → `es_reentrega=False`. Verificación: verde. Checkpoint: resumen del backend a Neyén antes de seguir.

## 4. web-teacher

- [x] 4.1 RED: en `apps/web-teacher/tests/CorreccionesView.test.tsx`, con `setupFetchMock` (`tests/_mocks.ts`): una entrega `submitted` con `es_reentrega:true, nota_final:6` muestra "Re-entrega · antes 6" en su tarjeta; una nueva no lo muestra. Verificación: rojo.
- [x] 4.2 GREEN: `EntregaDocente` suma `es_reentrega?: boolean` y `nota_final?: number | null` (`lib/api.ts`); badge junto al de estado (design D4). Verificación: verde.
- [x] 4.3 RED→GREEN: toggle "Sólo re-entregas": al activarlo, `listEntregas` se llama con `reentrega=true` (afirmar la URL del fetch) y la cola de "corregir pendientes" sólo contiene esas. `listEntregas` acepta `reentrega?: boolean`. Probar rojo el "no la llama sin el toggle". Verificación: verde.
- [x] 4.4 RED→GREEN: detalle de ejercicios pedidos (design D5, lectura tolerante): `ejercicio_estados` con `reabierto_por_docente` en 2 y 4 → "Corrección pedida: ej. 2 y 4"; en todos → "todos"; sin marca → sólo "Re-entrega". Función pura en `apps/web-teacher/src/utils/` con su test. Verificación: verde.
- [x] 4.5 Ayuda: una línea en `helpContent.correcciones` (`apps/web-teacher/src/utils/helpContent.tsx`, sin tildes) que explica el badge y el toggle. Verificación: `pnpm test` verde.

## 5. Chequeos finales

- [x] 5.1 Tesis: `git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/evaluation-service/alembic` → **vacío**. Verificación: salida pegada en `STATUS.md`.
- [x] 5.2 Suites completas (evaluation-service, web-teacher, `tsc`, `biome`) contra la línea base de 1.1. Verificación: sin rojos nuevos; números en `STATUS.md`.
- [x] 5.3 Correr la "Prueba local reproducible" de `design.md` (pasos 1–10; el 9 sólo si D5-A quedó aplicado) y anotar el resultado por paso en `STATUS.md`.
- [x] 5.4 Deuda preexistente que bloquea el archive (no el apply): `openspec/specs/correccion-grading/spec.md` arranca con `## ADDED Requirements` en vez de `## Purpose` + `## Requirements`. Si `publicar-nota-y-pedir-correccion` (su tarea 7.5) no lo corrigió todavía, corregir sólo esos encabezados antes de `/opsx:archive`. Verificación: `openspec validate reentregas-marcadas-en-pendientes --strict` sin "Archive would refuse".
