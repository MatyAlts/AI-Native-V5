## ADDED Requirements

### Requirement: Sequential exercise flow in web-student
The web-student SHALL display exercises of a TP as a sequential list. The student SHALL complete exercises in order: exercise N+1 unlocks only after exercise N is marked complete.

#### Scenario: Student sees exercise list for a multi-exercise TP
- **WHEN** a student selects a TP that has `ejercicios` with 3 items
- **THEN** the UI displays a list of 3 exercises with titles, showing exercise 1 as available and exercises 2-3 as locked

#### Scenario: Exercise unlocks after completing previous
- **WHEN** a student completes exercise 1 (closes the episode)
- **AND** returns to the TP exercise list
- **THEN** exercise 1 shows as completed and exercise 2 is now available

#### Scenario: Monolithic TP bypasses exercise flow
- **WHEN** a student selects a TP with `ejercicios` null or empty
- **THEN** the current single-episode flow is used (no exercise list)

### Requirement: One episode per exercise
Each exercise SHALL open exactly one episode. The episode payload SHALL include `ejercicio_orden` to link the episode to the specific exercise.

#### Scenario: Opening an exercise creates an episode with ejercicio_orden
- **WHEN** a student opens exercise with `orden=2`
- **THEN** an episode is created with `ejercicio_orden=2` in the CTR event `episodio_abierto` payload

#### Scenario: Reopening a completed exercise is not allowed
- **WHEN** a student attempts to open exercise 1 again after it is marked complete
- **THEN** the UI SHALL prevent opening and show "Ejercicio completado"

### Requirement: Submit button appears when all exercises complete
The web-student SHALL show an "Entregar TP" button only when all exercises in the TP are marked as completed.

#### Scenario: All exercises complete shows submit button
- **WHEN** all exercises have `completado=true` in the entrega's `ejercicio_estados`
- **THEN** the "Entregar TP" button is visible and enabled

#### Scenario: Incomplete exercises hides submit button
- **WHEN** at least one exercise has `completado=false`
- **THEN** the "Entregar TP" button is hidden or disabled

### Requirement: Exercise view shows individual exercise context
When a student opens an exercise, the tutor session SHALL receive the exercise-specific `enunciado_md`, `inicial_codigo`, and `test_cases` instead of the monolithic TP enunciado.

#### Scenario: Exercise-specific context sent to tutor
- **WHEN** a student opens exercise 2 of a TP
- **THEN** the tutor-service receives the exercise's `enunciado_md` and `inicial_codigo` as the problem context
- **AND** test validation uses the exercise's `test_cases`
