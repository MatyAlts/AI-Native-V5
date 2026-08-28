## ADDED Requirements

### Requirement: Correction is requested per exercise by a teacher
The system SHALL expose `POST /api/v1/entregas/{id}/correccion-ia`, accepting a **required** `ejercicio_orden`. Exactly that exercise SHALL be corrected. The endpoint SHALL return 202 with the identifier of the created correction.

`ejercicio_orden` is required rather than optional-meaning-all: each correction is a paid call, and a request that spends N of them must be an explicit decision, not the default of an omitted field. A teacher who wants to correct every exercise makes N requests and sees N previews.

Only teaching roles SHALL be able to request a correction. Students SHALL NOT have access to this endpoint or to its results.

#### Scenario: Teacher corrects a single exercise
- **WHEN** a teacher posts with `ejercicio_orden: 2`
- **THEN** the API SHALL return 202 and only that exercise SHALL be sent to Active-IA

#### Scenario: Student cannot request or read a correction
- **WHEN** a student calls the correction endpoints for their own entrega
- **THEN** the API SHALL deny access and no correction data SHALL be returned

#### Scenario: Teacher of another comision is denied
- **WHEN** a teacher who does not belong to the entrega's comision requests a correction
- **THEN** the API SHALL return 404, not 403

### Requirement: Tests are re-executed and their result sent as evidence
Before sending an exercise to Active-IA, the system SHALL re-execute that exercise's test cases against the persisted artefacto using the platform sandbox, and SHALL include the detailed result — per case: input, expected output, obtained output, and pass or fail — in the payload.

The system SHALL NOT reuse the result of a previous execution: the detailed outcome is held in Redis with a short TTL and the CTR retains only aggregate counts.

The system SHALL store the sent result alongside the correction, so the returned grade can be audited against the evidence it was based on.

#### Scenario: Tests run before the correction is sent
- **WHEN** a correction is requested for an exercise
- **THEN** its test cases SHALL be executed against the persisted artefacto
- **AND** the detailed result SHALL be sent together with the source code

#### Scenario: The sent evidence is retained
- **WHEN** a correction completes
- **THEN** the test result that was sent SHALL be stored with the correction record

#### Scenario: Code that does not compile is still sent, flagged
- **WHEN** the artefacto fails to compile during the pre-execution
- **THEN** the correction SHALL still be sent to Active-IA
- **AND** the payload SHALL carry the compilation state explicitly (`compila`, `error_compilacion`)
- **AND** the teacher's result view SHALL warn that the grade came from code that never ran

> Revised 2026-08-19. The original scenario cut the flow to avoid paying for a
> correction on broken code. A missing semicolon is not a reason to leave the
> student without feedback: the qualitative judgement on the *design* is still
> useful, and it is exactly what a compiler does not give. What replaces the
> gate is that the compilation state travels explicitly, so the engine can
> avoid closing "it works" criteria that no run backs.

### Requirement: Preview does not consume quota
When invoked with `confirmado=false`, the endpoint SHALL return what would be sent — exercise, rubric and its synchronization state, test cases to be run, and payload size — without executing tests, contacting Active-IA or consuming quota.

#### Scenario: Preview shows the payload without spending
- **WHEN** a teacher requests a correction with `confirmado=false`
- **THEN** the API SHALL describe what would be sent
- **AND** no call to Active-IA SHALL be made and no quota SHALL be consumed

### Requirement: Infrastructure failures are never grades
A timeout, a `GEMINI_OVERLOADED` response, or any transport error SHALL be recorded as an infrastructure failure with its cause. Such an outcome SHALL NOT produce a `nota_100` value, and SHALL be presented to the teacher as a service problem rather than as a result about the student's work.

#### Scenario: Overloaded engine produces no grade
- **WHEN** Active-IA responds with `GEMINI_OVERLOADED`
- **THEN** the correction SHALL be marked as an infrastructure failure with no grade
- **AND** the UI SHALL state that it is not a problem with the student's submission

#### Scenario: A rejection is distinguished from a failure
- **WHEN** Active-IA rejects the submission with a client error
- **THEN** the UI SHALL present it distinctly from an infrastructure failure

### Requirement: Correction requests are idempotent
Repeated requests for the same exercise, rubric and artefacto hash SHALL NOT create duplicate corrections nor duplicate uploads. A request matching a completed correction SHALL return that correction; one matching a running correction SHALL return the running one.

#### Scenario: Double click yields one correction
- **WHEN** a teacher triggers the same correction twice in a row
- **THEN** only one correction SHALL exist and only one upload SHALL have been made

#### Scenario: New submission after return is a new correction
- **WHEN** an entrega is returned, resubmitted with different code, and corrected again
- **THEN** a new correction SHALL be created, because the artefacto hash changed

### Requirement: Feature is gated and quota fails closed
The capability SHALL be governed by a kill switch defaulting to disabled. A per-teacher daily quota SHALL be enforced, and SHALL fail closed: if the counter cannot be read, the request SHALL be rejected rather than allowed.

#### Scenario: Disabled feature rejects requests
- **WHEN** the kill switch is disabled and a correction is requested
- **THEN** the API SHALL reject the request stating the feature is disabled

#### Scenario: Quota counter unavailable rejects the request
- **WHEN** the quota counter cannot be read
- **THEN** the request SHALL be rejected rather than permitted by default

#### Scenario: Exceeded quota is reported as such
- **WHEN** a teacher exceeds the daily quota
- **THEN** the API SHALL reject the request identifying the quota as the cause

### Requirement: Long-running corrections survive and are reconciled
Corrections SHALL run asynchronously with their state persisted, and the client SHALL poll for the outcome. A reconciler SHALL pick up corrections left running beyond a threshold and resume polling, so that a process restart does not leave a correction permanently in progress.

Database sessions SHALL be short-lived within the background work, and concurrent corrections SHALL be bounded, so that the connection pool is not exhausted.

#### Scenario: Correction outcome is polled
- **WHEN** a correction is accepted with 202
- **THEN** the client SHALL be able to poll its state until it completes or fails

#### Scenario: Restart does not strand a correction
- **WHEN** the service restarts while a correction is running
- **THEN** the reconciler SHALL resume it or mark it failed, and it SHALL NOT remain running indefinitely

### Requirement: Result is presented as a suggestion, never written as a grade
The system SHALL display, per exercise, the returned grade over 100 and its breakdown, together with the rubric used. It SHALL compute the weighted average using each exercise's weight in the TP and SHALL show the calculation, not only its result.

When any exercise of the entrega lacks a correction, the system SHALL NOT compute an average; it SHALL present the partial result and identify which exercises are missing.

The system SHALL offer an action that fills the grade field with the proposed value converted to the local scale, without saving it. The system SHALL NOT write to `calificaciones` as a consequence of a correction.

#### Scenario: Weighted average is shown with its calculation
- **WHEN** every exercise of the entrega has a completed correction
- **THEN** the weighted average SHALL be displayed together with the per-exercise grades and weights that produced it

#### Scenario: Missing correction prevents an average
- **WHEN** at least one exercise has no completed correction
- **THEN** no average SHALL be shown, and the missing exercises SHALL be named

#### Scenario: Using the suggestion does not save it
- **WHEN** a teacher activates "use as base"
- **THEN** the grade field SHALL be populated and focused
- **AND** no grade SHALL be persisted until the teacher explicitly grades

#### Scenario: Breakdown that does not add up is flagged
- **WHEN** the sum of the returned criteria differs from the returned total
- **THEN** the UI SHALL flag the discrepancy instead of presenting the total as reliable
