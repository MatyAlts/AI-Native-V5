## ADDED Requirements

### Requirement: Entrega model with lifecycle states
The system SHALL maintain an `entregas` table in `academic_main` with columns: `id` (UUID PK), `tenant_id` (UUID, RLS), `tarea_practica_id` (FK), `student_pseudonym` (UUID), `comision_id` (FK), `estado` (draft|submitted|graded|returned), `ejercicio_estados` (JSONB), `submitted_at` (nullable timestamp), `created_at`, `deleted_at`. UNIQUE constraint on `(tenant_id, tarea_practica_id, student_pseudonym)`.

#### Scenario: One entrega per student per TP
- **WHEN** a student already has an entrega for a given TP
- **AND** the student attempts to create another entrega for the same TP
- **THEN** the API SHALL return 409 conflict

#### Scenario: RLS enforces tenant isolation
- **WHEN** a request with `tenant_id=A` queries entregas
- **THEN** only entregas with `tenant_id=A` are returned

### Requirement: Auto-create entrega in draft on first exercise
The system SHALL automatically create an `Entrega` in estado `draft` when a student opens the first exercise of a multi-exercise TP.

#### Scenario: First exercise creates draft entrega
- **WHEN** a student opens exercise 1 of a TP that has exercises
- **AND** no entrega exists for this student+TP
- **THEN** an entrega is created with `estado=draft` and `ejercicio_estados` initialized for all exercises with `completado=false`

#### Scenario: Subsequent exercise does not create duplicate
- **WHEN** a student opens exercise 2 of a TP
- **AND** an entrega already exists in draft
- **THEN** no new entrega is created

### Requirement: Exercise completion updates entrega state
When a student closes an episode linked to an exercise, the corresponding `ejercicio_estados` entry SHALL be updated to `completado=true` with the `episode_id` and `completed_at` timestamp.

#### Scenario: Close episode marks exercise complete
- **WHEN** a student closes an episode linked to exercise `orden=2`
- **THEN** the entrega's `ejercicio_estados[orden=2]` is updated with `completado=true`, `episode_id`, and `completed_at`

### Requirement: Explicit submit transitions to submitted
The student SHALL explicitly submit a TP via `POST /api/v1/entregas/{id}/submit`. This transitions the entrega from `draft` to `submitted` and records `submitted_at`.

#### Scenario: Submit with all exercises complete
- **WHEN** all exercises in `ejercicio_estados` have `completado=true`
- **AND** the student calls `POST /api/v1/entregas/{id}/submit`
- **THEN** estado transitions to `submitted` and `submitted_at` is set

#### Scenario: Submit with incomplete exercises rejected
- **WHEN** at least one exercise has `completado=false`
- **AND** the student calls `POST /api/v1/entregas/{id}/submit`
- **THEN** the API SHALL return 422 with "all exercises must be completed before submission"

### Requirement: CTR event tp_entregada emitted on submit
The system SHALL emit a CTR event `tp_entregada` when an entrega transitions to `submitted`.

#### Scenario: Submit emits CTR event
- **WHEN** an entrega transitions to `submitted`
- **THEN** a CTR event `tp_entregada` is emitted with payload `{tarea_practica_id, n_ejercicios, exercise_episode_ids}`
- **AND** the event is added to `_EXCLUDED_FROM_FEATURES` in the classifier

### Requirement: List entregas endpoint with filters
`GET /api/v1/entregas` SHALL support query params `comision_id`, `estado`, and `student_pseudonym`. Casbin policy `entrega:read` for docente/docente_admin/superadmin (all entregas in scope) and estudiante (own entregas only, filtered by `student_pseudonym` from header).

#### Scenario: Teacher lists submitted entregas for a comision
- **WHEN** a teacher calls `GET /api/v1/entregas?comision_id=X&estado=submitted`
- **THEN** all entregas with `comision_id=X` and `estado=submitted` are returned

#### Scenario: Student lists own entregas
- **WHEN** a student calls `GET /api/v1/entregas`
- **THEN** only entregas matching the student's `student_pseudonym` (from X-User-Id header) are returned

### Requirement: Get entrega detail with exercise episodes
`GET /api/v1/entregas/{id}` SHALL return the entrega with `ejercicio_estados` including linked `episode_id` per exercise.

#### Scenario: Entrega detail shows exercise completion state
- **WHEN** a teacher calls `GET /api/v1/entregas/{id}`
- **THEN** the response includes `ejercicio_estados` with per-exercise `completado`, `episode_id`, and `completed_at`
