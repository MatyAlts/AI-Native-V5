# Estado del repositorio — F1 completado

F1 implementa el dominio académico completo con matriz de permisos y
aislamiento multi-tenant verificado. Sobre F0 (fundaciones) se agregan
las capas de modelos, schemas, services, repositorios, routers, migraciones
y vistas frontend mínimas.

## Entregables F1

### Modelos del dominio académico (academic-service)

11 entidades SQLAlchemy en `apps/academic-service/src/academic_service/models/`:

- **Institucionales** (`institucional.py`): `Universidad` (tenant raíz, sin RLS),
  `Facultad`, `Carrera`, `PlanEstudios`, `Materia`.
- **Operativas** (`operacional.py`): `Periodo`, `Comision`, `Inscripcion`,
  `UsuarioComision`.
- **Transversales** (`transversal.py`): `AuditLog`, `CasbinRule`.

Mixins compartidos en `base.py`:

- `TenantMixin` — agrega `tenant_id UUID NOT NULL` indexado.
- `TimestampMixin` — agrega `created_at` + `deleted_at` (soft-delete).

### Schemas Pydantic v2

En `apps/academic-service/src/academic_service/schemas/`, uno por entidad con
variantes `Create` / `Update` / `Out`:

- `universidad.py`, `carrera.py`, `materia.py`, `comision.py` (incluye `Periodo`).
- `base.py` con `BaseResponse`, `ListResponse`, `ProblemDetail` (RFC 7807).
- Validaciones: ranges, patterns, `model_validator` para reglas cruzadas
  (ej. `fecha_fin > fecha_inicio` en períodos).

### Capa de persistencia con RLS

`apps/academic-service/src/academic_service/db/session.py`:

- `tenant_session(tenant_id)` — context manager async que setea
  `SELECT set_config('app.current_tenant', :t, true)` al inicio de cada
  transacción. Toda query posterior se filtra automáticamente por RLS.
- `superadmin_session()` — sin tenant seteado; solo para superadmin.

### Autenticación y autorización

En `apps/academic-service/src/academic_service/auth/`:

- `dependencies.py` — dataclass `User` + dependency `get_current_user`
  que acepta headers `X-User-Id`, `X-Tenant-Id`, `X-User-Roles` en F1/F2
  (en F3 el api-gateway validará JWT real y agregará esos headers).
- `casbin_setup.py` — modelo RBAC-con-dominios cargado con adapter
  SQLAlchemy. `check_permission(user, resource, action)` + dependency
  factory `require_permission(resource, action)`.

### Repositorios y services

- `repositories/base.py` — `BaseRepository[ModelT]` genérico con CRUD
  (get, list con cursor, count, create, update, soft_delete).
- 9 repos específicos en `repositories/__init__.py`.
- Services con lógica de dominio:
  - `UniversidadService` — create restringido a superadmin, update solo
    sobre la propia universidad.
  - `CarreraService` — valida que `universidad.tenant == user.tenant`.
  - `MateriaService` — valida existencia de correlativas.
  - `ComisionService` — valida que período esté `abierto` antes de crear.
  - `PeriodoService`.

Todos los services escriben al `AuditLog` en la misma transacción que
la operación principal.

### Routers REST

En `apps/academic-service/src/academic_service/routes/`:

- `universidades.py` — POST, GET list (cursor pagination), GET one, PATCH.
- `carreras.py` — POST, GET list (con filtros `universidad_id`, `facultad_id`),
  GET one, PATCH, DELETE (soft).
- `materias.py` — POST, GET list (filtro `plan_id`), GET one, PATCH.
- `comisiones.py` — dos routers (periodos + comisiones) con CRUDs completos.
- Todos usan `@require_permission(resource, action)` del Casbin helper.

### Migración Alembic inicial

`apps/academic-service/alembic/versions/20260420_0001_initial_schema_with_rls.py`:

- Crea las 10 tablas del dominio con sus FKs, índices y constraints.
- Aplica `SELECT apply_tenant_rls('<tabla>')` a las 9 tablas multi-tenant
  (todas excepto `universidades` y `casbin_rules`).
- Configuración Alembic async completa (`alembic.ini`, `env.py`,
  `script.py.mako`).

### Seeds de Casbin

`apps/academic-service/src/academic_service/seeds/casbin_policies.py`:

- 65 policies cubriendo la matriz completa de 4 roles × 17 recursos × acciones.
- Idempotente (DELETE + INSERT).
- Ejecutable con `make seed-casbin`.

> **Update 2026-04-21**: el snapshot histórico de F1 fue 65 policies. Conforme se agregaron entidades en Camino 3 (Facultad/Plan delete = 79) y Opción C (TareaPractica CRUD = 92), la cuenta creció. Ver `reglas.md` RN-018 actualizada — el count específico se removió de la spec; el código fuente del seed es source of truth.

> **Update 2026-04-23 (ADR-016)**: se introduce `TareaPracticaTemplate` a nivel `(materia_id, periodo_id)` como fuente canónica opcional de TPs. Las `TareaPractica` ganan FK nullable `template_id` y flag `has_drift`; al crear un template, el sistema auto-instancia una TP en cada comisión de la materia+periodo. Editar la instancia setea `has_drift=true` pero NO toca la cadena CTR — `Episode.problema_id` sigue apuntando al UUID de la instancia (RN-013bis). Casbin sumó 14 policies para `tarea_practica_template:CRUD` (79 → 107 total). Ver ADR-016 y `reglas.md` RN-013bis.

### enrollment-service

Importación masiva de inscripciones por CSV con pandas:

- `POST /api/v1/imports` — sube CSV, valida en dry-run, devuelve errores por fila.
- `POST /api/v1/imports/{id}/commit` — aplica cambios transaccionalmente.
- Validaciones: columnas requeridas, tipos (UUID, date, enums).
- Formato documentado en `docs/imports/enrollment-csv-format.md`.

### api-gateway

`apps/api-gateway/src/api_gateway/routes/proxy.py`:

- Mapa de ruteo por prefijo de path a servicios downstream.
- httpx async client con passthrough de headers y body.
- En F3 se extenderá para validar JWT y emitir headers X-*.

### web-admin con vistas funcionales

En `apps/web-admin/src/`:

- `lib/api.ts` — cliente HTTP tipado con errores estructurados.
- `pages/UniversidadesPage.tsx` — lista + form de creación.
- `pages/CarrerasPage.tsx` — lista con nombre de universidad resuelto + form.
- `router/Router.tsx` — navegación simple (TanStack Router llega en F2).

### Tests

**Unit** (sin Docker, rápido):

- `tests/unit/test_schemas.py` — 10 tests de validación Pydantic. **10/10 ✓**.

**Integration**:

- `tests/integration/test_casbin_matrix.py` — 23 tests parametrizados de la
  matriz de permisos. **23/23 ✓**.
- `tests/integration/test_rls_isolation.py` — property tests con
  testcontainers que verifican aislamiento entre 2 tenants (SELECT/UPDATE).
- `tests/integration/test_comision_periodo_cerrado.py` — regla de negocio.

## Comandos nuevos en el Makefile

```bash
make seed-casbin           # carga las 65 policies en la base
make migrate-new SERVICE=academic-service NAME=agregar_tabla_x
```

## Cómo validar F1 localmente

```bash
# Asegurarse de tener infra levantada
make dev-bootstrap

# Aplicar migraciones
cd apps/academic-service
uv run alembic upgrade head

# Cargar policies de Casbin
make seed-casbin

# Arrancar servicios
cd ../..
make dev

# En otra terminal
curl http://localhost:8000/health/ready       # api-gateway
curl http://localhost:8002/health/ready       # academic-service

# Consumir (con headers de dev para saltar validación JWT hasta F3)
curl -X POST http://localhost:8000/api/v1/universidades \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: 10000000-0000-0000-0000-000000000001' \
  -H 'X-Tenant-Id: 00000000-0000-0000-0000-000000000000' \
  -H 'X-User-Email: superadmin@platform.ar' \
  -H 'X-User-Roles: superadmin' \
  -d '{"nombre":"Demo U","codigo":"demo","keycloak_realm":"demo_uni"}'

# Abrir el admin web
open http://localhost:5173
```

## Tests que pasan

```bash
# Correr todo lo que no requiere Docker
PYTHONPATH=apps/academic-service/src:packages/contracts/src:packages/test-utils/src \
  python3 -m pytest \
  apps/academic-service/tests/unit/ \
  apps/academic-service/tests/integration/test_casbin_matrix.py \
  packages/contracts/tests/ -v

# Resultado esperado:
#   contracts hashing:     7/7
#   academic schemas:     10/10
#   casbin matrix:        23/23
#   Total:                40/40
```

## Qué queda fuera de F1 (va en F2+)

- Vistas de `web-admin` para Materias, Comisiones, Periodos, Inscripciones
  (diseño decidido, pero el tiempo alcanzó para 2 entidades de ejemplo).
- Integration tests de los endpoints completos con Keycloak real
  (pendiente de F3 cuando el gateway valide JWTs).
- Integración con bus de eventos (ADR-005): los services emiten TODO en
  comentarios `TODO F3: publish event`.
- `evaluation-service`, `analytics-service`, `content-service`, `tutor-service`,
  `ctr-service`, `classifier-service`, `ai-gateway`, `governance-service`:
  aún en estado F0 (stub `/health`). Se desarrollan F2+ según el plan.

## Próxima fase — F2

Contenido y RAG. Principales entregables esperados:

1. `content-service` con ingesta multi-formato (PDF, Markdown, código ZIP).
2. Chunking estratificado + embeddings con multilingual-e5-large.
3. pgvector como vector store con índice IVFFlat.
4. Retrieval con filtro estricto por `comision_id` + re-ranker bge.
5. Endpoint `content_service.retrieve(query, comision_id, top_k)` listo
   para que lo use el tutor en F3.
6. `web-teacher` con gestión de materiales.
7. Golden queries para evaluación continua del retrieval.

Plan detallado: `docs/plan-detallado-fases.md` → F2.
