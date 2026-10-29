## ADDED Requirements

### Requirement: Reopened exercise shows the code already submitted
When the web-student hydrates the episode of an exercise of a multi-exercise TP, and there is neither a local draft of that same episode nor a code snapshot in the episode state, the editor SHALL start with the code the student already submitted for that same exercise in the entrega's sealed submission artefact, before falling back to the teacher's scaffolds or the language placeholder. Loading that code SHALL NOT emit any CTR event, and SHALL NOT reopen any closed episode. Code submitted for a different exercise SHALL never be used.

#### Scenario: Broken reopening chain falls back to the submitted code
- **WHEN** a student opens a reopened exercise whose episode state has no `last_code_snapshot`
- **AND** the entrega's submission artefact has non-empty code for that exercise's `orden` and `ejercicio_id`
- **THEN** the editor starts with that submitted code
- **AND** no `edicion_codigo` event is emitted until the student types

#### Scenario: Own code still wins
- **WHEN** the episode state has a `last_code_snapshot`, or there is a local draft of the same episode
- **THEN** the editor starts with that code and the submission artefact is not requested

#### Scenario: Artefact of another exercise is ignored
- **WHEN** the submission artefact only has code for a different `orden` or `ejercicio_id`
- **THEN** the editor falls back to the teacher's scaffold or the language placeholder, as before this change

#### Scenario: Artefact unavailable
- **WHEN** the artefact request fails, the entrega is `legacy`, or the code is empty
- **THEN** the editor falls back to the teacher's scaffold or the language placeholder, as before this change

### Requirement: Closing an unchanged reopened exercise completes it with the code shown
When the student closes the episode of an exercise of a multi-exercise TP without having edited code in that episode, there is no local draft, and the editor started with the student's own code (episode snapshot, including the code inherited on reopening, or the submitted code), the web-student SHALL store that code as the exercise's local draft and mark the exercise as completed. This SHALL hold for every path that closes the exercise (closing the episode, "Siguiente ejercicio", closing the reflection modal) and SHALL NOT add, remove or change any CTR event. An exercise whose editor shows only the teacher's scaffold or the language placeholder, or that the student edited and left empty, SHALL NOT be marked completed.

#### Scenario: Returned TP, reopened exercise closed without editing
- **WHEN** an entrega is `returned`, the student opens exercise 1 (a new episode) whose editor starts with the student's own previous code, does not type, and closes the episode
- **THEN** exercise 1 is marked completed for the closing episode
- **AND** exercise 2 is available in the exercise list

#### Scenario: Re-submit sends the code that was shown
- **WHEN** exercise 1 was completed by closing it unchanged
- **AND** the student re-submits the TP from the same browser
- **THEN** the submit request carries, for exercise 1, the code the editor showed

#### Scenario: Exercise with no own code is still not completed
- **WHEN** the student closes an exercise without editing, there is no local draft, and the editor started with the teacher's scaffold or the language placeholder
- **THEN** the exercise is NOT marked completed and the next exercise stays locked

#### Scenario: Edited-to-empty exercise does not fall back to the shown code
- **WHEN** the student edited code in the episode and left the editor empty before closing
- **THEN** the shown code is NOT used and the exercise is NOT marked completed

#### Scenario: Only one mark across the closing paths
- **WHEN** the student closes the episode and then clicks "Siguiente ejercicio"
- **THEN** exactly one completion request is sent
