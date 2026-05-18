## Why

Tres bugs chicos pero visibles bloquean la demo del piloto UNSL para defensa doctoral:

1. **`scripts/seed-3-comisiones.py` rompe la promesa de `template_id` que la tesis defiende**: los 94 episodios sembrados apuntan a `problema_id=99999999-9999-9999-9999-999999999999` (constante hardcodeada que NO existe como `TareaPractica` real en la base). El seed crea correctamente 2 templates + 6 instancias con `template_id` poblado, pero los `Episode.problema_id` jamas son redirigidos a esas instancias. Resultado: `GET /api/v1/analytics/student/{id}/cii-evolution-longitudinal` y `/cohort/{id}/cii-quartiles` devuelven `insufficient_data: true` aunque haya datos suficientes — se rompe el JOIN `episodes.problema_id -> tareas_practicas.id -> tareas_practicas_templates.id`. **Esto es el corazon de ADR-018 / RN-130** (CII evolution longitudinal por `template_id`) y la prueba mas visible de la propiedad multidimensional N4 ante el comite.

2. **`PROMPT_SYSTEM_VERSION = "v1.0.0"` hardcodeado en el seed contradice runtime**: el seed registra eventos CTR con `prompt_system_version="v1.0.0"`, pero `Settings.default_prompt_version="v1.0.1"` en `apps/tutor-service/src/tutor_service/config.py:37` y `ai-native-prompts/manifest.yaml` declara `tutor: v1.0.1`. Episodios viejos (data sembrada) ven una version y los que cree el tutor en runtime registran otra. Viola el invariante G12 ("manifest declarativo + config efectivo deben mantenerse alineados", CLAUDE.md). Ambos prompts (`v1.0.0/system.md` y `v1.0.1/system.md`) existen ya en disco con `manifest.yaml` firmado — el bug es que el seed se desfasa.

3. **`GET /api/v1/comisiones` no expone `nombre`**: el modelo `Comision` (apps/academic-service/src/academic_service/models/operacional.py:56-94) tiene solo `codigo` (e.g. "A"), `cupo_maximo`, `horario`, `curso_config_hash`, `ai_budget_monthly_usd`. **No hay columna `nombre`**. El seed pasa `nombre` como key del dict Python pero nunca lo persiste — la columna no existe. Selectores de los 3 frontends muestran solo "A", "B", "C" sin etiqueta humana ("A-Manana", "B-Tarde", "C-Noche"). Es feo en la demo y fuerza a memorizar codigos.

## What Changes

- **Reescritura quirurgica de `scripts/seed-3-comisiones.py`**: reemplazar la constante `PROBLEMA_ID` por un mapping deterministico `(comision_id, ep_idx) -> tarea_practica_instance_id` que distribuya los episodios round-robin sobre las 6 instancias de TP (3 comisiones x 2 templates). Esto preserva la idempotencia y el orden estable del `episode_refs` que `seed_classifications` consume.
- **Bumpear `PROMPT_SYSTEM_VERSION` a `"v1.0.1"`** en el seed (linea 82) y recomputar el `PROMPT_SYSTEM_HASH` apuntando al `system.md` de v1.0.1 (sha256 declarado en `ai-native-prompts/prompts/tutor/v1.0.1/manifest.yaml:8`). Mantener el comportamiento bit-exact de los hashes CTR (ADR-010).
- **Agregar columna `nombre` a `comisiones`**:
  - Migracion Alembic en `apps/academic-service/alembic/versions/` (e.g. `20260430_0001_comision_nombre.py`) que agrega `nombre VARCHAR(100) NOT NULL` con default backfill desde `codigo` para registros existentes.
  - Campo `nombre: Mapped[str]` en `Comision` (operacional.py).
  - Campo `nombre: str = Field(min_length=1, max_length=100)` en `ComisionBase` (schemas/comision.py).
  - Confirmar que el seed ya pasa `nombre` (tiene la key, falta agregarlo al INSERT — lineas 482-496 del seed).
- **BREAKING (interno, NO publico)**: re-correr `seed-3-comisiones.py` borra y rehace tenant `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`. Documentado en docstring del seed.

## Capabilities

### New Capabilities
<!-- Ninguna nueva capability. Es deuda chica sobre capabilities ya activas. -->

### Modified Capabilities
- `academic-comisiones`: el response de `GET /api/v1/comisiones`, `GET /api/v1/comisiones/{id}` y `GET /api/v1/comisiones/mis` agrega el campo `nombre` (string, 1-100 chars). `POST` y `PATCH` lo aceptan. Migration Alembic + nueva columna NOT NULL.
- `pilot-demo-seed`: `seed-3-comisiones.py` deja los `Episode.problema_id` apuntando a instancias de TP reales (no a `99999999-...`), habilitando el JOIN longitudinal por `template_id`. Bumpea `prompt_system_version/hash` a v1.0.1 para alinear con runtime.

## Impact

### Archivos que cambian (en la fase apply, NO ahora)
- `scripts/seed-3-comisiones.py` (reescritura del mapping problema_id + bump version)
- `apps/academic-service/alembic/versions/20260430_0001_comision_nombre.py` (NUEVO)
- `apps/academic-service/src/academic_service/models/operacional.py` (Comision.nombre)
- `apps/academic-service/src/academic_service/schemas/comision.py` (ComisionBase.nombre, ComisionUpdate.nombre opcional)
- `apps/academic-service/src/academic_service/services/comision_service.py` (opcional: update logic acepta nombre)
- Tests: `apps/academic-service/tests/unit/test_comision_routes.py` o equivalente, asegurar `nombre` en payloads

### Archivos que NO cambian (criticos — no romper)
- `packages/contracts/src/platform_contracts/ctr/hashing.py` (ADR-010, hashing canonico)
- `apps/ctr-service/**` (CTR es append-only — solo el seed reescribe data demo, no la migracion)
- `ai-native-prompts/prompts/tutor/v1.0.0/**` y `v1.0.1/**` (ya estan firmados con manifest.yaml)
- `apps/tutor-service/src/tutor_service/config.py` (default_prompt_version ya esta en v1.0.1)
- `apps/governance-service/**` (manifest loader ya correcto)
- `ROUTE_MAP` del api-gateway (`/api/v1/comisiones` ya esta expuesto)

### Riesgos

- **Re-ejecutar `seed-3-comisiones.py` es destructivo** — borra tenant `aaaa...` y rehace todo el estado academico/CTR/classifications. Si alguien inserto data demo manual post-seed, se pierde. Documentar en docstring + en `docs/SESSION-LOG.md` la fecha de re-corrida. NO pisar bases de profesores reales (mitigado: el seed esta scopeado a `TENANT_ID = aaaa...` y siempre fue asi).
- **Migracion `comisiones.nombre NOT NULL`**: con backfill desde `codigo` para filas existentes, no hay nulls. Validar que no haya tests de la suite que asumen el shape viejo de `ComisionOut` sin `nombre` — si los hay, actualizarlos en el mismo PR (testeo obligatorio en PRs por convencion CLAUDE.md).
- **Prompt version bump del seed NO regenera classifications historicas** — los episodios viejos del piloto (si los hubiera) seguirian con `v1.0.0`. En el piloto UNSL aun no hay data real produccion; aplicable solo a la data demo. No hay riesgo de ROMPER cadenas SHA-256 porque el seed reconstruye todo desde cero (idempotente).
- **No se toca el prompt body de v1.0.1** — su `manifest.yaml` ya tiene el sha256 firmado y system.md presente. Si en el futuro se decide cambiar el cuerpo del prompt, eso es OTRO change (otro ADR).

### Non-goals (explicitamente fuera de scope)

- **NO agregar `materia_nombre` ni denormalizar otros campos** al response de comisiones. El frontend debe seguir resolviendo nombres de materia/periodo via `/api/v1/materias/{id}` cuando los necesite.
- **NO escribir prompt v1.0.1 nuevo body** — ya existe en disco con manifest firmado (`bump_kind: patch_documental`, texto identico salvo header de version + correccion HTML comment 4/10 -> 3/10). Solo reconciliamos lo que el seed registra.
- **NO tocar migraciones del CTR ni del classifier** — el cambio del seed reescribe las filas pero no toca el schema de `ctr_store` ni `classifier_db`.
- **NO modificar `LABELER_VERSION` del classifier** (sigue en `1.1.0`, ADR-023).
- **NO incorporar `nombre` al UNIQUE constraint** `uq_comision_codigo` — la unicidad sigue siendo `(tenant_id, materia_id, periodo_id, codigo)`. `nombre` es etiqueta humana, no clave.
- **NO refactorizar `seed-demo-data.py`** (el seed mas chico) — solo `seed-3-comisiones.py` (el que usa el piloto UNSL para defensa).

### Acceptance criteria (verificables, ejecutables)

1. Tras correr `uv run python scripts/seed-3-comisiones.py`:
   - `GET /api/v1/analytics/student/b1b1b1b1-0001-0001-0001-000000000001/cii-evolution-longitudinal?comision_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` (con headers `X-Tenant-Id`, `X-User-Id`, `X-User-Roles=docente`) devuelve `slope_per_template` con al menos 1 template con `insufficient_data: false` y `slope` no-null.
   - `GET /api/v1/analytics/cohort/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/cii-quartiles` devuelve cuartiles validos (no `insufficient_data`) — los 6 estudiantes de comision A pasan el threshold `MIN_STUDENTS_FOR_QUARTILES = 5`.
2. `SELECT DISTINCT prompt_system_version FROM events WHERE tenant_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'` devuelve solo `v1.0.1` post-seed.
3. `SELECT DISTINCT problema_id FROM episodes WHERE tenant_id='aaaa...'` devuelve **6 UUIDs** (uno por instancia de TP), NO el `99999999-...` legacy.
4. `GET /api/v1/active_configs` devuelve `tutor: v1.0.1`, alineado con la primera muestra de `events.prompt_system_version` del seed.
5. `GET /api/v1/comisiones` devuelve cada item con `nombre` no-null (e.g. `"A-Manana"`, `"B-Tarde"`, `"C-Noche"`).
6. `make migrate` aplica la migracion Alembic sin errors. `make test` pasa con suite ampliada (test de schema con `nombre`).
7. `make check-rls` sigue pasando — no se introducen tablas con `tenant_id` sin RLS (el cambio es solo agregar columna a tabla existente).
8. Frontend web-teacher selector de comisiones muestra `"A-Manana"` en vez de `"A"` (visualmente verificable en demo).

### ADRs / RNs referenciadas

- ADR-016 — TareaPracticaTemplate + instancia (criterio #1, #3)
- ADR-018 / RN-130 — CII evolution longitudinal por template_id (criterio #1)
- ADR-010 / RN-026 — hashing canonico CTR (no se rompe — el seed reconstruye desde cero)
- G12 invariante (CLAUDE.md) — manifest + config alineados (criterio #2, #4)
- Modelo Comision (operacional.py:56) — nombre column (criterio #5)
