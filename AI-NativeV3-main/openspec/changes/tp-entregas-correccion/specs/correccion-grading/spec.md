## ADDED Requirements

### Requirement: Calificacion model linked to entrega
The system SHALL maintain a `calificaciones` table in `academic_main` with columns: `id` (UUID PK), `tenant_id` (UUID, RLS), `entrega_id` (FK UNIQUE to entregas), `graded_by` (UUID, docente user_id), `nota_final` (NUMERIC(5,2), CHECK 0-10), `feedback_general` (TEXT nullable), `detalle_criterios` (JSONB array of `{criterio, puntaje, max_puntaje, comentario}`), `graded_at` (timestamp), `deleted_at` (nullable).

#### Scenario: One calificacion per entrega
- **WHEN** a calificacion already exists for an entrega
- **AND** a teacher attempts to create another calificacion for the same entrega
- **THEN** the API SHALL return 409 conflict

#### Scenario: RLS enforces tenant isolation on calificaciones
- **WHEN** a request with `tenant_id=A` queries calificaciones
- **THEN** only calificaciones with `tenant_id=A` are returned

### Requirement: Grade an entrega via POST endpoint
`POST /api/v1/entregas/{id}/calificar` SHALL create a calificacion and transition the entrega estado to `graded`. Casbin policy `calificacion:create` for docente/docente_admin/superadmin.

#### Scenario: Successfully grade a submitted entrega
- **WHEN** a teacher calls `POST /api/v1/entregas/{id}/calificar` with `nota_final`, `feedback_general`, and `detalle_criterios`
- **AND** the entrega has `estado=submitted`
- **THEN** a calificacion is created, entrega transitions to `graded`, and `graded_at` is set

#### Scenario: Grade a non-submitted entrega rejected
- **WHEN** a teacher calls `POST /api/v1/entregas/{id}/calificar`
- **AND** the entrega has `estado=draft`
- **THEN** the API SHALL return 422 with "can only grade submitted entregas"

#### Scenario: nota_final out of range rejected
- **WHEN** `nota_final` is less than 0 or greater than 10
- **THEN** the API SHALL return 422 with validation error

### Requirement: CTR event tp_calificada emitted on grading
The system SHALL emit a CTR event `tp_calificada` when a calificacion is created.

#### Scenario: Grading emits CTR event
- **WHEN** a calificacion is created
- **THEN** a CTR event `tp_calificada` is emitted with payload `{entrega_id, nota_final, graded_by}`
- **AND** the event is added to `_EXCLUDED_FROM_FEATURES` in the classifier

### Requirement: Read calificacion endpoint
`GET /api/v1/entregas/{id}/calificacion` SHALL return the calificacion for an entrega. Casbin: `calificacion:read` for docente (all in scope) and estudiante (own only).

#### Scenario: Teacher reads calificacion
- **WHEN** a teacher calls `GET /api/v1/entregas/{id}/calificacion`
- **AND** the entrega has been graded
- **THEN** the calificacion with `nota_final`, `feedback_general`, `detalle_criterios`, and `graded_at` is returned

#### Scenario: Calificacion not yet created
- **WHEN** a teacher calls `GET /api/v1/entregas/{id}/calificacion`
- **AND** the entrega has not been graded
- **THEN** the API SHALL return 404

### Requirement: Return entrega for re-submission
`POST /api/v1/entregas/{id}/return` SHALL transition the entrega from `graded` to `returned`, allowing the student to re-submit by updating the same entrega.

#### Scenario: Return a graded entrega
- **WHEN** a teacher calls `POST /api/v1/entregas/{id}/return`
- **AND** the entrega has `estado=graded`
- **THEN** estado transitions to `returned` and the student can re-submit

#### Scenario: Student re-submits a returned entrega
- **WHEN** a student calls `POST /api/v1/entregas/{id}/submit`
- **AND** the entrega has `estado=returned`
- **THEN** estado transitions back to `submitted` and `submitted_at` is updated

### Requirement: Grading view in web-teacher
The web-teacher SHALL include a "Correcciones" section accessible from the sidebar. It SHALL display a list of entregas filtered by comision and estado, with drill-down to a grading form showing the rubrica criteria, score inputs per criterion, and a general feedback textarea.

#### Scenario: Teacher navigates to grading view
- **WHEN** a teacher clicks "Correcciones" in the sidebar
- **THEN** a list of entregas for the selected comision is displayed with columns: student pseudonym, TP title, estado, submitted_at

#### Scenario: Teacher opens grading form
- **WHEN** a teacher clicks on a submitted entrega
- **THEN** a grading form appears with: rubrica criteria from the TP, score input per criterion, feedback textarea, and "Calificar" button
