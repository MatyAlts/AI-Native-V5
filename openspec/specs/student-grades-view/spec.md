## ADDED Requirements

### Requirement: Student sees entrega status per TP
The web-student SHALL display the entrega status for each TP in the TareaSelector. For TPs with exercises, the status SHALL show: number of exercises completed, whether submitted, and whether graded.

#### Scenario: TP in progress shows exercise progress
- **WHEN** a student views the TareaSelector
- **AND** they have an entrega in `draft` for a TP with 3 exercises, 2 completed
- **THEN** the TP card shows "2/3 ejercicios completados"

#### Scenario: TP submitted shows pending status
- **WHEN** a student has an entrega in `submitted` for a TP
- **THEN** the TP card shows "Entregado - Pendiente de correccion"

#### Scenario: TP graded shows grade
- **WHEN** a student has an entrega in `graded` for a TP
- **THEN** the TP card shows the `nota_final` value

### Requirement: Student grade detail view
The web-student SHALL provide a view where the student can see their calificacion detail including `nota_final`, `feedback_general`, and per-criterion scores with comments.

#### Scenario: Student views graded TP
- **WHEN** a student navigates to the grade detail of a graded entrega
- **THEN** the view displays: `nota_final`, `feedback_general`, and a list of criteria with `puntaje/max_puntaje` and `comentario` per criterion

#### Scenario: Student views ungraded TP
- **WHEN** a student navigates to the grade detail of a submitted but ungraded entrega
- **THEN** the view displays "Pendiente de correccion" message

### Requirement: Student can only see own grades
The student grade endpoints SHALL filter by `student_pseudonym` from the authenticated user header. A student SHALL NOT be able to see another student's grades.

#### Scenario: Student queries own calificacion
- **WHEN** a student calls `GET /api/v1/entregas/{id}/calificacion`
- **AND** the entrega belongs to the student
- **THEN** the calificacion is returned

#### Scenario: Student queries another student's calificacion
- **WHEN** a student calls `GET /api/v1/entregas/{id}/calificacion`
- **AND** the entrega belongs to a different student
- **THEN** the API SHALL return 403
