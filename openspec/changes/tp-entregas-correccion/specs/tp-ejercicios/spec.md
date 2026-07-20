## ADDED Requirements

### Requirement: TareaPractica supports ordered exercises as JSONB array
The `TareaPractica` model SHALL include an `ejercicios` field of type `JSONB` containing an ordered array of exercise objects. Each exercise object SHALL have: `orden` (int), `titulo` (string), `enunciado_md` (string, markdown), `inicial_codigo` (string), `test_cases` (array, same schema as existing `TareaPractica.test_cases`), and `peso` (numeric, 0-1).

#### Scenario: TP with exercises created via API
- **WHEN** a teacher creates a TareaPractica with `ejercicios` containing 3 exercise objects
- **THEN** the TP is persisted with `ejercicios` JSONB containing 3 items ordered by `orden`
- **AND** each exercise has `titulo`, `enunciado_md`, `inicial_codigo`, `test_cases`, and `peso`

#### Scenario: TP without exercises remains backwards-compatible
- **WHEN** a TareaPractica has `ejercicios` as null or empty array
- **THEN** the TP behaves as a monolithic TP (current behavior)
- **AND** no exercise-related UI or logic activates

#### Scenario: Exercise orden must be unique within a TP
- **WHEN** a teacher attempts to create a TP with two exercises having the same `orden`
- **THEN** the API SHALL return 422 with validation error

### Requirement: Exercises are editable only in draft state
The `ejercicios` field SHALL only be modifiable when the TareaPractica is in `draft` estado. Once `published`, the TP is immutable (existing invariant).

#### Scenario: Edit exercises on draft TP
- **WHEN** a teacher updates `ejercicios` on a TP with `estado=draft`
- **THEN** the update succeeds

#### Scenario: Reject exercise edit on published TP
- **WHEN** a teacher attempts to update `ejercicios` on a TP with `estado=published`
- **THEN** the API SHALL return 409 with immutability error

### Requirement: Exercise weights must sum to 1.0
The `peso` values across all exercises in a TP SHALL sum to 1.0 (with tolerance of 0.01).

#### Scenario: Valid weights
- **WHEN** a TP has 2 exercises with `peso` 0.5 and 0.5
- **THEN** validation passes

#### Scenario: Invalid weights
- **WHEN** a TP has 2 exercises with `peso` 0.3 and 0.3
- **THEN** the API SHALL return 422 with "exercise weights must sum to 1.0"
