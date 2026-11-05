# apply-2-constructor-F: corrección de verify-1-breaker (F1 a F7)

- Rol: constructor. Ejecutor: subagente nativo Claude Code (familia Anthropic, la misma que planner, plan-reviewer, constructores A a E y breaker). Gate verify, intento 2. Nivel CRITICAL.
- Fecha: 04/11/2026, 14:06 a 14:23 (-03:00).
- Revisión de partida: árbol sobre HEAD `b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits, huella `arbol=159b44f425465551` (la que atacó el breaker).
- Revisión entregada (14:21:08, `scratchpad/hash-arbol.sh`, excluye `openspec/changes/cibse-codificacion-ciega/`): `HEAD=b32e621 diff_HEAD_sha256=ad796f2631fd9e3eed469fb3de876f37fdddcca871210aae21956ca49b6d795a untracked_n=59 untracked_list_sha256=4b1db26112d7e4aacfe16ec245fa9f8d5bf5ab3708ae52d86a7b18fdb259d9c5 arbol=291628b1211abf5a`. Sin commits (instrucción del orquestador).
- Lecciones L-NNN: no existen en el repo (declarado por el orquestador; no repetí la búsqueda). Ruta leída: ninguna.
- Alcance: solo F1 a F7 de `informes/verify-1-breaker.md`. Las suposiciones S1 a S5 del breaker no se tocaron.

## Archivos tocados

Producción:
- `apps/classifier-service/src/classifier_service/services/estudio_esquema.py`: `_es_clave_de` (F2/F3); `errores_respuesta_esperada` (F1).
- `apps/classifier-service/src/classifier_service/routes/estudio.py`: `PUT .../codebook/{etiqueta}` devuelve `VersionEditadaOut` con `anclas_invalidas`; `congelar` rechaza 422 `anclas_invalidas`; `_anclas_de`, `_anclas_invalidas` (F1).
- `apps/classifier-service/src/classifier_service/routes/estudio_trabajo.py`: cerrar sin muestra -> 409 `sin_muestra` (F4).
- `apps/classifier-service/src/classifier_service/services/ctr_lectura.py`: `r.json()` protegido y `tiene_forma_de_episodio` (F6).
- `apps/classifier-service/alembic/versions/20261104_0007_estudio_codificacion.py`: función `estudio_sin_truncate()` y seis triggers `BEFORE TRUNCATE ... FOR EACH STATEMENT`, con su downgrade (F5).
- `apps/web-teacher/src/lib/estudioApi.ts` (tipos `AnclaInvalida`, `VersionEditada`), `src/views/estudio/AdministracionEstudioView.tsx` (aviso del PUT), `CodificacionEstudioView.tsx` (estado vacío sin muestra; lista vacía de faltantes no es "Faltan 0"), `mensajesError.ts` (`sin_muestra`, `anclas_invalidas`).

Tests: `tests/unit/test_estudio_esquema.py`, `tests/unit/test_ctr_lectura.py`, `tests/integration/test_estudio_{anclas,codebook,etiquetas,inmutabilidad,traza}_db.py`; web-teacher `tests/{CodificacionEstudioView,AdministracionEstudioView}.test.tsx`, `tests/mensajesError.test.ts`.

Documentación: `docs/servicios/classifier-service.md` (§12.2 «Forma exacta del meta-esquema», canónica; aviso del PUT; §12.6 422 al congelar); `docs/adr/063-estudio-codificacion-ciega.md` (D9 apunta a la sección canónica). `tasks.md`: grupo 14 nuevo y la ruta del codebook v0 en "Registro del planner" (`~/Descargas` -> `~/Documentos/MTAC/...`). "Estado de orquestación" sin tocar.

## EVIDENCIA

Entorno: `cibse-test-pg` (`127.0.0.1:55432`), `CLASSIFIER_TEST_DB_URL=postgresql+asyncpg://classifier_user:***@127.0.0.1:55432/classifier_db`. No toqué `seguridad_jwt_db` (5432). Mutantes con `scratchpad/constructorF/mutar.sh` (copia de respaldo, diff, corrida, restauración y `cmp`); diffs y salidas en `scratchpad/constructorF/mutantes/`. El detalle por tarea, con todas las salidas, está en `tasks.md` §14.

| Hora | Paso | Comando (resumido) | Resultado |
|---|---|---|---|
| 14:06:33 | Base | pytest estudio + ctr_lectura | `306 passed, 1 skipped` (ciclo de migración sin su variable) |
| 14:07:01 | Base | vitest 3 archivos del estudio | `47 passed` |
| 14:09:02 | F1 RED | `test_estudio_anclas_db.py -k ...` | `6 failed` por aserción (`assert [] == [(…, 'practica', 1)]` x4, `(200, None) == (200, [])`, `200 == 422`). El intento de 14:08:51 cayó por `KeyError` y no se contó |
| 14:09:29 | F1 GREEN | anclas + codebook | `49 passed` (incluye el sha literal) |
| 14:10:12-24 | F1 mutantes | 4 | todos muertos |
| 14:10:41 | F2/F3 RED | etiquetas + codebook `-k` | `11 failed` (`assert 500 == 400`), 6 controles verdes |
| 14:11:00 | F2/F3 GREEN | etiquetas + codebook + esquema | `142 passed` |
| 14:11:22-30 | F2/F3 mutantes | 2 | muertos (`500 == 400`) |
| 14:11:38 | F4 RED back | `-k sin_muestra` | `(422, {…'faltantes': []}) == (409, 'sin_muestra')` |
| 14:12:36 | F4 GREEN back | etiquetas | `24 passed`; mutante 14:12:42 muerto (sin el guard el cierre pasaba con 200) |
| 14:13:26 | F4/F1 RED front | vitest 3 archivos | `7 failed, 48 passed`, por aserción |
| 14:14:03 | GREEN front | idem | `55 passed`; 5 mutantes 14:14:16-32 muertos |
| 14:15:12 | F6 RED | ctr_lectura + traza | `18 failed` (`JSONDecodeError is CTRNoDisponibleError`, `None is …`, `500 == 502`) |
| 14:15:28 | F6 GREEN | idem | `45 passed`; 3 mutantes 14:15:40-48 muertos |
| 14:16:19 | F5 RED | inmutabilidad `-k truncate` | `8 failed`, `DID NOT RAISE DBAPIError` |
| 14:16:36 | F5 | re-migración de `cibse-test-pg` (`downgrade -1`, `upgrade head`) | head; 6 triggers en `pg_trigger` |
| 14:16:43 | F5 GREEN | inmutabilidad | `34 passed`; 3 mutantes de migración muertos (14:16:56, 14:16:58, 14:17:19) |
| 14:18:22 | F7 contrato | `validar_doc_meta.py` | 33 afirmaciones, `FALLAS: 0`; sensibilidad 14:18:37 `[FAIL] ejemplo documentado valido` con el ejemplo roto |
| 14:18:48 | Revisión | `ruff check` / `ruff format --check` / `mypy` classifier | limpio / `93 files already formatted` / `Success … 39 source files` |
| 14:19:02 | Revisión | `pnpm turbo lint typecheck --filter @platform/web-teacher` | `2 successful` |
| 14:19:25 | Revisión | `uv run pytest apps/classifier-service -q -rs` (+ ciclo de migración) | `4 failed, 681 passed`, sin skips |
| 14:20:13 | Revisión | `cd apps/web-teacher && pnpm test` | `51 files`, `685 passed` |
| 14:20:25 | Revisión | `python3 scripts/check-claude-md.py` | `[OK] 3 claims verificados, 2 skip, sin drift` |
| 14:20:57-59 | Revisión | migración en base limpia `cibse-clean-pg` (`:55447`) | upgrade head (9 tablas, 6 triggers TRUNCATE, 6 funciones) -> downgrade `20260906_0006` (0/0/0) -> upgrade head (9/6/6); `TRUNCATE` rechazado; contenedor borrado |
| 14:21:08 | Huella | `hash-arbol.sh` | `arbol=291628b1211abf5a` |
| 14:22:27 | F6 real | ctr-service temporal `:18087` sobre `cibse-smoke-pg` | episodio cerrado real: `forma OK: True`, `motivo_rechazo: None`, `seq_tope: 4`; proceso detenido |

Conteo independiente de tests nuevos (classifier 617 -> 681, +64): F1 13 (6 HTTP, 7 unitarias), F2/F3 23 (13 HTTP, 10 unitarias), F4 1, F5 8, F6 19 (17 unitarias, 2 HTTP). Web-teacher 677 -> 685 (+8: 3 en Codificación, 3 en Administración, 2 en mensajes). Los 4 fallos de la suite son los ambientales de siempre (`test_classify_episode_review_composition_e2e_db.py` x1 y `test_submit_review_concurrency_db.py` x3, URL `:5432` fija, `InvalidPasswordError` contra el contenedor ajeno).

Mutantes: 17 en código y migración, todos muertos (F1 4, F2/F3 2, F4 1, front 5, F6 3, F5 3 con re-migración) y 1 sobre el documento (F7). Sin restos: `rg` de los patrones mutados en `src/` y la migración devuelve nada.

## JUICIO

Autor: constructor F. Comparación: código y docs entregados contra cada falla del breaker y contra design D2, D8, D9, D10 y las specs. Confianza alta en F1 a F6 (RED por aserción, GREEN y mutantes); alta en F7 como validación de contrato, no TDD.

- **F1, PUT avisa y congelar rechaza.** Rechazar el `PUT` dejaría sin salida al investigador que renombra una dimensión: el ancla no vale contra el esquema viejo ni contra el nuevo, y editarla primero falla contra el viejo. Con el aviso, el investigador ve qué anclas corregir, y el gate del sha queda en congelar, que es lo que certifica la referencia. La validación usa la misma función que el etiquetado (`evaluar_pedido`) y agrega una regla: el régimen guardado tiene que ser el que la regla da hoy. Así cae también el caso que el breaker no listó (ancla con régimen nulo que la regla nueva ya deriva). No exige completitud de la respuesta esperada (`faltantes_cierre`): el brief no lo pide y sería alcance nuevo.
- **F2/F3**: un guard de tipo en cada `in` sobre set o dict; no cambia el contrato para entradas válidas (suite completa verde).
- **F4**: 409 `sin_muestra` antes de calcular faltantes. El mutante mostró que el `or not item_ids` previo era lo único que impedía cerrar sin muestra con 200; ahora lo cubre un test.
- **F5**: trigger por tabla con el nombre de la tabla en el mensaje; el test exige ese nombre porque con `CASCADE` otra tabla protegida tapaba la falta de un trigger (F5-M2 y F5-M3 lo demuestran).
- **F6**: la forma mínima es la que leen la traza, la evidencia fija y el criterio de terminado; se probó contra un episodio real del ctr-service.
- **F7**: el lugar canónico es el runbook (`docs/servicios/classifier-service.md` §12.2), que es lo que ya decía el ADR; el ADR apunta y no repite.

## SUPOSICIÓN (no verificado)

- No corrí `make test-smoke` (stack no levantado en esta corrección). La lectura del CTR se probó contra el ctr-service real para un episodio cerrado del seed, pero no la carga de muestra ni la traza de punta a punta por el gateway.
- Las specs del change (`codebook-versionado`, `entrenamiento-calibracion`) no tienen un escenario para "congelar con ancla inválida da 422" ni para "cerrar sin muestra da 409 `sin_muestra`". Son artefactos del planner: no los edité. Queda para el orquestador decidir si el planner los agrega o va a DEUDA.
- `design.md` y la línea de "Estado de orquestación" en `tasks.md` siguen con la ruta vieja `~/Descargas/...`: no las toqué (el primero no estaba en el alcance; la segunda la reservó el orquestador).
- La re-migración de `cibse-test-pg` (14:16:36) borró las filas de prueba que habían dejado los tests anteriores en las nueve tablas del estudio. Era la forma de aplicar la migración cambiada; no toqué otras tablas ni otros contenedores.
- `biome check` sobre los tres archivos de test del front marca diferencias de formato en líneas previas de la tanda C. El script `lint` del paquete solo cubre `src/`; no reformateé código ajeno.
- No ejecutado: `ruff`/`mypy` del repo entero, analytics, `create_all`, CI, Clerk.

## Fuentes leídas

`informes/verify-1-breaker.md` (completo) y los 4 tests de reproducción de `scratchpad/breaker/`; `design.md` (D1 a D13); `tasks.md` (estado, registros, convenciones, 13.x); `informes/apply-1-constructor-B.md` líneas 69 a 110 (forma del meta-esquema); el comienzo de `informes/apply-1-constructor-E.md` (formato) y `informes/LEEME.md`; código: `services/estudio_esquema.py`, `services/ctr_lectura.py`, `services/estudio_muestra.py` (consumidores del episodio), `routes/estudio.py` (codebook), `routes/estudio_trabajo.py` (traza, cierre, anclas), la migración 0007, `tests/integration/conftest.py` y los tests del estudio que toqué; ctr-service `schemas/__init__.py` (`EpisodeWithEvents`); web-teacher `views/estudio/{CodificacionEstudioView,AdministracionEstudioView,mensajesError}`, `lib/estudioApi.ts` y sus tests; `docs/servicios/classifier-service.md` §12 y ADR-063 D9. No leí las specs completas (solo lo que cita el breaker).

## Contaminación

Partí de los hallazgos y los tests del breaker (pedido explícito del orquestador): los tests de regresión del repo derivan de sus reproducciones. Del informe B tomé solo la forma del meta-esquema, verificada después contra `validar_esquema`. Mismo proveedor y familia que todos los roles previos: no hay independencia por proveedor.
