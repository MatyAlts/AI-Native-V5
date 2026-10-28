## MODIFIED Requirements

### Requirement: Return entrega for re-submission
`POST /api/v1/entregas/{id}/return` ("Pedir corrección") SHALL transition the entrega from `graded` to `returned`, allowing the student to re-submit by updating the same entrega. The request body SHALL be optional and MAY carry `ordenes`, the list of exercise `orden` values to reopen. Without `ordenes`, every exercise SHALL be reopened (the behavior before this change). With `ordenes`, ONLY those exercises SHALL be set to `completado=false` and marked `reabierto_por_docente=true`; every other exercise SHALL keep `completado`, `completed_at`, `episode_id` and its sealed submission artefact unchanged. No closed episode SHALL be reopened and no CTR event SHALL be emitted.

#### Scenario: Return a graded entrega
- **WHEN** a teacher calls `POST /api/v1/entregas/{id}/return` without a body
- **AND** the entrega has `estado=graded`
- **THEN** estado transitions to `returned`, every exercise is reopened, and the student can re-submit

#### Scenario: Request correction of a subset of exercises
- **WHEN** a teacher calls `POST /api/v1/entregas/{id}/return` with `{"ordenes": [2]}` on a graded entrega of 3 exercises
- **THEN** estado transitions to `returned`
- **AND** exercise 2 has `completado=false` and `reabierto_por_docente=true`
- **AND** exercises 1 and 3 keep `completado=true` and their previous `episode_id`

#### Scenario: Invalid list of exercises is rejected
- **WHEN** the body carries an empty `ordenes`, a duplicated `orden`, or an `orden` that is not in the entrega
- **THEN** the API SHALL return 422 and the entrega SHALL stay `graded`

#### Scenario: Student re-submits a returned entrega
- **WHEN** a student calls `POST /api/v1/entregas/{id}/submit`
- **AND** the entrega has `estado=returned`
- **THEN** estado transitions back to `submitted` and `submitted_at` is updated

#### Scenario: Re-submission of a partial return keeps the untouched exercises' sealed code
- **WHEN** a student re-submits an entrega returned with `ordenes=[2]`
- **AND** the request carries code only for exercise 2, or carries different code for exercises 1 and 3
- **THEN** the submit succeeds
- **AND** the new artefacts of exercises 1 and 3 have the same `codigo`, `sha256` and `episode_id` as before the return
- **AND** no exercise keeps `reabierto_por_docente=true` after the submit

#### Scenario: Existing returned entregas keep their behavior
- **WHEN** an entrega is `returned` and no exercise carries `reabierto_por_docente`
- **THEN** every exercise is treated as reopened, and the submit requires code for every exercise, as before this change

### Requirement: Grading view in web-teacher
The web-teacher SHALL include a "Correcciones" section accessible from the sidebar. It SHALL display a list of entregas filtered by comision and estado, with drill-down to a grading form showing the rubrica criteria, score inputs per criterion, and a general feedback textarea. The action that saves the first grade SHALL be labeled "Publicar nota", because the student sees the grade and feedback as soon as it is saved. A graded entrega SHALL offer a "Pedir corrección" action that lets the teacher choose which exercises to reopen. Help, tour and onboarding texts SHALL NOT claim that the grade stays hidden until the entrega is returned.

#### Scenario: Teacher navigates to grading view
- **WHEN** a teacher clicks "Correcciones" in the sidebar
- **THEN** a list of entregas for the selected comision is displayed with columns: student pseudonym, TP title, estado, submitted_at

#### Scenario: Teacher opens grading form
- **WHEN** a teacher clicks on a submitted entrega
- **THEN** a grading form appears with: rubrica criteria from the TP, score input per criterion, feedback textarea, and a "Publicar nota" button

#### Scenario: Teacher requests correction of chosen exercises
- **WHEN** a teacher clicks "Pedir corrección" on a graded entrega, ticks exercises 2 and 4, and confirms
- **THEN** the web-teacher calls `POST /api/v1/entregas/{id}/return` with `{"ordenes": [2, 4]}`
- **AND** confirming is not possible with zero exercises ticked

## ADDED Requirements

### Requirement: Student cannot modify exercises the teacher did not reopen
While an entrega is `returned` from a partial correction request, `PATCH /api/v1/entregas/{id}/ejercicio/{orden}` SHALL return 409 for any exercise that is not marked `reabierto_por_docente`, in both directions (`completado=true` and `completado=false`), and SHALL leave the entrega unchanged.

#### Scenario: Student tries to reopen an exercise that was not requested
- **WHEN** the entrega was returned with `ordenes=[2]`
- **AND** the student sends `PATCH .../ejercicio/1` with `completado=false`
- **THEN** the API SHALL return 409 and exercise 1 stays completed with its previous `episode_id`

#### Scenario: Requested exercise can still be marked
- **WHEN** the entrega was returned with `ordenes=[2]`
- **AND** the student closes exercise 2 and the web-student sends `PATCH .../ejercicio/2` with `completado=true`
- **THEN** exercise 2 is marked completed with the new `episode_id`
