# evaluation-service

## 1. Qué hace (una frase)

Gestiona el ciclo de vida de **entregas** del estudiante (`draft → submitted → graded → returned`) y las **calificaciones** docentes contra las TPs publicadas — comparte la base `academic_main` con [academic-service](./academic-service.md) vía un engine independiente, y emite audit log structlog (`tp_entregada`, `tp_calificada`).

## 2. Rol en la arquitectura

Pertenece al **plano académico-operacional**. Materializa parte del componente "Servicio de evaluación" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: persistir las entregas del estudiante por TareaPractica y permitir al docente calificarlas con devolución cualitativa.

Era stub F0 hasta el epic `tp-entregas-correccion` (commit 5efcce8) — ahora tiene 8 endpoints REST operativos. La decisión de fusionarlo con academic-service (Fase 2 del plan de restructure) queda como deuda post-piloto.

## 3. Responsabilidades

- Exponer 8 endpoints REST sobre el flujo de Entrega/Calificación:
  - `POST /api/v1/entregas` — crear entrega en `draft` (idempotente por `(tenant_id, tarea_practica_id, student_pseudonym)`).
  - `GET /api/v1/entregas` (con filtros) — listar entregas del tenant.
  - `GET /api/v1/entregas/{id}` — detalle.
  - `POST /api/v1/entregas/{id}/submit` — `draft → submitted` + audit log `tp_entregada`.
  - `PATCH /api/v1/entregas/{id}/ejercicio/{n}` — marcar ejercicio individual completado.
  - `POST /api/v1/entregas/{id}/calificar` — crear `Calificacion` + audit log `tp_calificada`.
  - `GET /api/v1/entregas/{id}/calificacion` — leer la calificación.
  - `POST /api/v1/entregas/{id}/return` — `graded → returned`.
- Emitir audit log structlog en operaciones críticas (`tp_entregada`, `tp_calificada`) con `tenant_id`, `user_id`, `entrega_id`, `tarea_practica_id`. **No tabla persistente** — sigue el mismo patrón que κ/AB del analytics-service (HU-088).
- Manejar `IntegrityError` global (handler en `main.py`) y devolverlo como 409 con detalle apropiado.
- Aplicar Casbin RBAC: `entrega:create/read` para `estudiante`, `entrega:update` + `calificacion:create/read` para `docente`/`docente_admin`/`superadmin`.
- Multi-tenancy via RLS sobre las tablas `entregas` y `calificaciones` (`SET LOCAL app.current_tenant`).
- **Race condition guard** en `create_entrega`: si dos requests concurrentes pasan el SELECT y colisionan en el UNIQUE constraint, el perdedor reintenta el SELECT tras rollback del savepoint.

## 4. Qué NO hace (anti-responsabilidades)

- **NO valida que los ejercicios entregados compilen ni pasen tests**: la ejecución de tests vive en [tutor-service](./tutor-service.md) (`POST /run-tests`) y emite evento CTR `tests_ejecutados`. Acá sólo se persiste el estado de la entrega.
- **NO calcula la nota automáticamente**: la `Calificacion.nota` la pone el docente. Una integración futura con la `rubrica` JSONB de la TP sigue como deuda.
- **NO clasifica en N4**: eso es [classifier-service](./classifier-service.md). La nota docente y la categoría N4 son señales independientes.
- **NO reemplaza `tareas_practicas`**: la TP autoritativa vive en [academic-service](./academic-service.md). Acá se referencia por `tarea_practica_id` (UUID, sin FK cross-service explícita pero misma DB).
- **NO emite eventos al CTR**: la entrega no es un evento del CTR — es persistencia de evaluación académica del docente. La actividad pedagógica del estudiante (que SÍ va al CTR) la captura tutor-service.
- **NO es el único endpoint para marcar ejercicios completados**: el frontend puede marcar individualmente con `PATCH /ejercicio/{n}` antes del `submit` final.

## 5. Endpoints HTTP

Todos los endpoints exigen `X-Tenant-Id` + `X-User-Id` + `X-User-Roles` inyectados por [api-gateway](./api-gateway.md).

| Método | Path | Qué hace | Casbin |
|---|---|---|---|
| `POST` | `/api/v1/entregas` | Crear entrega en `draft` (idempotente). 200 si ya existe, 201 si nueva. | `entrega:create` (estudiante) |
| `GET` | `/api/v1/entregas?tarea_practica_id=&comision_id=&estado=` | Listar con filtros. | `entrega:read` |
| `GET` | `/api/v1/entregas/{id}` | Detalle. | `entrega:read` |
| `POST` | `/api/v1/entregas/{id}/submit` | `draft → submitted`. Emite `tp_entregada` a structlog. | `entrega:update` (estudiante) |
| `PATCH` | `/api/v1/entregas/{id}/ejercicio/{n}` | Marcar ejercicio individual completado en `ejercicio_estados`. | `entrega:update` |
| `POST` | `/api/v1/entregas/{id}/calificar` | `submitted → graded`. Crea `Calificacion`. Emite `tp_calificada` a structlog. | `calificacion:create` (docente+) |
| `GET` | `/api/v1/entregas/{id}/calificacion` | Leer la `Calificacion`. | `calificacion:read` |
| `POST` | `/api/v1/entregas/{id}/return` | `graded → returned`. | `entrega:update` (docente+) |
| `GET` | `/health`, `/health/ready` | Health real con `check_postgres` (epic `real-health-checks`, 2026-05-04). | Ninguna |

**Estado FSM** (`Entrega.estado`): `draft → submitted → graded → returned → (re-submit → submitted)`. Re-submisión es válida — el docente puede marcar `returned` para que el estudiante itere.

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL — base lógica `academic_main` (compartida con academic-service vía engine independiente). Mismas reglas RLS.

**Depende de (otros servicios):** ninguno HTTP directo. Comparte DB con `academic-service` pero NO hace JOINs cross-service (las TPs son referenciadas por UUID).

**Dependen de él:**
- [web-student](./web-student.md) — flujo de entrega (crear/submit/marcar ejercicios).
- [web-teacher](./web-teacher.md) — flujo de calificación (calificar/return).

## 7. Modelo de datos

Base lógica: **`academic_main`** (compartida). Migraciones Alembic propias en `apps/evaluation-service/alembic/versions/`.

**Tablas principales** (`apps/evaluation-service/src/evaluation_service/models/entregas.py`):

- **`entregas`**
  - PK: `id` UUID.
  - `tenant_id` con RLS policy.
  - `tarea_practica_id` (UUID, sin FK cruzada — referenciada por código).
  - `student_pseudonym` (UUID).
  - `comision_id` (UUID).
  - `estado` — `draft | submitted | graded | returned`.
  - `ejercicio_estados` JSONB — array de booleanos o objetos por ejercicio.
  - `submitted_at`, `created_at`, `updated_at`.
  - Constraint UNIQUE `(tenant_id, tarea_practica_id, student_pseudonym)` — un estudiante una entrega por TP.

- **`calificaciones`**
  - PK: `id` UUID.
  - `tenant_id` con RLS policy.
  - `entrega_id` FK a `entregas`.
  - `nota` (Decimal — el formato string `"8.50"` cuando se serializa es deuda QA 2026-05-07: frontends lo tipan `number`).
  - `feedback` text.
  - `calificado_por` (UUID del docente).
  - `created_at`.
  - Constraint UNIQUE `(tenant_id, entrega_id)` — una calificación por entrega.

**RLS**: ambas tablas con policy `tenant_isolation`. Como comparte la base con academic-service, ambos servicios respetan el `SET LOCAL app.current_tenant` independientemente — ADR-003 no se rompe porque no hay JOINs cross-service en SQL (sólo refs por UUID).

## 8. Archivos clave para entender el servicio

- `apps/evaluation-service/src/evaluation_service/routes/entregas.py` — los 8 endpoints REST + race condition guard en `create_entrega`.
- `apps/evaluation-service/src/evaluation_service/models/entregas.py` — `Entrega` y `Calificacion` SQLAlchemy.
- `apps/evaluation-service/src/evaluation_service/schemas/entrega.py` — Pydantic schemas (`EntregaCreate`, `EntregaOut`, `CalificacionCreate`, `CalificacionOut`, `MarkEjercicioBody`).
- `apps/evaluation-service/src/evaluation_service/auth/` — Casbin enforcer + `require_permission(resource, action)` dependency.
- `apps/evaluation-service/src/evaluation_service/db/` — engine independiente para `academic_main`.
- `apps/evaluation-service/src/evaluation_service/main.py` — entrypoint FastAPI con `IntegrityError` handler global.
- `apps/evaluation-service/tests/` — suite de tests del flujo end-to-end (verificar coverage actual).

## 9. Configuración y gotchas

**Env vars críticas**:
- `EVALUATION_DB_URL` — apunta a `academic_main` (mismo cluster, mismo DB que academic-service).

**Puerto de desarrollo**: `8004`.

**Gotchas específicos**:

- **Comparte DB con academic-service via engine independiente**: dos servicios escribiendo al mismo `academic_main` requiere coordinar migrations — cada servicio tiene su propio Alembic con tablas no overlapping. Evaluation-service maneja `entregas` + `calificaciones`; academic-service maneja todo lo demás. Si un servicio borra una tabla del otro por accidente en una migration, hay drift difícil de detectar.
- **Decisión de fusión deferida**: la Fase 2 del plan de restructure prevé fusionar evaluation-service en academic-service (eliminando un servicio del monorepo). Hoy quedan separados por claridad y para no bloquear v1.0; cuando se haga el merge será deuda post-piloto.
- **`nota` Decimal serializado como string**: el JSON `{"nota": "8.50"}` viene como string. Frontends lo tipan `number` — `Number(nota)` works pero `.toFixed()` revienta. Deuda QA 2026-05-07.
- **Race condition en create_entrega**: si dos requests concurrentes pasan el SELECT y colisionan en el UNIQUE constraint, el perdedor reintenta el SELECT tras rollback del savepoint. Documentado en docstring.
- **Idempotencia parcial**: `POST /entregas` con misma `(tarea_practica_id, student_pseudonym)` devuelve la existente (200, no 201). Otros endpoints (`submit`, `calificar`) NO son idempotentes en el wire — re-POST falla con 409 si el estado ya cambió.
- **Sin emisión al CTR**: las entregas NO son eventos del CTR. La pedagogía del flujo de la entrega va por audit log structlog. Si compliance del piloto requiere persistencia auditable de las calificaciones, hay que evaluar agregar tabla `audit_log` paralela (mismo patrón que academic-service).

## 10. Relación con la tesis doctoral

El evaluation-service no implementa componentes centrales del modelo N4. Su rol es **soporte operativo** del flujo evaluativo tradicional para que el piloto UNSL pueda capturar las notas docentes (variable de control en el análisis correlacional con N4):

- La tesis (Capítulo 8) plantea como pregunta exploratoria: *"¿hay correlación entre la categoría N4 del clasificador (apropiación reflexiva) y la nota docente tradicional?"*. Para responderla, hay que tener ambas señales persistidas.
- La nota docente la persiste evaluation-service en `calificaciones.nota`; la categoría N4 la persiste classifier-service en `classifications.appropriation`. Analytics-service puede correlacionarlas cross-base por `(tarea_practica_id, student_pseudonym)`.
- La rúbrica JSONB en `tareas_practicas.rubrica` (academic-service) **no se aplica automáticamente** acá — la nota es manual del docente. Una integración LLM-based con la rúbrica queda como deuda post-piloto (probable evaluation gen IA, similar a TP-gen IA del ADR-036).

## 11. Estado de madurez

**Tests**: suite en `apps/evaluation-service/tests/` cubre el flujo end-to-end (verificar coverage exacto).

**Known gaps**:
- `nota` Decimal serializado como string vs. tipado `number` en frontends (deuda QA 2026-05-07).
- Sin endpoint queryable del audit log — hoy en structlog/Loki.
- Sin integración LLM-based con `rubrica` JSONB (probable epic post-piloto).
- Decisión de fusión con academic-service deferida (Fase 2 del plan de restructure).
- Sin tests RLS contra Postgres real — sólo matrices Casbin.

**Fase de consolidación**:
- Pre-2026-05 — stub F0 (placeholder con `/health` y CORS).
- 2026-05 (epic `tp-entregas-correccion`, commit 5efcce8) — implementación completa: 8 endpoints, 2 modelos, audit log structlog, `IntegrityError` handler, race condition guard, Casbin policies.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_postgres`.
