Gobernanza MEDIO-ALTO (tabla nueva con texto libre de alumnos + RLS), TDD estricto: cada grupo es RED (test que falla por la razón correcta) → GREEN (mínimo código) → TRIANGULAR → REFACTOR. Cada test negativo (403/404/409/422/429/"no emite") se prueba rojo quitando su guard y se anota en `STATUS.md`.

- Python, desde la raíz del repo: `uv run pytest apps/evaluation-service -q` y `uv run pytest apps/api-gateway -q` (scope del servicio; no usar `make test-fast`). Rojos ambientales conocidos: memoria "Los rojos de Python son ambientales".
- Integración con Postgres real: `EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main uv run pytest apps/evaluation-service/tests/integration -q`.
- Frontend: `cd apps/web-student && pnpm test` y `cd apps/web-teacher && pnpm test` (bajo Node 26 los rojos de `localStorage` locales son falsos: anotarlos, no arreglarlos).

## 1. Línea base

- [x] 1.1 Crear `STATUS.md` del change. Correr `uv run pytest apps/evaluation-service -q`, `uv run pytest apps/api-gateway -q`, `pnpm test` en web-student y web-teacher, `pnpm exec tsc --noEmit` y `pnpm exec biome check src` en los dos frontends; anotar números y rojos preexistentes. Confirmar el head de Alembic de evaluation (`uv run alembic -c apps/evaluation-service/alembic.ini heads`). Verificación: números y head en `STATUS.md`.

## 2. Backend — modelo, schema y migración

- [x] 2.1 RED: `apps/evaluation-service/tests/unit/test_pedido_ayuda_schemas.py`: `PedidoAyudaCreate` acepta el caso mínimo (TP + categoría) y el completo; rechaza categoría fuera de las 4, `mensaje` > 1000, `ejercicio_orden` < 1 y claves de `contexto` no permitidas (`extra="forbid"`, `error_visible` > 300). Verificación: rojo por import inexistente.
- [x] 2.2 GREEN: `schemas/pedido_ayuda.py` (`PedidoAyudaCreate`, `PedidoAyudaContexto`, `PedidoAyudaOut`, `PedidoAyudaListResponse` con `meta.pendientes`) y `models/pedidos_ayuda.py` (`PedidoAyuda(Base, TenantMixin)`, columnas e índices de design D2), registrado en `models/__init__.py`. Verificación: verde.
- [x] 2.3 Migración `apps/evaluation-service/alembic/versions/20261028_0001_pedidos_ayuda.py` (idempotente como `20260818_0003`: tabla, CHECKs de `categoria`/`estado`/largo de `mensaje`/coherencia `resuelto_at`, FK a `entregas` `ON DELETE SET NULL`, índices, `ENABLE`+`FORCE` RLS + policy `pedidos_ayuda_tenant_isolation`; downgrade simétrico). Verificación: `upgrade head` → `downgrade -1` → `upgrade head` limpio contra la base local, y `make check-rls` OK para `pedidos_ayuda`; salida anotada en `STATUS.md`.
- [x] 2.4 RED→GREEN: `tests/integration/test_pedidos_ayuda_rls_db.py` (patrón `test_reconciliador_rls_db.py`, skip sin `EVAL_TEST_DB_URL`): con usuario NOBYPASSRLS, tenant B no ve filas del tenant A, sin tenant no ve ninguna, e INSERT con `tenant_id` ajeno falla. Probar rojo con una migración sin `FORCE`. Verificación: verde con la DB local.

## 3. Backend — POST (alumno)

- [x] 3.1 RED: `tests/unit/test_pedidos_ayuda_crear.py` (DB fake / monkeypatch como `test_devolucion_reabre_ejercicios.py`): alumno inscripto crea → 201, `estado=pendiente`, `comision_id` = la de la TP aunque el body no la traiga, `created_at` del servidor. Verificación: rojo (404 de ruta inexistente).
- [x] 3.2 GREEN: `routes/pedidos_ayuda.py` con `POST`, gates `require_estudiante` en `auth/dependencies.py`, router incluido en `main.py`. Verificación: verde.
- [x] 3.3 TRIANGULAR: sin `episode_id` → 201; `episode_id` inexistente en el CTR → 201 y se guarda igual; con `entrega_id` propio → 201. Verificación: verde.
- [x] 3.4 RED→GREEN negativos, cada uno probado rojo sin su guard: TP inexistente → 422; alumno no inscripto → 403; `entrega_id` ajeno o de otra TP → 422; `ejercicio_orden` fuera de los ejercicios de la TP → 422; usuario docente → 403. Verificación: verde + notas en `STATUS.md`.
- [x] 3.5 RED→GREEN anti-spam (D4): segundo pedido a los 10 s → 429 con texto de espera; 4.º pendiente en la misma TP → 409; con uno resuelto y pasado el minuto → 201. Verificación: verde.
- [x] 3.6 RED→GREEN tesis: crear un pedido no llama a ningún cliente del CTR/tutor (assert sobre un spy/monkeypatch de httpx o del publisher; el módulo no importa nada de `ctr`/`tutor`), y el log `pedido_ayuda_creado` (capturado con `structlog.testing.capture_logs`) lleva `categoria` y ids pero **no** `mensaje`. Verificación: verde; probar rojo agregando `mensaje` al log.

## 4. Backend — lecturas y resolver

- [x] 4.1 RED→GREEN: `GET /mios?tarea_practica_id=` devuelve sólo los del alumno, del más nuevo al más viejo; con pedidos de otro alumno en la misma TP no aparecen. Verificación: verde; probar rojo quitando el `WHERE student_pseudonym`.
- [x] 4.2 RED→GREEN: `GET ?comision_id=&estado=` para docente asignado → lista filtrada + `meta.pendientes`; docente de otra comisión → 404; `docente_admin` → 200; alumno → 403. Helper `_assert_docente_de_comision` (misma consulta y 404 que `_assert_comision_visible`). Verificación: verde; cada rechazo probado rojo sin su guard.
- [x] 4.3 RED→GREEN: `PATCH /{id}/resolver`: docente de la comisión → `resuelto`, `resuelto_por`, `resuelto_at`; segunda llamada → 200 sin cambiar quién/cuándo; docente ajeno → 404 sin cambios; log `pedido_ayuda_resuelto`. Verificación: verde.
- [x] 4.4 api-gateway: agregar `"/api/v1/pedidos-ayuda": settings.evaluation_service_url` al `ROUTE_MAP` (`apps/api-gateway/src/api_gateway/routes/proxy.py`) con test que afirme que el prefijo rutea a evaluation (seguir el test existente del ROUTE_MAP si lo hay). Verificación: `uv run pytest apps/api-gateway -q` verde.

## 5. web-student

- [x] 5.1 RED: `apps/web-student/tests/PedirAyudaModal.test.tsx`: "Enviar" deshabilitado sin categoría; con categoría + mensaje hace `POST /api/v1/pedidos-ayuda` con `tarea_practica_id`, `ejercicio_orden`, `episode_id`, `categoria`, `mensaje`, `contexto.pantalla`; éxito → "Tu pedido le llegó a tu docente"; 429/409 → muestra el motivo y no da por enviado; muestra el texto "no al tutor". Verificación: rojo por import.
- [x] 5.2 GREEN: `components/PedirAyudaModal.tsx` (`Modal` de `@platform/ui`, `size="sm"`), `crearPedidoAyuda` y `listarMisPedidosAyuda` en `lib/api.ts`, lista "Tus pedidos en este trabajo" con estado. Verificación: verde.
- [x] 5.3 RED→GREEN: en `EpisodePage` el botón aparece en el header y en la pantalla de error "El ejercicio no terminó de abrirse" (con el `episodeId` de la URL y el contexto de `sessionStorage`); sin contexto de TP en la pantalla de error, no aparece. Abrir el modal no llama a pausa/cierre/abandono del episodio. Verificación: test nuevo `tests/PedirAyudaEnEpisodio.test.tsx` verde; probar rojo el "no llama a abandono".
- [x] 5.4 RED→GREEN: en `ExerciseListView` el botón aparece en el header de la TP y el modal ofrece el selector opcional de ejercicio. Los tests existentes de `ExerciseListView*.test.tsx` siguen verdes. Verificación: verde.
- [x] 5.5 Textos: párrafo en `utils/helpContent.tsx` (`episode`) y paso en `onboarding/alumnoOnboarding.tsx` (D10). Verificación: si hay test que cuente los pasos del onboarding, actualizarlo; `pnpm test` verde.

## 6. web-teacher

- [x] 6.1 RED: `apps/web-teacher/tests/PedidosAyudaView.test.tsx` (con `setupFetchMock`): lista pendientes con alumno, TP, ejercicio, categoría, mensaje y link "Ver episodio" a `/episode-timeline?episodeId=` sólo cuando hay `episode_id`; "Marcar resuelto" hace `PATCH .../resolver` y mueve la fila a Resueltos. Verificación: rojo por import.
- [x] 6.2 GREEN: `views/PedidosAyudaView.tsx` (`PageContainer` + `helpContent.pedidosAyuda`), `routes/pedidos-ayuda.tsx` (`?comisionId=`, redirect a `/` sin él), `listarPedidosAyuda` y `resolverPedidoAyuda` en `lib/api.ts`. Verificación: verde.
- [x] 6.3 Ítem "Pedidos de ayuda" en `NAV_GROUPS` (`routes/__root.tsx`, debajo de "Correcciones"). Verificación: `navegacionAlcanzable.test.ts` verde (y rojo antes de agregarlo, si el test detecta rutas fuera del menú).
- [x] 6.4 RED→GREEN: `ComisionDelDocenteCard` muestra "N pedidos de ayuda" con link cuando N > 0 y nada cuando es 0 (dato de `meta.pendientes`, cargado en `HomeView` con `useCallback` por la regla de fetchFn del repo). Verificación: test verde.
- [x] 6.5 Texto `pedidosAyuda` en `utils/helpContent.tsx` sin tildes (skill `help-system-content`). Verificación: `pnpm test` verde.

## 7. Integración

- [ ] 7.1 Prueba local reproducible de design.md (pasos 1-7) corrida de punta a punta; resultado por paso en `STATUS.md`. Verificación: todos los pasos OK o el desvío anotado.
- [x] 7.2 Suites completas otra vez (las de 1.1) + `tsc --noEmit` + `biome check src` en los dos frontends. Verificación: sin rojos nuevos respecto de la línea base.

## 8. Tesis

- [x] 8.1 Correr `git diff origin/main --stat -- apps/ctr-service apps/classifier-service apps/tutor-service apps/governance-service packages/contracts ai-native-prompts packages/platform-ops/src/platform_ops/academic_export.py`. Verificación: salida **vacía**, pegada en `STATUS.md`.
- [x] 8.2 Dejar en `STATUS.md` el texto de la nota para Cortez (design, "Tesis: qué NO se toca") listo para que Neyén se lo mande. Verificación: el texto está.
