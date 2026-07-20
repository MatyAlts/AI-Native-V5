## 1. Database & Models

- [x] 1.1 Add `ejercicios: JSONB` column to `TareaPractica` model in `academic-service/models/operacional.py` and create Alembic migration in academic-service
- [x] 1.2 Create `entregas` table model in `evaluation-service` (SQLAlchemy) pointing to `academic_main` DB, with RLS policy on `tenant_id`
- [x] 1.3 Create `calificaciones` table model in `evaluation-service` (SQLAlchemy) with FK UNIQUE to `entregas`, RLS policy on `tenant_id`
- [x] 1.4 Create Alembic migration for `entregas` and `calificaciones` tables (run via academic-service's Alembic since same DB)
- [x] 1.5 Validate exercises JSONB schema: unique `orden`, weights sum to 1.0, required fields — add Pydantic schemas in `packages/contracts`

## 2. Academic-Service: Exercises in TPs

- [x] 2.1 Extend `TareaPracticaCreate` / `TareaPracticaUpdate` Pydantic schemas to include `ejercicios` field with validation
- [x] 2.2 Update CRUD endpoints for TareaPractica to persist and return `ejercicios`
- [x] 2.3 Add endpoint `GET /api/v1/tareas-practicas/{id}/ejercicios` returning the exercise list for a TP
- [x] 2.4 Add unit tests for exercise JSONB validation (unique orden, weight sum, immutability when published)

## 3. Evaluation-Service: Entregas Endpoints

- [x] 3.1 Activate evaluation-service: add routes module, configure SQLAlchemy session with `academic_main`, add Casbin enforcer
- [x] 3.2 Implement `POST /api/v1/entregas` — create draft entrega for a student+TP (idempotent, returns existing if found)
- [x] 3.3 Implement `GET /api/v1/entregas` — list entregas with filters `comision_id`, `estado`, `student_pseudonym`; Casbin-scoped
- [x] 3.4 Implement `GET /api/v1/entregas/{id}` — entrega detail with `ejercicio_estados`
- [x] 3.5 Implement `POST /api/v1/entregas/{id}/submit` — transition draft→submitted, validate all exercises complete, emit CTR event `tp_entregada`
- [x] 3.6 Implement `PATCH /api/v1/entregas/{id}/ejercicio/{orden}` — mark exercise as completed with `episode_id`
- [x] 3.7 Add unit tests for entrega lifecycle (create, update exercise status, submit, reject incomplete submit)

## 4. Evaluation-Service: Grading Endpoints

- [x] 4.1 Implement `POST /api/v1/entregas/{id}/calificar` — create calificacion, transition submitted→graded, emit CTR event `tp_calificada`
- [x] 4.2 Implement `GET /api/v1/entregas/{id}/calificacion` — read calificacion; Casbin-scoped (docente=all in scope, student=own only)
- [x] 4.3 Implement `POST /api/v1/entregas/{id}/return` — transition graded→returned
- [x] 4.4 Add Casbin policies: `entrega:read`, `entrega:create`, `calificacion:create`, `calificacion:read` for relevant roles
- [x] 4.5 Add unit tests for grading (create calificacion, reject non-submitted, reject duplicate, return flow)

## 5. CTR Events & Classifier

- [x] 5.1 Add `tp_entregada` and `tp_calificada` event types to `packages/contracts` Pydantic schemas
- [x] 5.2 Add `tp_entregada` and `tp_calificada` to `_EXCLUDED_FROM_FEATURES` in classifier pipeline.py
- [x] 5.3 Add `ejercicio_orden: int | None` field to `EpisodioAbierto` payload in contracts
- [x] 5.4 Add unit test verifying new events are excluded from classifier features

## 6. Tutor-Service: Exercise-Aware Episodes

- [x] 6.1 Modify `open_episode` to accept optional `ejercicio_orden` param and include it in the `episodio_abierto` CTR event
- [x] 6.2 When `ejercicio_orden` is provided, resolve exercise-specific `enunciado_md`, `inicial_codigo`, and `test_cases` from the TP's `ejercicios` JSONB
- [x] 6.3 Add validation: reject opening exercise if previous exercises not completed (query entrega state)
- [x] 6.4 Add unit tests for exercise-aware episode opening

## 7. API-Gateway: Route Map

- [x] 7.1 Add `/api/v1/entregas` and `/api/v1/calificaciones` entries to `ROUTE_MAP` pointing to evaluation-service (port 8004)

## 8. Web-Student: Exercise Flow

- [x] 8.1 Modify `TareaSelector` to detect multi-exercise TPs and show exercise list with sequential unlock UI
- [x] 8.2 Create `ExerciseListView` component: ordered list of exercises with lock/unlock/complete states
- [x] 8.3 Wire exercise selection to `open_episode` with `ejercicio_orden` param
- [x] 8.4 Show entrega progress bar (X/N exercises completed)
- [x] 8.5 Add "Entregar TP" button visible only when all exercises complete, calls `POST /api/v1/entregas/{id}/submit`
- [x] 8.6 Show entrega status badges on TP cards (draft/submitted/graded/returned)

## 9. Web-Student: Grade View

- [x] 9.1 Create `GradeDetailView` component showing `nota_final`, `feedback_general`, and per-criterion detail
- [x] 9.2 Add route and navigation from TP card (when graded) to grade detail view
- [x] 9.3 Show "Pendiente de correccion" state for submitted-but-ungraded entregas

## 10. Web-Teacher: Grading View

- [x] 10.1 Add "Correcciones" entry to sidebar navigation
- [x] 10.2 Create `EntregasListView` — table of entregas filtered by comision + estado, columns: student, TP title, estado, submitted_at
- [x] 10.3 Create `GradingFormView` — drill-down from entrega: shows exercise code/episodes, rubrica criteria inputs, feedback textarea, "Calificar" button
- [x] 10.4 Wire grading form to `POST /api/v1/entregas/{id}/calificar`
- [x] 10.5 Add "Devolver" button for graded entregas calling `POST /api/v1/entregas/{id}/return`

## 11. Web-Teacher: Analytics Integration

- [x] 11.1 Extend `ProgressionView` to show entrega/grade stats per student (entregas pendientes, corregidas, nota promedio)
- [x] 11.2 Add drill-down from entrega to each exercise's episode (CTR trace navigation)

## 12. Tests E2E

- [x] 12.1 Add vitest+RTL tests for `ExerciseListView` in web-student
- [x] 12.2 Add vitest+RTL tests for `EntregasListView` and `GradingFormView` in web-teacher
- [x] 12.3 Add smoke tests in `tests/e2e/smoke/` for entregas + calificaciones endpoints
