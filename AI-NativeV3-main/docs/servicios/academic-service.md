# academic-service

## 1. Qué hace (una frase)

Es el CRUD autoritativo del dominio académico: gestiona la jerarquía Universidad → Facultad → Carrera → Plan → Materia → Período → Comisión y las entidades operativas asociadas (`Inscripcion`, `UsuarioComision`, `TareaPractica`, `TareaPracticaTemplate`, `Unidad`), con matriz de permisos Casbin RBAC-con-dominios, multi-tenancy via RLS, bulk-import centralizado ([ADR-029](../adr/029-bulk-import-centralized.md)) y generación asistida de TPs por IA ([ADR-036](../adr/036-tp-gen-ia.md)).

## 2. Rol en la arquitectura

Pertenece al **plano académico-operacional**. Materializa el componente "Servicio de dominio académico" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: mantener el árbol institucional del tenant, sostener la identidad de cursado (qué estudiante está en qué comisión), y ser la fuente de verdad para la entidad `TareaPractica` que todo episodio CTR referencia via `problema_id`.

## 3. Responsabilidades

- Exponer CRUDs REST sobre 10 entidades: universidades, facultades, carreras, planes, materias, periodos, comisiones, inscripciones, usuarios_comision, **unidades** (epic `unidades-trazabilidad`).
- Persistir la entidad central del piloto, `TareaPractica`, con versionado inmutable (publicar congela la fila, nueva versión clona con `parent_tarea_id` apuntando a la predecesora). Soporta `test_cases JSONB` ([ADR-034](../adr/034-test-cases-tp.md)) y flag `created_via_ai bool` ([ADR-036](../adr/036-tp-gen-ia.md)).
- Implementar [ADR-016](../adr/016-tp-template-instance.md): `TareaPracticaTemplate` como fuente canónica por `(materia_id, periodo_id)` + auto-instanciación de una `TareaPractica` por cada comisión de la cátedra + flag `has_drift` cuando una instancia diverge del template.
- **Generar TPs con IA** (epic `ai-native-completion-and-byok`, [ADR-036](../adr/036-tp-gen-ia.md)): `POST /api/v1/tareas-practicas/generate` resuelve el prompt `tp_generator/v1.0.0` desde governance-service, llama al ai-gateway con `feature="tp_generator"` + `materia_id` (para resolver BYOK), y emite audit log structlog `tp_generated_by_ai` con tenant/user/materia/prompt_version/tokens/latency/provider.
- Soportar **bulk-import centralizado** ([ADR-029](../adr/029-bulk-import-centralized.md)): toda nueva entidad para bulk-import va a `SUPPORTED_ENTITIES` de `services/bulk_import.py` (incluye `inscripciones` desde gap B.1) — el viejo `enrollment-service` quedó deprecado por [ADR-030](../adr/030-deprecate-enrollment-service.md).
- Enforcar permisos Casbin RBAC-con-dominios (ADR-008): el `dom` es el `tenant_id`, el `obj` es `recurso:*` o `recurso:{id}`. Seed idempotente en `seeds/casbin_policies.py` carga **131 policies** del catálogo actual en `casbin_rules` (verificado 2026-05-07; +14 por templates ADR-016, +1 `facultad:read` para docente, +8 `byok_key:CRUD` ADR-039, +7 `unidad:CRUD/read`).
- Validar integridad del árbol: `carrera.facultad_id` coincide con `carrera.universidad_id`, `comision.codigo` único por `(materia_id, periodo_id)`, `comision` no puede crearse en `Periodo.estado = "cerrado"` (RN verificada por `test_comision_periodo_cerrado.py`).
- Exponer `GET /api/v1/comisiones/mis` que el web-teacher y el web-admin usan para listar "mis comisiones" (los docentes via JOIN a `usuarios_comision`).
- Registrar `AuditLog` en la misma transacción que la operación principal (rollback solidario).
- Exponer `POST /api/v1/bulk` para import masivo via CSV/JSON (usado en onboarding UNSL y para carga de padrones e inscripciones).

## 4. Qué NO hace (anti-responsabilidades)

- **NO persiste identidad personal de usuarios**: los `user_id` son UUIDs opacos desde Keycloak; el `student_pseudonym` es opaco por construcción. La identidad real vive en Keycloak. Auth/JWT lo resuelve [api-gateway](./api-gateway.md) + Casbin descentralizado en cada servicio (el viejo `identity-service` quedó deprecado por [ADR-041](../adr/041-deprecate-identity-service.md)). La des-identificación la implementa `packages/platform-ops/privacy.py`.
- **NO procesa inscripciones masivas en otro servicio**: el bulk-import de inscripciones (gap B.1) está centralizado **acá** desde [ADR-029](../adr/029-bulk-import-centralized.md). El `enrollment-service` original quedó deprecado por [ADR-030](../adr/030-deprecate-enrollment-service.md) (preservado en disco con README de deprecation).
- **NO conoce el CTR ni los eventos**: el `problema_id` del `Episode` apunta a una `TareaPractica` que vive acá, pero esta tabla no tiene FK al CTR (bases lógicas separadas, ADR-003). La referencia es por UUID sin integridad referencial cruzada.
- **NO clasifica ni evalúa entregas**: las `rubricas` están persistidas como JSONB en `TareaPractica`, pero este servicio no las aplica. Las **entregas** y **calificaciones** viven en [evaluation-service](./evaluation-service.md) (que comparte DB `academic_main` con un engine independiente).
- **NO hace JOINs contra `ctr_store`, `classifier_db` ni `content_db`**: ADR-003. Para estadísticas cross-base ver [analytics-service](./analytics-service.md).
- **NO valida reglas semánticas del prompt TP-gen IA**: el endpoint `/generate` enforce restricciones sintácticas declaradas en el prompt (`tp_generator/v1.0.0` de governance-service); las semánticas (ej. "no usar funciones en dificultad básica") son responsabilidad del docente al revisar la TP generada antes de publicar.

## 5. Endpoints HTTP

12 routers (no listo los 70+ endpoints uno a uno; agrupo por recurso):

| Prefijo | Endpoints típicos | Permiso Casbin |
|---|---|---|
| `/api/v1/universidades` | `POST / GET / GET/{id} / PATCH / DELETE` | `universidad:*` |
| `/api/v1/facultades` | CRUD completo | `facultad:*` |
| `/api/v1/carreras` | CRUD completo | `carrera:*` |
| `/api/v1/planes` | CRUD completo + materias anidadas | `plan:*` |
| `/api/v1/materias` | CRUD completo | `materia:*` |
| `/api/v1/periodos` | CRUD + transición `abierto`/`cerrado` | `periodo:*` |
| `/api/v1/comisiones` | CRUD + `GET /mis` (comisiones del user docente) + `GET /{id}/inscripciones` | `comision:*` |
| `/api/v1/unidades` | CRUD por comisión (epic `unidades-trazabilidad`) | `unidad:CRUD`, `unidad:read` |
| `/api/v1/tareas-practicas` | CRUD + `/{id}/publish` + `/{id}/archive` + `/{id}/new-version` + `/{id}/versions` + `GET /{id}/test-cases?include_hidden=...` ([ADR-034](../adr/034-test-cases-tp.md)) + `POST /generate` (TP-gen IA, [ADR-036](../adr/036-tp-gen-ia.md)) | `tarea_practica:*` |
| `/api/v1/tareas-practicas-templates` | CRUD + publish/archive/new-version + `/{id}/instances` + `/{id}/versions` + test_cases JSONB | `tarea_practica_template:*` |
| `/api/v1/bulk` | `POST` para import masivo (entidades en `SUPPORTED_ENTITIES` incluyen inscripciones, comisiones, materias, etc.) | `bulk_import:create` |
| `/health`, `/health/ready`, `/health/live` | Health real con `check_postgres` (epic `real-health-checks`) | Ninguna |

Todos los endpoints exigen `X-Tenant-Id` + `X-User-Id` + `X-User-Roles` inyectados por [api-gateway](./api-gateway.md) (o por los Vite proxies en `dev_trust_headers=True`).

**Test-cases endpoint con filtro por rol** ([ADR-034](../adr/034-test-cases-tp.md)): `GET /tareas-practicas/{id}/test-cases?include_hidden=true` con role `estudiante` devuelve **403** — los hidden tests (`is_public=false`) son sólo visibles a docentes/superadmin. Cada test = `{id, name, type, code, expected, is_public, weight}`.

**TP-gen IA** ([ADR-036](../adr/036-tp-gen-ia.md)): el endpoint `/generate` recibe un payload con `materia_id`, `unidad_id?`, `dificultad`, `enunciado_brief`. Resuelve el prompt `tp_generator/v1.0.0` desde `governance-service`, llama a `ai-gateway` con `feature="tp_generator"` + `materia_id` (para resolver BYOK jerárquico), persiste la TP con `created_via_ai=true`, y emite `tp_generated_by_ai` a structlog con `tenant/user/materia/prompt_version/tokens/latency/provider`. **Bug histórico cerrado en commit c8a4685**: el campo `created_via_ai` se persistía siempre `false` por bug en `services/tarea_practica_service.py:94` (el dict pasado a `repo.create()` no incluía el campo) — fix de 1 línea. Trazabilidad ADR-036 ahora íntegra. UI wizard en web-teacher DEFERIDO.

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL — base lógica `academic_main`. Usuario `academic_user`.

**Depende de (otros servicios):** ninguno en runtime — es **hoja** del punto de vista HTTP. La autorización Casbin se resuelve in-process (adapter SQLAlchemy sobre la misma DB).

**Depende de (otros servicios) para TP-gen IA**:
- [governance-service](./governance-service.md) — resolver el prompt `tp_generator/v1.0.0` antes de cada `/generate`.
- [ai-gateway](./ai-gateway.md) — llamar al LLM con `feature="tp_generator"` + `materia_id` para resolver BYOK.

**Dependen de él:**
- [tutor-service](./tutor-service.md) — `GET /api/v1/tareas-practicas/{id}` para los 6 chequeos de validación antes del `episodio_abierto`.
- [evaluation-service](./evaluation-service.md) — comparte la base `academic_main` vía un engine independiente; persiste entregas y calificaciones contra TPs gestionadas acá.
- [analytics-service](./analytics-service.md) — lee `academic_main` (read-only) para resolver `comision.materia_id` / `comision.periodo_id` / `template_id` al agregar clasificaciones.
- [web-admin](./web-admin.md) — consumidor principal (10+ páginas de gestión, incluyendo `BulkImportPage` con entidad `inscripciones` y CRUD de `Unidad`).
- [web-teacher](./web-teacher.md) — vistas "Plantillas" (templates), "Trabajos Prácticos" (instancias), "Materiales" (via content-service pero linkeado por `comision_id`).
- [web-student](./web-student.md) — `GET /api/v1/comisiones/mis` + `GET /tareas-practicas?comision_id=...`.

## 7. Modelo de datos

Base lógica: **`academic_main`** (ADR-003). Usuario `academic_user`. Migraciones en `apps/academic-service/alembic/versions/`.

**Jerarquía institucional** (`models/institucional.py`):
- `universidades` — raíz del tenant. **Única tabla SIN `tenant_id`** (ella ES el tenant). `keycloak_realm` único — mapeo 1:1 universidad ↔ realm Keycloak. No lleva policy RLS.
- `facultades` — opcional. FK a `universidades`. Unique `(tenant_id, codigo)`.
- `carreras` — FK a `universidades` + `facultades`. Migración `20260422_0001` hace `facultad_id` NOT NULL.
- `planes_estudios` — versionado de planes. FK a `carreras`.
- `materias` — asignaturas. FK a `planes_estudios`.

**Jerarquía operativa** (`models/operacional.py`):
- `periodos` — ej. "2026-S1". Estado `abierto|cerrado`. Unique `(tenant_id, codigo)`.
- `comisiones` — **unidad operativa central** (docentes + estudiantes + material + tutor + CTR viven al nivel de comisión). FK a `materias` + `periodos`. `curso_config_hash` (64 chars) — hash de la configuración AI-Native (prompt + profile + classifier_config) que se embede en cada evento CTR. `ai_budget_monthly_usd` por comisión.
- `unidades` (epic `unidades-trazabilidad`) — agrupación pedagógica scoped a `comision_id`. Permite trazabilidad longitudinal cuando `template_id=NULL` (TP huérfana sin template a nivel materia+periodo): el slope longitudinal puede agruparse por `unidad_id` en vez de `template_id`. Modelo en `models/operacional.py::Unidad` con campos `id, tenant_id, comision_id, codigo, titulo, orden, descripcion`. CRUD endpoints `/api/v1/unidades`. Casbin: `unidad:CRUD` para superadmin/docente_admin/docente, `unidad:read` para estudiante.
- `inscripciones` — estudiante (`student_pseudonym`) ↔ comisión. Estado `activa|cursando|aprobado|desaprobado|abandono`. Unique `(tenant_id, comision_id, student_pseudonym)`. Bulk-import desde [ADR-029](../adr/029-bulk-import-centralized.md).
- `usuarios_comision` — asignación de docente/adjunto/JTP/ayudante/corrector a comisión. Separada de `inscripciones` porque un mismo user puede ser docente en una y estudiante en otra.
- `tareas_practicas` — el TP asignado. Versionado inmutable: `UniqueConstraint(tenant_id, comision_id, codigo, version)`, `parent_tarea_id` FK self con `ondelete=RESTRICT`. CHECK constraints: `estado IN ('draft','published','archived')`, `peso BETWEEN 0 AND 1`, `version >= 1`, `has_drift=false OR template_id IS NOT NULL`. **Columnas nuevas (epic ai-native-completion)**:
  - `test_cases JSONB` ([ADR-034](../adr/034-test-cases-tp.md)): array de `{id, name, type, code, expected, is_public, weight}`.
  - `created_via_ai BOOLEAN` ([ADR-036](../adr/036-tp-gen-ia.md)): true si la TP fue generada por el endpoint `/generate`.
  - `unidad_id UUID NULL` (epic `unidades-trazabilidad`): FK opcional a `unidades` para trazabilidad longitudinal cuando `template_id=NULL`. **Filtro pendiente**: `GET /tareas-practicas?unidad_id=X` no filtra hoy (deuda QA pass 2026-05-07).
- `tareas_practicas_templates` (ADR-016) — fuente canónica por `(materia_id, periodo_id)`. Mismas reglas de versionado que `tareas_practicas`. Relación `instances` hacia `TareaPractica.template_id`. También tiene `test_cases JSONB` (ADR-034).

**Transversales** (`models/transversal.py`):
- `audit_log` — append-only. Escrito en la misma transacción que la operación. Columns: `user_id`, `action` (`comision.create`, etc.), `resource_type`, `resource_id`, `changes` JSONB `{"before": ..., "after": ...}`, `request_id`, `ip_address` (INET).
- `casbin_rules` — gestionada por `casbin_sqlalchemy_adapter`. Schema estándar de Casbin (`ptype`, `v0..v5`).

**RLS**: todas las tablas con `tenant_id` tienen policy `tenant_isolation` usando `current_setting('app.current_tenant')::uuid = tenant_id`. `universidades` NO la tiene (es el tenant). Migración `20260420_0001_initial_schema_with_rls.py`. Verificable con `make check-rls`.

## 8. Archivos clave para entender el servicio

- `apps/academic-service/src/academic_service/models/institucional.py` — jerarquía universidad → facultad → carrera → plan → materia.
- `apps/academic-service/src/academic_service/models/operacional.py` — periodo → comisión → inscripción/usuario_comision + TareaPractica + TareaPracticaTemplate (ADR-016).
- `apps/academic-service/src/academic_service/models/transversal.py` — AuditLog + casbin_rules.
- `apps/academic-service/src/academic_service/auth/casbin_setup.py` — modelo Casbin (sub/dom/obj/act). La función `require_permission(resource, action)` es la dependencia FastAPI estándar en los routes.
- `apps/academic-service/src/academic_service/auth/casbin_model.conf` — definición del modelo Casbin (RBAC-con-dominios, ver [ADR-008](../adr/008-casbin-autorizacion.md)).
- `apps/academic-service/src/academic_service/seeds/casbin_policies.py` — fuente de verdad de las **131 policies** (verificado 2026-05-07). Idempotente (DELETE + INSERT en una transacción). Cualquier cambio se refleja tras correr `make seed-casbin`.
- `apps/academic-service/src/academic_service/services/tarea_practica_template_service.py` — implementación de la auto-instanciación del template en todas las comisiones de la cátedra (ADR-016).
- `apps/academic-service/src/academic_service/services/tarea_practica_service.py` — service layer del CRUD de TPs. **Bug fixed en commit c8a4685**: `created_via_ai` se persistía siempre `false` (ADR-036) — fix de 1 línea.
- `apps/academic-service/src/academic_service/services/bulk_import.py` — `SUPPORTED_ENTITIES` con la lista de entidades bulk-importables (incluye `inscripciones` desde ADR-029).
- `apps/academic-service/src/academic_service/services/unidad_service.py` — service layer de `Unidad`.
- `apps/academic-service/src/academic_service/routes/tareas_practicas.py` + `tareas_practicas_templates.py` — los endpoints más densos del servicio (publish, archive, new-version, versions, instances, test-cases, generate).
- `apps/academic-service/src/academic_service/routes/unidades.py` — CRUD de `Unidad` por comisión.
- `apps/academic-service/src/academic_service/routes/bulk.py` — import CSV/JSON masivo.
- `apps/academic-service/tests/integration/test_casbin_matrix.py` — suite que ejercita los 4 roles principales sobre el catálogo completo de recursos.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/academic-service/src/academic_service/config.py`):

- `ACADEMIC_DB_URL` — default `postgresql+asyncpg://academic_user:academic_pass@127.0.0.1:5432/academic_main`.
- `KEYCLOAK_URL`, `KEYCLOAK_REALM` — para resolver roles del JWT en prod (en dev con `dev_trust_headers=True` no se usa).

**Puerto de desarrollo**: `8002`.

**Gotchas específicos**:

- **`universidades` sin `tenant_id`**: es la **única** excepción al principio "toda tabla tiene `tenant_id` con RLS". Ella ES el tenant — el `tenant_id` en el resto del sistema es `universidades.id`. Documentado en RN-005 y verificado por `check-rls.py` con allowlist explícito. No replicar la excepción.
- **Comisión selector vacío para estudiantes reales** (documentado en CLAUDE.md "Brechas conocidas"): `GET /comisiones/mis` hace JOIN a `usuarios_comision` — tabla para docentes/JTP/auxiliares. Los estudiantes viven en `inscripciones` con `student_pseudonym`. El endpoint actual devuelve `[]` para un estudiante. F9 prevé que Keycloak traiga `comisiones_activas` como claim del JWT para destrabar (plan en `docs/plan-b2-jwt-comisiones-activas.md`).
- **Seed Casbin desactualiza enforcer en memoria**: `make seed-casbin` corrido **después** de arrancar un servicio Python no refresca el enforcer cacheado en memoria. `--reload` de uvicorn tampoco — no detecta el cambio en DB. Hay que **matar y relanzar** el servicio para tomar las policies nuevas. Documentado en CLAUDE.md.
- **`has_drift=true` requiere `template_id IS NOT NULL`** (CHECK constraint): una instancia sin template nunca puede estar "drifteada" — el concepto no aplica. El service layer lo valida antes de llegar al CHECK, pero el constraint es el último gate.
- **Versionado inmutable**: publicar un TP lo vuelve no-editable via `PATCH`. Para cambios post-publish hay que usar `POST /{id}/new-version` que clona y linkea por `parent_tarea_id`. Misma regla para templates. Cualquier PR que permita editar campos canónicos post-publish rompe la integridad del `curso_config_hash` congelado en los episodios CTR.
- **TP-gen IA y prompt drift**: el prompt `tp_generator/v1.0.0` declara restricciones sintácticas que Mistral respeta (resolver BYOK), pero las semánticas (ej. "no usar funciones para dificultad básica") las rompe ocasionalmente. La revisión humana del docente antes de publicar la TP es la última línea de defensa.
- **`IntegrityError` handler global**: `main.py` captura `IntegrityError` y lo traduce a 409 con detalle "Ya existe un registro con esos datos únicos" o "Conflicto de integridad de datos". Los route handlers no tienen que manejar unique violations manualmente.
- **`AuditLog` dentro de la misma transacción**: operaciones que necesiten auditoría escriben la fila de `audit_log` antes del commit final. Si la operación principal rolbackea, el audit también — **por diseño**. No hay audit de operaciones fallidas.
- **`alembic/env.py` apunta hardcoded a `academic_user`** que NO es owner de las tablas en piloto local (las tablas son owned by `postgres`). `make migrate` falla siempre con permission denied. Workaround verificado 2026-05-04: `ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main uv run alembic -c apps/academic-service/alembic.ini upgrade head`. Pendiente PR aparte.
- **`comision/{id}/inscripciones` leak de pseudónimos a estudiantes** (deuda QA 2026-05-07): Casbin permite, handler debería filtrar a `WHERE student_pseudonym = user.id`. No bloqueante para v1.0 pero queda en backlog.

## 10. Relación con la tesis doctoral

El academic-service **no implementa componentes centrales del modelo N4**. Su rol es servir de **columna vertebral estructural** que hace operables al resto: el CTR sin `TareaPractica` no sabe a qué `problema_id` apuntar; el classifier sin `comision_id` no puede agregar por cohorte; el tutor sin validación de "TP publicada + dentro de ventana + comisión correcta" permitiría episodios sobre trabajos inexistentes o archivados.

Tres afirmaciones de la tesis que este servicio sostiene operativamente:

1. **Aislamiento multi-tenant** (Capítulo 7): el `tenant_id` RLS en 10 tablas es el gate que evita que una universidad vea datos de otra. La excepción `universidades` es consciente — la tabla raíz no puede auto-referenciarse.
2. **Trazabilidad del contexto de cursado** (Capítulo 6): `curso_config_hash` en `Comision` es el hash que el evento `episodio_abierto` del CTR embebe. Permite, meses después, recuperar la configuración exacta del curso (prompt + profile + classifier_config) que corresponde a un episodio.
3. **TareaPractica como unidad de análisis pedagógico** (Capítulo 5): los dashboards de progresión y distribución N4 se agregan por TP. El versionado inmutable garantiza que una clasificación sobre la TP v1 no se "corrompa" si se edita a v2 — son entidades distintas con `parent_tarea_id` trazable.

[ADR-016](../adr/016-tp-template-instance.md) documenta formalmente la introducción de `TareaPracticaTemplate`. La razón operativa: una cátedra con 3 comisiones (A-Mañana, B-Tarde, C-Noche) antes tenía que editar 3 TPs idénticos manualmente. Con el template, edita una vez y el fan-out es automático (salvo instancias que ya driftearon, que quedan excluidas del re-sync).

## 11. Estado de madurez

**Tests** (13 archivos — el servicio más testeado del monorepo: 1 unit + 11 integration + health):
- `tests/unit/test_schemas.py` — 10 tests de validación Pydantic (RN-030).
- `tests/integration/test_casbin_matrix.py` — **matriz completa** de permisos sobre los 4 roles × catálogo de recursos.
- `tests/integration/test_rls_isolation.py` — aislamiento multi-tenant contra Postgres real (requiere `ACADEMIC_DB_URL_FOR_RLS_TESTS`).
- `tests/integration/test_comision_periodo_cerrado.py` — invariante "no se crea comisión en período cerrado".
- `tests/integration/test_tareas_practicas_crud.py` + `test_planes_crud.py` + `test_periodos_crud.py` + `test_facultades_crud.py` — CRUDs completos.
- `tests/integration/test_tareas_practicas_templates_crud.py` — drift, fan-out, matriz Casbin del template.
- `tests/integration/test_bulk_import.py` — import masivo.
- `tests/integration/test_soft_delete.py` — soft-delete.
- `tests/integration/test_mis_comisiones.py` — el endpoint `GET /comisiones/mis` (con el gap conocido).

**Known gaps**:
- `GET /comisiones/mis` devuelve `[]` para estudiantes reales (gap F9 documentado arriba; plan `docs/plan-b2-jwt-comisiones-activas.md`).
- Audit log sin endpoint queryable — hoy se consulta directo la tabla via DBeaver. Si compliance del piloto lo pide, es S effort (1-2h) exponer `GET /api/v1/audit?resource_type=...`.
- Filtro `unidad_id` en `GET /tareas-practicas` no filtra (deuda QA 2026-05-07).
- Leak de `student_pseudonyms` a estudiantes en `GET /comisiones/{id}/inscripciones` — el handler debería filtrar; Casbin permite (deuda QA 2026-05-07).
- `nota_final` se serializa como string Decimal `"8.50"` en respuestas; frontends lo tipan `number` — `Number()` works pero `.toFixed()` revienta (deuda QA 2026-05-07).
- No hay endpoint para mergear drifts de una instancia de vuelta al template (F8+).
- UI wizard para TP-gen IA en web-teacher DEFERIDO.

**Fase de consolidación**:
- F1 — schema inicial + matriz Casbin básica (`docs/F1-STATE.md`).
- F5 — extensión de Casbin con permisos por comisión específica.
- F6 — onboarding UNSL (realm Keycloak, federación LDAP, feature flags).
- F8 — entidad `TareaPractica` con versionado inmutable.
- F9 — `TareaPracticaTemplate` (ADR-016), RLS migrations review.
- 2026-04-29 — bulk-import de `inscripciones` consolidado (ADR-029); `enrollment-service` deprecado (ADR-030).
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `test_cases JSONB` (ADR-034), `created_via_ai` (ADR-036), `POST /generate` con audit log structlog. Bug `created_via_ai` fixed en c8a4685.
- 2026-05-04 (epic `real-health-checks`) — health `/ready` real con `check_postgres`.
- 2026-05-07 — entidad `Unidad` (epic `unidades-trazabilidad`); `identity-service` deprecado (ADR-041) y auth descentralizada en api-gateway + Casbin local. **131 policies** en seed Casbin verificadas.
