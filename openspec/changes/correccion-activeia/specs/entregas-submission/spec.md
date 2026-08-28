## MODIFIED Requirements

### Requirement: Explicit submit transitions to submitted
The student SHALL explicitly submit a TP via `POST /api/v1/entregas/{id}/submit`. This transitions the entrega from `draft` to `submitted` and records `submitted_at`.

The submit SHALL carry the source code of every exercise, which is persisted as the entrega's artefacto (see `entrega-artefacto`).

Completeness SHALL be validated against the exercises expected by the TP, obtained from `tp_ejercicios`, and NOT against the entries that happen to be present in `ejercicio_estados`. An entrega whose `ejercicio_estados` is empty SHALL be rejected rather than accepted.

#### Scenario: Submit with all exercises complete
- **WHEN** all exercises expected by the TP have `completado=true` in `ejercicio_estados`
- **AND** the student calls `POST /api/v1/entregas/{id}/submit` with the source of each exercise
- **THEN** estado transitions to `submitted`, `submitted_at` is set, and the artefacto is persisted

#### Scenario: Submit with incomplete exercises rejected
- **WHEN** at least one exercise expected by the TP has `completado=false`
- **AND** the student calls `POST /api/v1/entregas/{id}/submit`
- **THEN** the API SHALL return 422 with "all exercises must be completed before submission"

#### Scenario: Submit with no exercise state at all is rejected
- **WHEN** `ejercicio_estados` is empty and the TP has at least one exercise
- **AND** the student calls `POST /api/v1/entregas/{id}/submit`
- **THEN** the API SHALL return 422 identifying the exercises that are missing

### Requirement: Auto-create entrega in draft on first exercise
An entrega SHALL be created in `draft` state the first time a student opens an exercise of the TP.

At creation, `ejercicio_estados` SHALL be seeded from the TP's `tp_ejercicios`, with one entry per expected exercise marked as not completed. The list SHALL NOT be created empty, so that a missing exercise is a detectable state rather than the initial state of every entrega.

#### Scenario: Entrega is created with every expected exercise seeded
- **WHEN** a student opens the first exercise of a TP with four exercises
- **THEN** an entrega SHALL be created in `draft`
- **AND** `ejercicio_estados` SHALL contain four entries, one per exercise, all not completed

#### Scenario: Completing an exercise updates its seeded entry
- **WHEN** the student completes one exercise
- **THEN** its existing entry SHALL be updated rather than appended
