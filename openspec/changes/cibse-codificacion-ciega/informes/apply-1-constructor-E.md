# apply-1-constructor-E: grupo 13 (smoke E2E y revisión entregada)

- Rol: constructor. Ejecutor: subagente nativo Claude Code (familia Anthropic, misma que planner, plan-reviewer y constructores A a D).
- Fecha: 04/11/2026, 13:35 a 13:52 (-03:00).
- Revisión: árbol de trabajo sobre HEAD `b32e621` (rama `feat/cibse-codificacion-ciega`), sin commits. Huella (excluye `openspec/changes/cibse-codificacion-ciega/`): `git diff HEAD | sha256sum` = `7baa7f619f747ee1058b49a13b20c48bb5e8f237630a71c8a695fd423308ac25`; 59 archivos sin seguimiento, sha256 de la lista ordenada = `133998efb5c58f40eac4899a0cb1f0c9ec865477d670fa6ae76f2135172a5f34` (lista en `scratchpad/c132/untracked.sha256`; script `scratchpad/hash-arbol.sh`). Igual antes (13:47:47) y después (13:51:19) de los checks.
- Archivos tocados: nuevo `tests/e2e/smoke/test_smoke_estudio_codificacion.py` (sha256 `aed43bbfa508833afe15fdc59a61382ed7201eb26e6a200b5967c7a4609b0ae8`); `CLAUDE.md` (conteo smoke 57 -> 63, fecha, ejemplo `rg` 77 -> 83); `tasks.md` (evidencia bajo 13.1 y 13.2; "Estado de orquestación" sin tocar); este informe y su fila en `LEEME.md`. Sin cambios de producción.
- Lecciones L-NNN: no existen en el repo (declarado por el orquestador en tasks.md; no se repitió la búsqueda).

## EVIDENCIA

### 13.1 Smoke E2E

Entorno (sin tocar recursos ajenos; `seguridad_jwt_db` en el 5432 intacto):
- `cibse-smoke-pg` (pgvector/pgvector:pg16, `127.0.0.1:55433`, tmpfs, `init-dbs.sql`) y `cibse-smoke-redis` (redis:7-alpine, `127.0.0.1:6379`, puerto libre). Creados por mí.
- `uv run bash scripts/migrate-all.sh` -> exit 0, 4 bases a head (classifier `20261104_0007`). `academic_service.seeds.casbin_policies` -> `[OK] 213 policies`. `scripts/seed-3-comisiones.py` -> exit 0 (el seed de CI).
- 13 servicios HTTP + 8 workers del CTR (mismo listado que `scripts/dev-start-all.sh`), lanzados con `uv run --project` desde un cwd sin `.env` (como CI), `DEV_TRUST_HEADERS=true`, mocks, `EXECUTION_ENABLED=true`, `PROMPTS_REPO_PATH` del repo. `/health`: 8000 503 (Keycloak ausente; el gate acepta 503), resto 200. Scripts: `scratchpad/smoke/env.sh`, `start.sh`; logs `scratchpad/smoke/logs/`.

Corridas:

| Hora | Comando | Resultado |
|---|---|---|
| 13:39:45 | `make test-smoke` (línea de base, sin el archivo nuevo) | `94 passed, 2 skipped, 20 deselected` |
| 13:41:39 | `uv run pytest tests/e2e/smoke/test_smoke_estudio_codificacion.py -m smoke` | `6 passed` (nacen verdes: el código ya existe) |
| 13:42:30 | M1 `prompt_kind` permitido en `prompt_enviado` | `AssertionError: {'prompt_kind'}`, 1 failed |
| 13:42:37 | M2 `intento_adverso_detectado` en `TIPOS_INCLUIDOS` | SOBREVIVE, `6 passed` |
| 13:42:45 | M3 exportación con `ROLES_ESTUDIO` | `AssertionError: codificador exportando: 200 ...` |
| 13:43:03 | M4 sin chequeo de `cerrada_at` al guardar | falla `(status, detail) == (409, 'codificacion_cerrada')` |
| 13:43:11 | M5 alta de membresía sin `lower()` | SOBREVIVE, `6 passed` |
| 13:43:38 | aserción nueva sobre `GET .../membresias` | `6 passed` |
| 13:43:42 | M5 de nuevo | `AssertionError: las membresias se guardan con el email en minusculas` |
| 13:43:18 | M6 email en la columna `alias` exportada | falla la aserción del conjunto `(alias, regimen, dim_d1_valor)` |
| 13:43:50 | M7 traza con `enunciado: None` | `AssertionError: la traza deberia traer el enunciado revisado` |
| 13:43:57 | M8 `filtrar_traza(eventos, seq_tope - 1)` | falla `elementos[-1]["tipo"] == "fin_cerrado"` |
| 13:44 | `python3 scripts/check-claude-md.py -v` antes de editar | `[FAIL] Smoke tests E2E: CLAUDE.md dice 57, codigo tiene 63` |
| 13:44:21 | ídem después de editar CLAUDE.md | `[OK] Smoke tests E2E: 63`, `sin drift` |
| 13:44:26 | `make test-smoke` | `100 passed, 2 skipped, 20 deselected` (revisión previa al refactor) |
| 13:46:53 | focal tras el refactor del helper | `6 passed` |
| 13:46:57 | M1b (M1 repetido tras el refactor) | `AssertionError: {'prompt_kind'}` |
| 13:47:06 | `make test-smoke` sobre la revisión ENTREGADA | `100 passed, 2 skipped, 20 deselected`; `check-claude-md` `[OK]` |

Mutantes: cada uno con respaldo y diff en `scratchpad/smoke/mutantes/<nombre>.{bak,diff}`, classifier reiniciado con el mutante y otra vez tras revertir; `cmp` respaldo vs. archivo actual: OK en los 9. Búsqueda de restos (`if False:`, `seq_tope - 1`, `+ m.email`, `"enunciado": None`, `"prompt_kind"))`) en `src/`: sin resultados.

Los 2 skips son los de la línea de base (BYOK sin `BYOK_MASTER_KEY`, runner sin `RUNNER_TOKEN`).

### 13.2 Revisión entregada

| Hora | Comando | Resultado |
|---|---|---|
| 13:47:54 | `uv run ruff check .` | exit 1, 2 errores (`PLW2901`, `PLR0915`) en `scripts/backfill-attestations.py` |
| 13:47:54 | `uv run ruff format --check .` | exit 1, `Would reformat: scripts/backfill-attestations.py`; 784 formateados |
| idem | ambos con `--exclude scripts/backfill-attestations.py` | `All checks passed!` / `784 files already formatted` |
| 13:46:20 | `uv run mypy .` | `Success: no issues found in 371 source files` |
| 13:47:58 | `uv run pytest apps/classifier-service -q -rs` (`CLASSIFIER_TEST_DB_URL` a `:55432`, `CLASSIFIER_TEST_MIGRATION_CYCLE=1`) | `4 failed, 617 passed`, sin skips |
| 13:48:51 | `uv run pytest apps/analytics-service -q` | `182 passed` |
| 13:50:24 | 4 archivos de `create_all` (1.1) | `36 passed` |
| 13:50:29 | `make check-rls` (4 URLs a `:55432`) | `[OK]` |
| 13:50:30 | `make check-rls` (4 URLs a `:55433`, stack del smoke) | `[OK]` |
| 13:50:34 | `cd apps/web-teacher && pnpm test` | `51 passed (51)` archivos, `677 passed (677)` tests |
| 13:51:05 | base limpia `cibse-clean-pg` `:55434`: `alembic upgrade head` | `20261104_0007 (head)` |
| 13:51:06 | `alembic downgrade -1` | `20260906_0006`, 0 tablas del estudio |
| 13:51:08 | `alembic upgrade head` | `20261104_0007 (head)`, 9 tablas |

Fallas preexistentes, con evidencia contra origin/main:
- ruff: `git show origin/main:scripts/backfill-attestations.py` -> exit 128 (no existe en origin/main). Único commit `43c605c` (2026-09-01, rama `feat/backfill-attestaciones`). Archivo sin seguimiento desde 2026-10-01 15:21; el informe A lo vio sin seguimiento antes de empezar el apply.
- classifier, 4 fallos: `test_precheck_mas_gobernanza_bajo_el_router_completo`, `test_dos_revisiones_concurrentes_no_pierden_la_primera`, `test_segunda_revision_tras_commit_de_la_primera_no_pisa`, `test_conflicto_contra_reclasificacion_automatica_sugiere_reintentar`, todos `InvalidPasswordError`. Sus archivos (`test_classify_episode_review_composition_e2e_db.py`, `test_submit_review_concurrency_db.py`) fijan `127.0.0.1:5432` y son idénticos a `git show origin/main:<archivo>` (`diff` vacío). El 5432 es del contenedor ajeno.

## JUICIO

Autor: constructor E. Confianza alta en los conteos (salidas propias, revisión identificada); media en lo que el smoke prueba de la traza ciega.

- 13.1 está hecha con ejecución real: el smoke corre contra api-gateway, classifier y ctr-service reales con Postgres y Redis reales, y 7 de 8 mutantes de producción lo tumban por aserción. Primera vez que se verifica la lectura classifier -> ctr-service real (12.2 la había corrido con un CTR falso). Esto vale para la configuración local sin firma de gateway.
- La ausencia de `intento_adverso_detectado` en la traza NO se prueba en el smoke: el seed de CI no tiene ese evento, y el mutante M2 sobrevive. Sí se prueba la ausencia de `prompt_kind` (precondición afirmada contra el crudo). Para que el smoke lo pruebe hace falta un seed con eventos adversos o que el test los genere vía tutor (abrir, mandar un prompt adverso, cerrar, esperar a los workers). Lo propongo como DEUDA para el orquestador; no lo hice porque el encargo pedía un episodio del seed y tocar el seed queda fuera del alcance.
- 13.2: todo en verde salvo dos fallas preexistentes y ajenas al change (un script sin seguimiento de otra rama y 4 tests que fijan el 5432). Ningún archivo del change falla un check.
- Observación ajena al change (hecho observado, causa no investigada): cada `make test-smoke` dejó 2 contenedores `eclipse-temurin:21-jdk` (`--network none`, `AutoRemove=true`) corriendo al 100 % de CPU después de terminar la corrida: 6 en total, creados a las 13:39:55, 13:40:05, 13:44:36, 13:44:46, 13:47:16 y 13:47:26 (UTC-3), coincidentes con `test_smoke_java_execution` (bucle infinito). Los de 13:39 seguían vivos mientras el execution-runner estaba arriba, así que no parece efecto de haberlo detenido. Los maté con `docker kill` (eran de mis corridas). Si se reproduce en un entorno real, el sandbox no corta el contenedor al vencer el wall-time; queda para quien sea dueño de ADR-060, fuera de este change.
- El smoke crea un estudio por corrida y no hay baja de estudios: deja filas en `classifier_db`, como otros smoke (BYOK, episodios). Aceptable; queda dicho en el docstring.

## SUPOSICIÓN

- Que el smoke pase en CI: no corrí CI (no hay push). El workflow `e2e-smoke.yml` usa el mismo seed, `SMOKE_PG_DSN` y `DEV_TRUST_HEADERS`; no hay `cibse-smoke-*` en CI sino el Postgres del job en 5432. No verificado.
- La lectura classifier -> ctr con `REQUIRE_GATEWAY_SIGNATURE`/`GATEWAY_SHARED_SECRET` de producción: no verificada (sigue en "Workflow follow-up").
- `pnpm turbo lint typecheck` y `build` del web-teacher no se corrieron (no están en 13.2); su última evidencia es la de la tanda C sobre una huella anterior, y desde entonces el web-teacher no cambió por este grupo.
- No se corrió `make test-sin-stack`.

## Fuentes leídas

`tasks.md` (completo), `CLAUDE.md` del repo (secciones del smoke, `DEV_TRUST_HEADERS`, gotchas), `tests/e2e/smoke/{conftest.py,_helpers.py,README.md,test_smoke_language_provenance.py}`, `.github/workflows/e2e-smoke.yml`, `Makefile` (test-smoke, check-rls), `scripts/{dev-start-all.sh,migrate-all.sh,check-rls.py (variables),seed-smoke.py (encabezado)}`, `apps/api-gateway/.../middleware/jwt_auth.py` (rama dev), rutas `routes/estudio.py` y `routes/estudio_trabajo.py` (firmas y los puntos mutados), `services/{traza_ciega.py,ctr_lectura.py}` (encabezados), `tests/integration/conftest.py` (`EstudioHTTP`, esquema de prueba), `tests/integration/test_estudio_separacion_db.py`. No leí `design.md` entero (solo lo citado en tasks). `.env` no se leyó (permiso denegado; tampoco hacía falta: los servicios corrieron desde un cwd sin `.env`).

## Contaminación

- Informes ajenos: usé `informes/apply-1-constructor-A.md` solo para confirmar que `scripts/backfill-attestations.py` ya estaba sin seguimiento al empezar el apply (línea citada). No leí B, C ni D; los datos de sus tandas que menciono vienen de `tasks.md`, que es su registro.
- Mismo proveedor y familia que los constructores A a D y que planner y plan-reviewer: no hay independencia de juicio respecto de ellos.
