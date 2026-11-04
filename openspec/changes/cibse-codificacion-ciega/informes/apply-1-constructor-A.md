# apply-1-constructor-A: tanda A (grupos 1 a 5)

- Rol: constructor. Fase apply, intento 1, tanda A (1 línea de base; 2 modelo, migración y triggers; 3 meta-esquema y régimen según la regla; 4 acceso y membresías; 5 codebook versionado).
- Ejecutor: subagente nativo Claude Code (familia Anthropic). Fecha: 04/11/2026, 12:16 a 12:48 (-03:00).
- Revisión: árbol de trabajo sobre `origin/main b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits. Archivos entregados y sha256 (primeros 16 hex) al cierre:

| Archivo (bajo `apps/classifier-service/`) | Estado | sha256 |
|---|---|---|
| `alembic/versions/20261104_0007_estudio_codificacion.py` | nuevo | `3061a9266d483898` |
| `src/classifier_service/models/estudio.py` | nuevo | `35ee44add8554374` |
| `src/classifier_service/models/__init__.py` | modificado (import al final y `__all__`) | `46b029d56d4392b2` |
| `src/classifier_service/routes/estudio.py` | nuevo | `a17e16fa3ba804eb` |
| `src/classifier_service/services/estudio_codebook.py` | nuevo | `3fa816c532a1e8bf` |
| `src/classifier_service/services/estudio_esquema.py` | nuevo | `4e1ea7ac8730427a` |
| `src/classifier_service/services/traza_ciega.py` | nuevo (solo `TRAZA_VERSION`) | `443337ad951e5820` |
| `src/classifier_service/main.py` | modificado (registra el router) | `3b5d646614426925` |
| `tests/integration/conftest.py` | modificado (`CLASSIFIER_TEST_DB_URL`, fixtures `test_db_url` y `app_db`) | `f1ef478c3958d0dd` |
| `tests/integration/test_estudio_schema_db.py` | nuevo, 9 tests | `9bc03e89c0156848` |
| `tests/integration/test_estudio_inmutabilidad_db.py` | nuevo, 26 tests | `9dae2e9344ec63c8` |
| `tests/integration/test_estudio_acceso_db.py` | nuevo, 30 tests | `5b5ffd26730d3bfa` |
| `tests/integration/test_estudio_codebook_db.py` | nuevo, 27 tests | `2873bc0b8fceee21` |
| `tests/unit/test_estudio_esquema.py` | nuevo, 77 tests | `e490239b38a48611` |
| `tests/unit/test_estudio_codebook.py` | nuevo, 6 tests | `9dacc42f9fabf22c` |

Además: `openspec/changes/cibse-codificacion-ciega/tasks.md` (evidencia bajo 1.1, 2.1, 2.2, 3.1, 3.2, 4.1, 5.1 y sección nueva "Registro del constructor"; no se tocó "Estado de orquestación") y este informe más su fila en `informes/LEEME.md`. Nada commiteado ni pusheado. No se tocó tutor-service, ctr-service, academic-service, api-gateway ni web-teacher.

## EVIDENCIA

Detalle completo por tarea (comandos, timestamps, salidas, diffs de mutantes) en `tasks.md`. Resumen:

- **Entorno de base**: el puerto 5432 lo ocupa un contenedor de OTRO proyecto (`seguridad_jwt_db`, postgres:16-alpine, sin `classifier_db`); `platform-postgres` está detenido. No se tocó el contenedor ajeno. Se levantó un Postgres efímero propio: `cibse-test-pg` (`pgvector/pgvector:pg16`, `127.0.0.1:55432`, datos en tmpfs, `infrastructure/postgres/init-dbs.sql`), usuario `classifier_user` (dueño, no superuser: RLS forzado aplica). Queda corriendo para reuso.
- **Línea de base (1.1)**, 12:16 a 12:18: classifier `4 failed, 224 passed, 10 errors` (falla ambiental: `InvalidPasswordError` contra el contenedor ajeno); analytics `182 passed`; 4 archivos de `create_all` `36 passed`; web-teacher `512 passed (39 files)`; typecheck web-teacher sin errores.
- **RED por aserción observado en cada tarea de código** (todas las corridas sin skips, `-rs`):
  - 2.1 12:22:26 `9 failed` (`AssertionError: faltan tablas del estudio`).
  - 2.2 12:28:35 `22 failed, 4 passed` (`DID NOT RAISE DBAPIError`; los 4 verdes son controles de lo permitido).
  - 3.1/3.2 12:32:08 `72 failed, 5 passed` contra un stub sin comportamiento (declarado); un caso fallaba por `KeyError` y se reescribió hasta fallar por aserción (12:32:22).
  - 4.1 12:36:32 `29 failed` (`assert 404 == 201`, etc.).
  - 5.1 12:41:10 `29 failed, 4 passed` contra stub de `sha256_codebook`.
- **GREEN**: 2.1 12:24:29 `9 passed`; 2.2 12:29:13 `35 passed`; 3.1 12:33:04 (37 de validación); 3.2 12:33:37 `77 passed`; 4.1 12:37:23 `29 passed` (30 tras triangular mayúsculas); 5.1 12:41:29 unit `6 passed`, 12:42:12 `33 passed`. Re-corrida tras refactor 12:43:36: `175 passed` (todos los tests del estudio).
- **Literal del sha del codebook** calculado fuera de la implementación (JSON canónico escrito a mano + `sha256sum`): `51c3389612d2e87b72a2bab32177a2d3b23d2ec53dcb1b096b5fd7ced75e775f`; la implementación lo reproduce.
- **Mutantes**: 43 ejecutados, 43 muertos, todos revertidos (diffs en el scratchpad de la sesión, `mutante-*.diff`; script `mutar.py` que baja la base, aplica, corre, revierte y re-migra). 2.1: 6 (RLS en `check-rls` y en test; 5 unicidades). 2.2: 7 triggers quitados + 4 de bloqueo de más sobre los controles. 3.2: los 5 del plan + 4 para los nacidos verdes. 4.1: (a) a (e) del plan + alta sin minúsculas. 5.1: los 3 del plan + 8 (incluidos los 4 nacidos verdes y roles). Tres mutantes murieron primero por excepción y no por aserción; se corrigió el test y se re-corrió hasta muerte por aserción (ver JUICIO).
- **Cierre de la tanda** (una vez, árbol entregado):
  - 12:44:09 `uv run pytest apps/classifier-service -q -rs` con `CLASSIFIER_TEST_DB_URL` y `CLASSIFIER_TEST_MIGRATION_CYCLE=1` -> `4 failed, 409 passed`. Los 4 son de la línea de base, con URL `:5432` fija en su propio archivo (no usan el conftest). Sin variables: `30 failed, 311 passed, 1 skipped, 71 errors` (ambiental).
  - 12:45:09 `create_all` x4 -> `36 passed`; 12:45:11 analytics -> `182 passed` (iguales a la línea de base).
  - 12:46:44 `make check-rls` -> `[OK]`; `alembic current` -> `20261104_0007 (head)`; `ruff check apps/classifier-service` -> limpio; `ruff format --check apps/classifier-service` -> `72 files already formatted`; `mypy apps/classifier-service/src` -> `no issues found in 33 source files`.
  - `rg -i "la trampa|sobreuso manda|si ves que sobreusa" apps/classifier-service/src` -> sin resultados.

## JUICIO

Autor: constructor (esta sesión). Comparación: implementación contra design D1 a D3, D8, D9, D10b (locks usados en 4 y 5) y specs `estudio-codificacion-acceso` y `codebook-versionado`. Confianza: alta en lo verificado por los tests y mutantes listados; media en las decisiones de interpretación de abajo, que el rompedor y el auditor deberían mirar.

- Tareas cerradas: 1.1, 2.1, 2.2, 3.1, 3.2, 4.1, 5.1. Abiertas: ninguna de la tanda A. No se hizo nada de los grupos 6 en adelante.
- Calidad de los RED: tres mutantes murieron al principio por una causa que no era la aserción y se tomaron como señal de test flojo, no como evidencia: (1) 4.1(e) sin `require_gateway_auth` murió por `InvalidPasswordError` porque el test de 401 no apuntaba la app a la base de pruebas; se agregó `app_db` y murió por `assert 200 == 401`; (2) 5.1 "PUT sobre congelada" murió por la excepción del trigger propagada por `ASGITransport`; se pasó a `raise_app_exceptions=False` y murió por `assert 500 == 409` (de paso muestra que la base frena la edición aunque la API falle); (3) 4.1(c2) "alta sin minúsculas" sobrevivió al filtro de mayúsculas porque la búsqueda compara `lower` en ambos lados; murió con la aserción de la fila guardada.
- Decisiones de interpretación (no estaban cerradas en el plan):
  1. Meta-esquema: clave opcional NUEVA `notas_obligatorias_si_frontera` (bool, exige `marca_frontera`), necesaria para el escenario "Notas obligatorias" de la spec ("y el esquema las exige en ese caso"); D9 no nombra cómo se expresa. `regimen_por_defecto` y `regimenes_exentos` como claves de primer nivel; `regimenes_exentos` por defecto `[regimen_evidencia_insuficiente]`; claves de dimensión y régimen `^[a-z][a-z0-9_]{0,39}$` (van a nombres de columna en la exportación). Si el planner prefiere otra forma, afecta el esquema v0 que prepara el orquestador.
  2. `regimen_regla` solo se calcula si TODAS las dimensiones referenciadas por cualquier regla tienen valor (no hay evaluación parcial aunque una regla temprana ya decida).
  3. `require_membresia` es una función llamada dentro de la sesión del handler, no un `Depends`, para que la atadura del `user_id` comparta la transacción del pedido. `GET mis-membresias` cuenta como primer uso y ata.
  4. Revocación por `DELETE .../membresias/{membresia_id}`; alias `I<n>`/`C<n>` contando revocadas; alta y revocación bloquean la fila del estudio.
  5. Sin vigente: `404 {"detail": "sin_codebook"}`. Re-fijar la misma vigente con etiquetas es 200 no-op. Etiqueta de versión `vigente` reservada.
  6. El trigger de anclas falla CERRADO si la versión no es visible (RLS); la evidencia fija incluye `item_id` y `estudio_id`. `estudio_ancla` lleva `estudio_id` (lock y exclusión con la muestra por estudio).
  7. El cambio en `tests/integration/conftest.py` (URL por variable, mismo default) es infraestructura de test necesaria por el puerto ocupado; los tests HTTP del estudio commitean bajo tenant aleatorio y dejan filas inmutables (versiones congeladas): correrlos contra base efímera, documentado en el conftest.
- Huecos que van a necesitar tandas siguientes (fuera del plan, no agregados): listar membresías del estudio (el `DELETE` necesita el `membresia_id`, que hoy solo devuelve el alta) y leer o listar versiones no vigentes; los dos los va a pedir el panel de 11.8. Las altas y bajas de anclas de 7.3 deben tomar el lock `FOR UPDATE` del estudio, que es lo que serializa el congelado.

## SUPOSICIÓN

- `gen_random_uuid()` (default de PK en la migración) requiere Postgres 13 o más; no verifiqué la versión de Postgres de producción (EasyPanel).
- Los tests `_db` y la migración `0007` no corren en CI: `test-unit` solo junta `apps/*/tests/*.py` y `apps/*/tests/unit/`, y `migrations-dry-run` solo migra academic (leído en `.github/workflows/ci.yml`, no ejecutado). En CI solo corren `test_estudio_esquema.py` y `test_estudio_codebook.py`.
- No verifiqué el comportamiento con `require_gateway_signature=True` y firma VÁLIDA más allá del test existente `tests/test_auth.py` (25 passed en la regresión de 4.1): el email (`X-User-Email`) no está cubierto por la firma, como dice design D3; la atadura al `user_id` es la mitigación.
- No ejecutado: `pnpm test`/typecheck del web-teacher al cierre (la tanda no lo toca y está siendo modificado por otro actor), `ruff`/`mypy` del repo entero, `make test-smoke`, migración en base limpia distinta de la efímera (sí hice ciclo downgrade/upgrade en la efímera, dentro de `test_migracion_baja_y_vuelve_a_subir_limpia`).
- Observación de concurrencia (hecho observado, causa supuesta): entre 12:21 y al menos 12:47, otro actor creó y modificó archivos en `apps/web-teacher` (`src/lib/estudioApi.ts`, `src/utils/accesoPanel.ts`, `src/utils/diffLineas.ts`, `src/views/estudio/*`, borró `views/InterraterTraining.tsx`, `views/InterraterCodingView.tsx`, `views/interraterShared.tsx`, modificó `main.tsx`, `routes/__root.tsx`, `helpContent.tsx` y tests). No fui yo: al empezar, `git status` solo mostraba `openspec/`, `openspec/config.yaml` y `scripts/backfill-attestations.py`. Supongo que es la tanda del frontend corriendo en paralelo, en contra de "ejecución secuencial" del Estado de orquestación. No lo toqué. Mi línea de base del web-teacher (12:18) es anterior a esos cambios. Si ese actor escribe `tasks.md`, hay riesgo de que se pisen ediciones: verifiqué a las 12:47 que mis registros siguen ahí.

## Fuentes leídas

`proposal.md`, `design.md`, `tasks.md` (incluida "Convenciones para el constructor"), `specs/estudio-codificacion-acceso/spec.md`, `specs/codebook-versionado/spec.md`, `specs/estudio-codificacion/spec.md`; `openspec instructions apply --change cibse-codificacion-ciega --json`; `CLAUDE.md` del repo (invariantes, RLS, pytest); código de classifier-service: `models/__init__.py`, `db/__init__.py`, `auth/__init__.py`, `auth/gateway_auth.py`, `main.py`, `config.py`, `routes/interrater.py` (cabecera y `/sample`), `routes/classify_ep.py` (estilo de logs), migraciones `0003` y `0006`, `alembic/env.py`, `tests/integration/conftest.py`, cabeceras de `test_review_service_db.py`, `test_classify_episode_review_composition_e2e_db.py`, `test_submit_review_concurrency_db.py`, `tests/test_auth.py`, `tests/unit/test_review_routes.py`; `infrastructure/postgres/init-dbs.sql`, `scripts/check-rls.py`, `Makefile` (check-rls, migrate), `pyproject.toml` (ruff), `.github/workflows/ci.yml` (test-unit, migrations-dry-run), `apps/analytics-service/tests/unit/test_cohort_slopes_batch.py` (fixture `create_all`). Lecciones L-NNN: busqué `L-0NN` en `docs/` y `openspec/` y archivos `*lecci*`/`*lesson*`: ninguno (coincide con lo que reportó el orquestador). No se leyó `.env` (bloqueado por permisos; no hizo falta).

## Contaminación por informes previos

No leí los informes `propose-*` del planner ni del plan-reviewer; solo los artefactos del change y las líneas de base que el brief del orquestador cita (36 passed en `create_all`, 182 en analytics), que reproduje por mi cuenta antes de cambiar nada. La sección "Estado de orquestación" de `tasks.md` la leí como contexto, sin editarla.
