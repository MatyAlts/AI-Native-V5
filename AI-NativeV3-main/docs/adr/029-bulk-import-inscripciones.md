# ADR-029 — Bulk import de `inscripciones` centralizado en academic-service

- **Estado**: Aceptado
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: backend, academic-service, bulk-import, piloto-ready
- **Cierra**: B.1 de la auditoría de coherencia backend ↔ frontend (2026-04-29).
- **Coordinado con**: ADR-030 (deprecación de `enrollment-service`).

## Contexto y problema

El piloto UNSL requiere inscribir entre 50 y 200 estudiantes por cuatrimestre. El estado pre-iter-2 era:

- **No había endpoint individual** para crear inscripciones (`POST /api/v1/inscripciones`). El docstring de [`comisiones.py:117-118`](../../apps/academic-service/src/academic_service/routes/comisiones.py#L117-L118) referenciaba ese endpoint pero **no existía** — vaporware documental.
- **`bulk-import` de academic-service NO incluía `inscripciones`** en `SUPPORTED_ENTITIES` ([`bulk_import.py:62-70`](../../apps/academic-service/src/academic_service/services/bulk_import.py#L62-L70)). Soportaba 7 entidades: facultades, carreras, planes, materias, periodos, comisiones, tareas_practicas.
- **`enrollment-service` tenía endpoints de import** ([`POST /api/v1/imports`](../../apps/enrollment-service/src/enrollment_service/routes/imports.py)) pero ningún frontend los consumía y el commit tenía un TODO sin resolver: *"commit (TODO: integrate academic-service)"*.

Consecuencia operativa: **el piloto sólo podía cargar inscripciones via SQL manual o seed scripts** (`scripts/seed-3-comisiones.py`). Para uso real con UNSL sin DBA dedicado, esto era bloqueante.

## Drivers de la decisión

- **Camino más corto al piloto-ready**: el bulk-import de academic-service ya tiene infrastructura completa (parser CSV con UTF-8 BOM, dry-run + commit atómico, validación FK, audit log RN-016, mapping Casbin). Sumar `inscripciones` es una entrada en un registry, no infra nueva.
- **Coherencia arquitectónica**: las inscripciones son parte del dominio académico (`inscripciones` vive en `academic_main`), no parte de ingest/federación. Centralizarlas en academic-service alinea el código con su diseño semántico.
- **Eliminar duplicación**: tener dos endpoints (academic bulk + enrollment imports) que hacen import de CSV es deuda silenciosa. Los frontends no sabían cuál llamar; la implementación de `enrollment-service` quedó incompleta.
- **Consentimiento ético**: la identidad real del estudiante vive en Keycloak (federación LDAP). El CSV asume que `student_pseudonym` ya viene resuelto desde la capa de federación. Este ADR NO crea identidades — sólo registra la pertenencia a comisiones. Compatible con el principio de privacidad de `packages/platform-ops/privacy.py`.

## Opciones consideradas

### A — sumar `inscripciones` a `bulk-import` de academic-service (ELEGIDA)

Centralizar todo el bulk en un solo servicio. `enrollment-service` se deprecará por separado en [ADR-030](./030-deprecate-enrollment-service.md).

**LOC efectivo**: 1 schema (`InscripcionCreate`), 1 service (`InscripcionService`), 4 LOC en `bulk_import.py` + 1 LOC en `routes/bulk.py` + 7 tests + 1 LOC en UI web-admin.

### B — completar `enrollment-service` y mantener separación

Implementar el commit pendiente de [`imports.py:70`](../../apps/enrollment-service/src/enrollment_service/routes/imports.py#L70) para que persista a través de `academic-service`. Frontend consume `enrollment-service`.

**Descartada porque**: introduce una dependencia HTTP service-to-service entre `enrollment-service` y `academic-service` (latencia + flakiness + transaccionalidad cross-service). Y el `enrollment-service` no tiene casos de uso adicionales más allá del import CSV — su existencia separada no se justifica funcionalmente.

### C — crear endpoint REST individual `POST /api/v1/inscripciones`

Útil pero **no resuelve el caso de carga inicial masiva** (50-200 estudiantes). Sería UI individual estudiante por estudiante. Queda como agenda futura para el caso de inscripciones tardías mid-cuatrimestre.

## Decisión

**Opción A**. Centralizar bulk import de inscripciones en `academic-service`.

### Cambios concretos

| Archivo | Cambio |
|---|---|
| [`apps/academic-service/src/academic_service/schemas/inscripcion.py`](../../apps/academic-service/src/academic_service/schemas/inscripcion.py) | Nuevo. `InscripcionCreate` + `InscripcionOut` con `Literal` para `rol` y `estado`. |
| [`apps/academic-service/src/academic_service/services/inscripcion_service.py`](../../apps/academic-service/src/academic_service/services/inscripcion_service.py) | Nuevo. `InscripcionService.create()` con audit log + manejo de `IntegrityError` (constraint `uq_inscripcion_student`) → 409. |
| [`apps/academic-service/src/academic_service/services/bulk_import.py`](../../apps/academic-service/src/academic_service/services/bulk_import.py) | `inscripciones` agregado a `SUPPORTED_ENTITIES`, `_entity_registry()`, y `_check_fk_existence` (valida `comision_id` contra el tenant del caller). |
| [`apps/academic-service/src/academic_service/routes/bulk.py`](../../apps/academic-service/src/academic_service/routes/bulk.py) | `_RESOURCE_BY_ENTITY["inscripciones"] = "inscripcion"` (mapping Casbin). |
| [`apps/academic-service/src/academic_service/schemas/__init__.py`](../../apps/academic-service/src/academic_service/schemas/__init__.py) | Re-export de `InscripcionCreate` y `InscripcionOut`. |
| [`apps/web-admin/src/pages/BulkImportPage.tsx`](../../apps/web-admin/src/pages/BulkImportPage.tsx) | Entity nueva `"inscripciones"` con required + optional columns documentadas. |

### Casbin policies

**Sin cambios**. Las policies para `inscripcion` (create/read/update) ya existían pre-ADR-029 ([`casbin_policies.py:61-62, 104-105`](../../apps/academic-service/src/academic_service/seeds/casbin_policies.py#L61-L62)) — eran policies dormidas porque no había endpoint que las consumiera. Ahora el bulk las activa.

### Schema CSV de `inscripciones`

| Columna | Requerida | Tipo | Notas |
|---|---|---|---|
| `comision_id` | ✅ | UUID | Debe existir en el tenant del caller. |
| `student_pseudonym` | ✅ | UUID | Pre-derivado por federación LDAP / enrollment. NO se valida contra Keycloak. |
| `fecha_inscripcion` | ✅ | ISO date | Ej. `2026-03-15`. |
| `rol` | ❌ | Literal | `regular` (default) / `oyente` / `reinscripcion`. |
| `estado` | ❌ | Literal | `activa` (default) / `cursando` / `aprobado` / `desaprobado` / `abandono`. |
| `nota_final` | ❌ | Decimal[0,10] | Sólo para episodios cerrados. |
| `fecha_cierre` | ❌ | ISO date | Sólo para episodios cerrados. |

## Consecuencias

### Positivas

- **Cierra el gap B.1**: el piloto puede cargar inscripciones masivas via UI web-admin sin tocar SQL.
- **Coherencia arquitectónica**: todo el bulk del dominio académico vive en un solo servicio. Casbin policies que estaban dormidas se activan.
- **Transaccionalidad cross-row preservada**: el commit es atómico — si UNA fila falla validación, NINGUNA se persiste (mismo patrón ADR-anterior del bulk).
- **Audit trail completo**: cada inscripción confirmada genera un `AuditLog` con `action="inscripcion.create"` (RN-016).

### Negativas / trade-offs

- **`enrollment-service` queda redundante**: documentado en [ADR-030](./030-deprecate-enrollment-service.md). El servicio se elimina del workspace en el mismo commit que este ADR.
- **`student_pseudonym` no se valida contra Keycloak**: el CSV asume que el doctorando o el operador del piloto resolvió la federación previamente. Si se sube un pseudónimo huérfano (sin contraparte en Keycloak), la inscripción se crea pero el estudiante no podrá loguear. **Mitigación**: agendar reconciliation job que reporta inscripciones huérfanas (post-piloto-1).
- **Constraint de unicidad agresivo**: `uq_inscripcion_student(tenant_id, comision_id, student_pseudonym)` — la segunda inscripción del mismo estudiante en la misma comisión falla con 409. Re-inscripciones legítimas en períodos distintos van en filas separadas.

### Neutras

- El campo `student_pseudonym` es UUID opaco — no expone identidad real del estudiante (RN-090).
- El `rol="reinscripcion"` queda disponible para casos legítimos de re-cursar; el constraint sólo restringe duplicados exactos.

## Tests cubriendo el ADR

`apps/academic-service/tests/integration/test_bulk_import.py` — 7 tests nuevos al final del archivo:

1. `test_bulk_import_inscripciones_dry_run_happy_path` — 3 inscripciones válidas, dry_run reporta 3/3.
2. `test_bulk_import_inscripciones_dry_run_rol_invalido` — rol fuera del Literal → error con `column="rol"`.
3. `test_bulk_import_inscripciones_dry_run_comision_inexistente` — FK error detectado en `_check_fk_existence`.
4. `test_bulk_import_inscripciones_commit_happy_path` — 2 inscripciones → 2 audit logs + 2 InscripcionRepository.create() con tenant_id correcto.
5. `test_bulk_import_inscripciones_commit_rolls_back_on_fk_error` — 1 válida + 1 con comision_id bogus → 422 + ningún create + ningún audit (rollback total).
6. `test_bulk_import_inscripciones_en_supported_entities` — sanity check de registro completo.
7. `test_bulk_import_inscripciones_resource_mapping_casbin` — verifica `_RESOURCE_BY_ENTITY["inscripciones"] = "inscripcion"`.

**Total**: 7 tests, todos PASS contra el patch del repo (verificado 2026-04-29).

## Referencias

- Auditoría de coherencia backend ↔ frontend (2026-04-29) — gap B.1.
- ADR-030 — deprecación de enrollment-service (coordinado).
- RN-016 — audit log obligatorio para mutaciones del dominio académico.
- RN-090 — `student_pseudonym` es UUID opaco; identidad real vive en Keycloak.
- `packages/platform-ops/privacy.py` — política de pseudonimización.
