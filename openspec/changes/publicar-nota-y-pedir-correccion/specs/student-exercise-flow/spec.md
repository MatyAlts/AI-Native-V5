## MODIFIED Requirements

### Requirement: Sequential exercise flow in web-student
The web-student SHALL display exercises of a TP as a sequential list. The student SHALL complete pending exercises in order: an exercise that is not completed unlocks only when every exercise with a lower `orden` is completed. A completed exercise SHALL never be shown as locked. Exercises the teacher did not reopen in a partial correction request stay completed and therefore count as done.

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

#### Scenario: Partial correction request only locks among reopened exercises
- **WHEN** an entrega of 5 exercises is returned with `ordenes=[2, 4]`
- **THEN** exercises 1, 3 and 5 show as completed
- **AND** exercise 2 is available
- **AND** exercise 4 is locked until exercise 2 is completed

#### Scenario: Full return keeps the previous behavior
- **WHEN** an entrega is returned with every exercise reopened
- **THEN** only exercise 1 is available, as before this change

## ADDED Requirements

### Requirement: Student sees which exercises the teacher asked to correct
In a `returned` entrega, the web-student SHALL show a "A corregir" badge on each exercise marked `reabierto_por_docente`, and SHALL NOT offer "Volver a abrir" on exercises that the teacher did not reopen in a partial correction request.

#### Scenario: Partial correction request in the exercise list
- **WHEN** an entrega of 3 exercises is returned with `ordenes=[2]`
- **THEN** exercise 2 shows the "A corregir" badge
- **AND** exercises 1 and 3 show as completed without a "Volver a abrir" button

#### Scenario: Legacy returned entrega without marks
- **WHEN** an entrega is `returned` and no exercise carries `reabierto_por_docente`
- **THEN** the list behaves as before this change (no badge is required, every exercise is pending)
