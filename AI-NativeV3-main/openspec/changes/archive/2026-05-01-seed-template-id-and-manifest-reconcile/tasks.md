## 1. Migracion Alembic: comisiones.nombre

- [x] 1.1 Crear `apps/academic-service/alembic/versions/20260430_0001_comision_nombre.py` con upgrade(): `add_column nullable=True` -> `UPDATE SET nombre=codigo` -> `alter_column nullable=False`. downgrade(): `drop_column nombre`.
- [x] 1.2 Verificar localmente que `make migrate` corre sin errores contra `academic_main` (postgres dev) y deja todas las filas existentes con `nombre = codigo`. (verificado: revision 20260423_0001 -> 20260430_0001 aplicada limpio)

## 2. Modelos y schemas: Comision.nombre

- [x] 2.1 En `apps/academic-service/src/academic_service/models/operacional.py` agregar `nombre: Mapped[str] = mapped_column(String(100), nullable=False)` al modelo `Comision`. Mantener todos los demas campos y constraints intactos.
- [x] 2.2 En `apps/academic-service/src/academic_service/schemas/comision.py` agregar `nombre: str = Field(min_length=1, max_length=100)` a `ComisionBase` y `nombre: str | None = None` a `ComisionUpdate`. Confirmar que `ComisionOut` lo incluye via herencia o explicito.
- [x] 2.3 Revisar `apps/academic-service/src/academic_service/services/comision_service.py` y handler `routes/comisiones.py`: si hay logica que filtra fields antes del INSERT/UPDATE, asegurar que `nombre` pase. Si usa `**data.model_dump()`, no requiere cambios.

## 3. Reescritura quirurgica de seed-3-comisiones.py

- [x] 3.1 Eliminar la constante `PROBLEMA_ID = UUID("99999999-9999-9999-9999-999999999999")` del top del archivo. Buscar todas las referencias.
- [x] 3.2 En la funcion que crea las 6 instancias de TP (3 comisiones x 2 templates), construir y retornar un dict `tp_instances_by_comision: dict[UUID, list[UUID]]` con la lista de instance_ids por comision en orden estable.
- [x] 3.3 En el loop de creacion de episodios (~lineas 700+), reemplazar `problema_id=PROBLEMA_ID` por `problema_id=tp_instances_by_comision[comision_id][ep_idx % 2]`. Mantener determinismo del `ep_idx`.
- [x] 3.4 Bumpear `PROMPT_SYSTEM_VERSION = "v1.0.0"` a `"v1.0.1"` (linea ~82).
- [x] 3.5 Recomputar `PROMPT_SYSTEM_HASH` leyendo el sha256 de `ai-native-prompts/prompts/tutor/v1.0.1/manifest.yaml` (campo `sha256` o equivalente). Hardcodear el nuevo valor en la constante.
- [x] 3.6 En el INSERT de comisiones (lineas ~482-496) agregar `"nombre"` con valores `"A-Manana"`, `"B-Tarde"`, `"C-Noche"` correspondiendo a codigos `"A"`, `"B"`, `"C"`.
- [x] 3.7 Actualizar el docstring del seed: documentar que es destructivo para tenant `aaaa...`, que requiere migracion `20260430_0001` aplicada, y que recomputa hashes desde cero.

## 4. Tests

- [x] 4.1 Si existe `apps/academic-service/tests/unit/test_comision_routes.py` o similar, agregar test que verifique: (a) POST con `nombre` valido lo persiste; (b) POST con `nombre=""` devuelve 422; (c) GET devuelve `nombre` no-null; (d) PATCH actualiza solo `nombre` sin tocar `codigo`.
- [x] 4.2 Si no existe test del comision service, crear `test_comision_service_nombre.py` minimo cubriendo los 4 casos de arriba.
- [x] 4.3 Verificar que tests existentes que crean Comisiones via factory/fixture no rompen — agregar `nombre` al fixture si fuese necesario.

## 5. Verificacion E2E del piloto

- [x] 5.1 `make migrate` aplica revision 20260430_0001 sin errores.
- [x] 5.2 `seed-3-comisiones.py` corre limpio: 3 comisiones, 18 estudiantes, 94 episodios, 94 classifications.
- [x] 5.3 Criterio #3: 6 distinct `problema_id` UUIDs en episodes (`11110000-0000-000{0,1,2}-...`) — el legacy `99999999-...` NO aparece.
- [x] 5.4 Criterio #2: `SELECT DISTINCT prompt_system_version FROM events` devuelve solo `v1.0.1`.
- [x] 5.5 Criterio #5: GET `/api/v1/comisiones` via api-gateway devuelve `[{codigo:"A",nombre:"A-Manana"}, {codigo:"B",nombre:"B-Tarde"}, {codigo:"C",nombre:"C-Noche"}]`.
- [x] 5.6 Criterio #1: GET cii-evolution-longitudinal devuelve `n_groups_evaluated: 2`, ambos templates con `insufficient_data: false` y slope computado. **Bug pre-existente destapado**: `analytics-service/routes/analytics.py:506` declaraba `template_id: str` pero recibe UUID. Fix in-scope: `template_id: UUID` (pydantic serializa UUID como str en JSON, sin contract change).
- [x] 5.7 Criterio #4: GET `/api/v1/active_configs` devuelve `{"active":{"default":{"tutor":"v1.0.1","classifier":"v1.0.0"}}}`.

## 6. Quality gates

- [x] 6.1 `make lint` pasa sin errores nuevos. (verificado: 0 errores en archivos tocados por la epic; 9 errores pre-existentes en `apps/tutor-service/tests/unit/test_config_prompt_version.py` y `scripts/g8a-sensitivity-analysis.py` ajenos al scope)
- [x] 6.2 `make typecheck` pasa sin errores nuevos. (verificado: 0 errores en `apps/academic-service/`; 12 errores mypy en `scripts/seed-3-comisiones.py` todos pre-existentes — HEAD tenía 14, nuestros cambios redujeron a 12)
- [x] 6.3 `pytest apps/academic-service/tests/` pasa con la suite ampliada: **155 passed** (incluye los nuevos `test_comision_nombre.py` y los ajustes a `test_schemas.py` + `test_comision_periodo_cerrado.py`).
- [x] 6.4 `make check-rls` pasa: `[OK] Todas las tablas con tenant_id tienen policy RLS + FORCE` (no agregamos tablas, solo columna).
- [x] 6.5 Frontend `web-teacher` smoke check visual: el `ComisionSelector` muestra `"A-Manana"`, `"B-Tarde"`, `"C-Noche"` ✅ (verificado por el usuario contra `localhost:5174` con servicios + Vite arriba el 2026-05-01).
