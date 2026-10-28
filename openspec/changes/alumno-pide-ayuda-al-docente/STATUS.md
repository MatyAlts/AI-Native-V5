# STATUS — alumno-pide-ayuda-al-docente

Implementado en el worktree `C:/Users/LENOVO/wt-ayuda` (rama `feat/alumno-pide-ayuda-al-docente`, base `origin/main` `18bffe9`).
Tareas: 28/29. Pendiente: **7.1** (prueba local con el stack completo; receta en `prueba-local.md`).

## 1. Línea base (antes de tocar código)

| Suite | Resultado |
|---|---|
| `uv run pytest apps/evaluation-service -q` (sin `EVAL_TEST_DB_URL`) | 296 passed, 163 skipped |
| `uv run pytest apps/api-gateway -q` | 44 passed |
| web-student `pnpm test` | 675 passed (63 archivos) |
| web-teacher `pnpm test` | 477 passed (33 archivos) |
| `tsc --noEmit` (los dos) | limpio |
| `biome check src` (los dos) | 1 error: `src/index.css` format = falso positivo CRLF conocido |

Head de Alembic de evaluation antes del cambio: `20260902_0001` (reconfirmado contra `origin/main`).
Nota de entorno: `uv sync` pelado no instala los servicios; hace falta `uv sync --all-packages`.
Nota de entorno 2: el worktree está en `C:/Users/LENOVO/wt-ayuda` y no bajo el scratchpad porque `git worktree add` falla ahí por path demasiado largo (archivos de `openspec/changes/archive/...`).

## 2. Migración

`apps/evaluation-service/alembic/versions/20261028_0001_pedidos_ayuda.py`, `down_revision = "20260902_0001"`, head nuevo `20261028_0001`.

Verificada contra una base DESCARTABLE `wt_ayuda_test` (esquema copiado de `academic_main` con `pg_dump -s`, versión sembrada en `20260902_0001`; `academic_main` no se tocó; la base se borró al terminar):

```
upgrade head   : 20260902_0001 -> 20261028_0001
downgrade -1   : 20261028_0001 -> 20260902_0001
upgrade head   : 20260902_0001 -> 20261028_0001   (ciclo repetido dos veces, limpio)
```

`scripts/check-rls.py` contra la base descartable (más `ctr_store`, `classifier_db`, `content_db` en solo lectura):
`[OK] Todas las tablas con tenant_id tienen policy + RLS habilitado + FORCE`.
(`make check-rls` sobre `academic_main` queda para cuando Neyén migre local, paso 0.3 de `prueba-local.md`.)

## 3. TDD — evidencia por grupo

| Tarea | Archivo de test | Capa | RED | GREEN | Triangulación |
|---|---|---|---|---|---|
| 2.1/2.2 | `tests/unit/test_pedido_ayuda_schemas.py` | Unit | import inexistente | 16 pass | 4 categorías, bordes 1000/1001, 300/301, extra=forbid |
| 2.4 | `tests/integration/test_pedidos_ayuda_rls_db.py` | Integración (Postgres, rol NOBYPASSRLS) | con `DISABLE ROW LEVEL SECURITY`: 4 rojos | 6 pass | dueño ve 1, otro tenant 0, sin tenant 0, INSERT ajeno falla, ENABLE+FORCE |
| 3.x/4.2/4.3 | `tests/unit/test_pedidos_ayuda_rutas.py` | Unit (sesión falsa) | import inexistente | 34 pass | comisión otra TP, con/sin episodio, entrega, ejercicio, 60 s justo, 2 vs 3 pendientes |
| 3.5/4.1/4.2/4.3 (consultas) | `tests/integration/test_pedidos_ayuda_db.py` | Integración (Postgres) | — | 15 pass | tope por TP, por alumno, `/mios`, lista por comisión, membresía borrada |
| 4.4 | `apps/api-gateway/tests/unit/test_route_map_pedidos_ayuda.py` | Unit | 3 rojos (sin ROUTE_MAP) | 4 pass | 3 paths |
| 5.1/5.2 | `web-student/tests/PedirAyudaModal.test.tsx` | Vitest | import inexistente | 13 pass | 429, 409, 403 genérico, doble clic, selector de ejercicio |
| 5.3 | `web-student/tests/PedirAyudaEnEpisodio.test.tsx` | Vitest | 3 rojos | 5 pass | header, pantalla de error, sin contexto, 500 |
| 5.4 | `web-student/tests/PedirAyudaEnLista.test.tsx` | Vitest | 2 rojos | 2 pass | |
| 5.5 | `web-student/tests/alumnoOnboarding.test.tsx` (actualizado: nuevo hint `episodio-pedir-ayuda`) | Vitest | — | pass | |
| 6.1/6.2 | `web-teacher/tests/PedidosAyudaView.test.tsx` | Vitest | import inexistente | 5 pass | |
| 6.3 | `web-teacher/tests/navegacionAlcanzable.test.ts` (existente) | Vitest | ROJO con la ruta sin ítem en el menú | verde con el ítem | |
| 6.4 | `web-teacher/tests/PedidosAyudaEnTarjeta.test.tsx` | Vitest | 4 rojos | 5 pass | N=2, N=1, 0/null/undefined |

### Cada test negativo, probado ROJO quitando su guard (mutación y restaurado)

| Guard quitado | Tests que se ponen rojos |
|---|---|
| TP inexistente (422) | 1 |
| inscripción vigente (403) | 2 (unit) |
| entrega ajena (422) | 1 |
| ejercicio fuera de la TP (422) | 1 |
| 429 (espera 60 s) | 1 |
| 409 (3 pendientes) | 1 |
| `mensaje` agregado al log `pedido_ayuda_creado` | 1 |
| guard docente ajeno (404) | 2 |
| idempotencia de resolver | 1 |
| comisión tomada del body en vez de la TP | 5 |
| `WHERE student_pseudonym` de `/mios` | 1 (integración) |
| filtro por comisión del listado | 1 (integración) |
| `deleted_at` en inscripción / en `usuarios_comision` | 1 / 1 (integración) |
| anti-spam: cuenta todo en vez de pendientes / todas las TP / todos los alumnos | 1 / 1 / 10 |
| `require_estudiante` abierto / `require_docente` abierto | 2 / 2 |
| RLS desactivada en la tabla | 4 (integración) |
| botón del modal que dispara `/episodes/x/abandoned` | 1 (vitest) |

## 4. Suites finales

| Suite | Baseline → final |
|---|---|
| evaluation-service (sin DB) | 296 passed / 163 skipped → **346 passed / 184 skipped** |
| evaluation-service (con base descartable) | 370 passed / 158 skipped / 2 failed: los 2 rojos son `test_activeia_payload_db.py` ("la base no tiene casos ocultos / test cases tipados"): la base descartable es solo esquema, sin seed. No son regresión |
| api-gateway | 44 → **48 passed** |
| web-student | 675 → **697 passed** |
| web-teacher | 477 → **487 passed** |
| `tsc --noEmit` ×2 | limpio |
| `biome check src` ×2 | solo `src/index.css` (CRLF, falso positivo) |
| `ruff check` + `ruff format --check` (evaluation + gateway) | OK |
| `scripts/check-claude-md.py` | OK, sin drift |

`routeTree.gen.ts` de web-teacher se regeneró con `vite build` (solo agrega la ruta `/pedidos-ayuda`). Ícono `LifeBuoy` verificado en lucide-react 0.460.

## 5. Tesis (tarea 8.1)

```
$ git diff origin/main --stat -- apps/ctr-service apps/classifier-service apps/tutor-service apps/governance-service packages/contracts ai-native-prompts packages/platform-ops/src/platform_ops/academic_export.py
(salida vacía)
```

Además: el módulo `routes/pedidos_ayuda.py` no importa nada de CTR/tutor/classifier/httpx, un test lo verifica, y otro prueba que crear un pedido no hace requests HTTP salientes. Un test prueba que abrir el modal y enviar sólo llama a `/api/v1/pedidos-ayuda...` (ni pausa, ni cierre, ni abandono, ni `/events`).

## 6. Decisiones de implementación (desvíos menores de design.md)

- Las constantes de CHECK se nombran sin el prefijo `ck_` porque la naming convention del `MetaData` lo agrega (sino quedaba `ck_pedidos_ayuda_ck_...`).
- `EjercicioContext` (web-student) suma `tareaId?` opcional; la ruta `episodio.$id` lo toma de `sessionStorage` (`tarea_id`). Es lo que permite pedir ayuda desde la pantalla de error, donde la TP aún no cargó.
- El hint de onboarding nuevo (`episodio-pedir-ayuda`) no bumpea el id del flow: es un cartel nuevo, los descartes viejos no se ven afectados. Se actualizaron 5 asserts de `alumnoOnboarding.test.tsx` que enumeran los carteles.
- El contador de la tarjeta usa `useQueries` (react-query) en `HomeView`, como las demás métricas, y queda FUERA de `metricsPending`.
- La inscripción vigente se mide con `deleted_at IS NULL` (no filtra por `estado` de la inscripción).

## 7. Nota para Cortez (tarea 8.2) — lista para mandar

> Cortez: vamos a sumar un botón "Pedir ayuda a tu docente" en la plataforma. Es ayuda HUMANA fuera de banda: el pedido va al docente de la comisión y NO pasa por el tutor ni por el CTR (no emite ningún evento, no toca el episodio, no cambia el clasificador ni los prompts). Un episodio puede verse "autónomo" cuando el alumno en realidad destrabó hablando con el docente; eso ya pasaba hoy (foro de Moodle, consulta en clase) y no es nuevo. Lo nuevo es que el canal queda registrado con `episode_id` y hora en la tabla `pedidos_ayuda` (base `academic_main`), así que si lo necesitás se puede listar qué episodios tuvieron un pedido de ayuda para excluirlos o controlarlos en el análisis. Avisame si querés ese cruce antes del deploy.

## 8. Sin verificar

- (resuelto) Prueba local con navegador 7.1: corrida el 2026-10-28, ver sección 9.
- (resuelto) `make check-rls` sobre `academic_main` local real: OK tras aplicar la migración 20261028_0001.
- CI del PR (ver `gh pr checks` en el PR).

## 9. Prueba local 7.1 (2026-10-28, Playwright + chromium, stack local, tenant aaaa)
Migración `20261028_0001` aplicada a `academic_main` LOCAL (desde `apps/evaluation-service`, no desde la raíz: el `script_location` del alembic.ini es relativo). `make check-rls` OK.
- Paso 1 pedido desde episodio: botón en el header, modal, 'No puedo avanzar' + 'no entiendo el while' -> 'Tu pedido le llegó a tu docente' y al reabrir figura Pendiente. Episodio sigue `estado: open` (GET /episodes). OK
- Paso 2 anti-spam: segundo pedido enseguida -> 'Esperá 33 segundos antes de mandar otro pedido.', no se crea. OK
- Paso 3 sin episodio desde la lista de ejercicios ('Error de la plataforma', sin ejercicio) pasado el minuto: enviado. OK
- Paso 4 pantalla de error: reproducida forzando 404 del GET /episodes/{id} con `page.route`; 'El ejercicio no terminó de abrirse' con Reintentar / Pedir ayuda / Volver; el pedido sale con `episode_id` del intento y ejercicio 1. OK
- Paso 5 docente: tarjeta de la comisión con '3 pedidos de ayuda'; vista 'Pedidos de ayuda' con alumno, TP, ejercicio, categoría, mensaje, 'El alumno veía: ...'; 'Ver episodio' sólo en los que tienen episodio y abre la timeline (Estado: open, Eventos: 1). OK
- Paso 6 resolver: 'Marcar resuelto' -> pasa a Resueltos, contador baja a 2; en web-student el pedido figura Resuelto. OK
- Paso 7 privacidad (404 a docente ajeno): NO corrido en navegador.
- Paso 8 tesis: diff vacío en ctr/classifier/tutor/governance/contracts/prompts/academic_export. CTR en ctr_store antes/después de toda la sesión: único cambio `episodio_abierto` 28 -> 30 (los dos episodios que abrí a mano); cero eventos por los pedidos ni por abrir el modal; en el episodio del paso 1 sólo `episodio_abierto@0` antes y después de pedir ayuda.
- Observación (no bloqueante): si el episodio se abre por URL directa/recarga (sin el contexto de ejercicio de la navegación), el pedido desde el header sale con `ejercicio_orden` vacío aunque el episodio es del ejercicio 1 (visto en la prueba, que recargó la URL). Desde el flujo normal (Empezar) el contexto existe.
- Capturas: `capturas-prs-128-130/130-*.png`.
