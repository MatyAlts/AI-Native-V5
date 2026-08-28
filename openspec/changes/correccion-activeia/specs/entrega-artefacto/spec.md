## ADDED Requirements

### Requirement: Artefacto persisted per exercise at submit time
The system SHALL persist the student's source code for each exercise of a TP at submit time, sent by the client, in a dedicated table owned by `evaluation-service`. Each row SHALL record `orden`, `episode_id`, the source code, and its own `sha256`. The entrega SHALL also record a `sha256` of the whole set.

The system SHALL NOT reconstruct the artefacto by reading the CTR at correction time: CTR ingestion is asynchronous and would certify a read, not a submission.

#### Scenario: Submit persists code for every exercise
- **WHEN** a student calls `POST /api/v1/entregas/{id}/submit` with the source of each exercise
- **THEN** one artefacto row per exercise SHALL be stored with its `orden`, `episode_id`, code and `sha256`
- **AND** the entrega SHALL store the `sha256` of the whole set

#### Scenario: Hash is stored, never recomputed on read
- **WHEN** the artefacto is read back
- **THEN** the stored `sha256` SHALL be returned as persisted
- **AND** the system SHALL NOT recompute it from the current content

#### Scenario: Submit without code for an expected exercise is rejected
- **WHEN** the submit payload omits the source of an exercise present in `tp_ejercicios`
- **THEN** the API SHALL return 422 identifying the missing `orden`

### Requirement: Artefacto download endpoint for teachers
The system SHALL expose `GET /api/v1/entregas/{id}/artefacto`, returning the stored source plus a manifest listing, per exercise, its `orden`, `episode_id` and `sha256`, and the `sha256` of the set. Access SHALL require membership of the entrega's comision, except for the oversight roles (`superadmin`, `docente_admin`) and for the student who owns the entrega, consistent with the entrega listing.

#### Scenario: Teacher of the comision downloads the artefacto
- **WHEN** a teacher who belongs to the entrega's comision requests the endpoint
- **THEN** the API SHALL return the source and the manifest

#### Scenario: Teacher of another comision is denied
- **WHEN** a teacher who does not belong to the entrega's comision requests the endpoint
- **THEN** the API SHALL return 404, not 403, to avoid disclosing existence

#### Scenario: Teacher downloads from the grading view
- **WHEN** a teacher opens the grading form of an entrega with a stored artefacto
- **THEN** a "Descargar entrega" action SHALL be available in the actions row

### Requirement: LEGACY marking for entregas predating persistence
Entregas submitted before this capability SHALL be marked `LEGACY`. The system MAY reconstruct their code best-effort from the CTR, and SHALL label any such reconstruction as reconstructed in the response and in the UI. LEGACY entregas SHALL NOT be eligible for automated correction.

#### Scenario: Legacy entrega is shown as reconstructed
- **WHEN** a teacher opens an entrega submitted before this change
- **THEN** the UI SHALL state that the code is a best-effort reconstruction from the CTR, not the submitted artefacto

#### Scenario: Legacy entrega cannot be sent for automated correction
- **WHEN** a correction is requested for a LEGACY entrega
- **THEN** the API SHALL reject it, stating that there is no persisted artefacto

### Requirement: Editor flushes pending edits before submit
The student editor SHALL flush any pending debounced change before the submit request is issued, so the persisted artefacto includes the last keystrokes.

#### Scenario: Pending debounce is flushed on submit
- **WHEN** the student submits within the debounce window after typing
- **THEN** the pending change SHALL be included in the persisted artefacto
