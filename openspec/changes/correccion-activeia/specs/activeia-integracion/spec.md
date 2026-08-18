## ADDED Requirements

### Requirement: Per-teacher Active-IA credentials stored encrypted
The system SHALL store Active-IA credentials per teacher in a dedicated table, with the password encrypted using AES-256-GCM via `packages/platform-ops/src/platform_ops/crypto.py` and a dedicated `ACTIVEIA_MASTER_KEY`. The system SHALL NOT store any fragment of the plaintext password, including a fingerprint of its last characters.

Credentials SHALL NOT be stored in `byok_keys`: its scope is tenant/materia rather than per user, and it persists the last four plaintext characters.

#### Scenario: Teacher connects a Active-IA account
- **WHEN** a teacher submits username and password to `POST /api/v1/activeia/credenciales`
- **THEN** the password SHALL be stored encrypted and never returned in any response

#### Scenario: Password never appears in logs or responses
- **WHEN** any request touching credentials succeeds or fails
- **THEN** the plaintext password SHALL NOT appear in logs, error details or responses

#### Scenario: Only one active credential per teacher
- **WHEN** a teacher saves a credential while another active one exists
- **THEN** the previous one SHALL be revoked and the new one SHALL become the active credential

### Requirement: Credentials validated with a real login on save
The system SHALL perform a real `POST /auth/login` against Active-IA when saving a credential, and SHALL reject the save if authentication fails, reporting an authentication error explicitly.

The system SHALL NOT treat an empty rubric listing as evidence of a valid credential: Active-IA returns an empty list both when a materia has no rubrics and when authentication fails.

#### Scenario: Invalid credentials rejected at save time
- **WHEN** a teacher saves credentials that Active-IA rejects
- **THEN** the API SHALL return an error stating that the credentials are invalid
- **AND** the message SHALL NOT say that no rubrics were found

#### Scenario: Valid credentials record the successful login
- **WHEN** the login succeeds
- **THEN** `last_login_at` and `last_login_ok` SHALL be recorded

### Requirement: TP structure synchronized to Active-IA
When a TP is published, the system SHALL push to Active-IA the TP with its exercises nested, each carrying its `rubrica`, its `test_cases` and its `peso_en_tp`, identified by an `external_ref` owned by AI-Native.

The system SHALL store the identifier returned by Active-IA and a hash of the pushed rubric, so that later divergence can be detected without comparing full documents.

#### Scenario: Publishing a TP pushes its structure
- **WHEN** a teacher publishes a TP whose comision has a valid Active-IA credential
- **THEN** the TP and each of its exercises SHALL be pushed with rubric, test cases and weight
- **AND** the returned identifier and rubric hash SHALL be stored per exercise

#### Scenario: Editing a rubric marks the exercise as out of sync
- **WHEN** an exercise rubric changes after having been synchronized
- **THEN** the stored hash SHALL no longer match and the exercise SHALL be reported as out of sync

#### Scenario: Synchronization state is visible per exercise
- **WHEN** a teacher opens the Active-IA section
- **THEN** each exercise SHALL show one of: synchronized, out of sync, or not synchronized

#### Scenario: Test cases are sent as part of the statement
- **WHEN** an exercise is synchronized
- **THEN** its test cases SHALL be included with their input and expected output, as part of the exercise definition

### Requirement: Active-IA client tolerates its measured latency
The Active-IA HTTP client SHALL use a timeout of at least 90 seconds, cache its token in memory, and re-authenticate on a 401 response.

#### Scenario: Slow response within the measured range succeeds
- **WHEN** Active-IA answers after 40 seconds
- **THEN** the call SHALL succeed rather than time out

#### Scenario: Expired token triggers a single re-login
- **WHEN** a request returns 401
- **THEN** the client SHALL re-authenticate once and retry the request
