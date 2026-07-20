## ADDED Requirements

### Requirement: tutor-service unit test coverage ≥ 75%

The package `apps/tutor-service` SHALL have unit test coverage of at least 75% as measured by `uv run pytest apps/tutor-service --cov=tutor_service --cov-report=term-missing`. New test files MUST cover the four prioritized hot-spots: `content_client.py`, `governance_client.py`, `clients.py`, and `routes/episodes.py`.

#### Scenario: Coverage measurement gates the change

- **WHEN** a developer runs `uv run pytest apps/tutor-service --cov=tutor_service`
- **THEN** the reported coverage is ≥ 75% (computed over `apps/tutor-service/src/tutor_service`)

#### Scenario: Hot-spot files have non-trivial coverage

- **WHEN** the coverage report is generated with `--cov-report=term-missing`
- **THEN** `content_client.py` and `governance_client.py` show ≥ 70% line coverage each

### Requirement: ctr-service unit test coverage ≥ 75%

The package `apps/ctr-service` SHALL have unit test coverage of at least 75%. New test files MUST cover the three prioritized hot-spots: `partition_worker.py`, `routes/events.py`, and a direct test of chain integrity tampering detection.

#### Scenario: Coverage measurement gates the change

- **WHEN** a developer runs `uv run pytest apps/ctr-service --cov=ctr_service`
- **THEN** the reported coverage is ≥ 75%

### Requirement: Direct chain integrity tampering test

The repo SHALL include `apps/ctr-service/tests/unit/test_chain_integrity.py` covering at minimum three scenarios that verify the central invariant of the thesis (CTR append-only chain detects tampering).

#### Scenario: Intact chain passes verification

- **WHEN** N=5 sequential events are constructed with `compute_self_hash` + `compute_chain_hash` correctly chained from `GENESIS_HASH`
- **THEN** the verification helper returns no integrity violations

#### Scenario: Mutated self_hash is detected

- **WHEN** the `self_hash` of an intermediate event in an N=5 chain is mutated by changing one character
- **THEN** the verification helper flags the chain as compromised, identifying the position of the breakage

#### Scenario: Mutated chain_hash is detected

- **WHEN** the `chain_hash` of an intermediate event in an N=5 chain is mutated by changing one character
- **THEN** the verification helper flags the chain as compromised

### Requirement: Deferred ADRs have grep-able code flags

The 3 ADRs declared as `Status: deferred` in `docs/adr/` (ADR-017 CCD embeddings semánticos, ADR-024 prompt reflexivo runtime, ADR-026 botón insertar código tutor) SHALL each have a comment-flag at the relevant code site using the format `# Deferred: ADR-XXX / <milestone> — <one-line reason>`. The prefix `# Deferred:` MUST be grep-able and uniform.

#### Scenario: Grep finds all three flags

- **WHEN** a developer runs `rg "^# Deferred: ADR-(017|024|026)" apps/ packages/ web-student/ web-teacher/ web-admin/`
- **THEN** at least three matches are returned, one per ADR ID, each on the corresponding code site

#### Scenario: Flag is at the relevant code site

- **WHEN** a maintainer reads the file containing the deferred behavior (e.g., `apps/classifier-service/src/classifier_service/services/ccd.py` for ADR-017)
- **THEN** the `# Deferred:` comment is visually adjacent to the implementation that the ADR defers (within ~10 lines)

### Requirement: BUGS-PILOTO.md GAP-9 updated with post-epic coverage

The file `BUGS-PILOTO.md` SHALL have its GAP-9 (coverage ratchet plan) entry updated with the post-epic coverage numbers for `tutor-service` and `ctr-service`, plus a note about Fase B remaining toward target 85%.

#### Scenario: Numbers are current

- **WHEN** a maintainer reads GAP-9 after the epic is archived
- **THEN** the entry shows the coverage measurement from THIS epic (date + numbers) and a remaining gap pointer to Fase B

### Requirement: Full repo test suite passes after epic

After implementing the changes from this epic, `uv run pytest apps packages --ignore=apps/enrollment-service` SHALL pass with exit code 0.

#### Scenario: Smoke regression check

- **WHEN** the smoke command is run after the epic is implemented
- **THEN** all collected tests pass (no failures, no errors, skips are acceptable if pre-existing)

### Requirement: No production logic changes

The epic SHALL NOT modify any code in `apps/<svc>/src/<svc_snake>/services/`, `routes/`, `workers/`, `models/`, or equivalent production paths, EXCEPT for adding the three `# Deferred:` comments described above. All other changes MUST be additive (new test files only).

#### Scenario: Diff verification

- **WHEN** a maintainer runs `git diff --name-only` between the pre-epic and post-epic state
- **THEN** the only files modified outside `tests/` directories are the three files containing `# Deferred:` comments and `BUGS-PILOTO.md`

### Requirement: Optional verify_chain helper extraction is allowed

If the existing `apps/ctr-service/src/ctr_service/workers/integrity_checker.py` has its chain verification logic inline (not extractable as a pure function), the epic MAY refactor it to expose a pure helper `verify_chain(events: list[Event]) -> ChainStatus` (or equivalent name) that the new `test_chain_integrity.py` consumes. This refactor SHALL preserve existing worker behavior bit-for-bit.

#### Scenario: Refactor preserves worker behavior

- **WHEN** the helper is extracted and the worker is updated to call it
- **THEN** existing integration tests of the worker (if any) continue to pass without modification
