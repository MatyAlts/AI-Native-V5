## ADDED Requirements

### Requirement: Demo seed produces episodes with template-resolvable problema_id

The `scripts/seed-3-comisiones.py` script SHALL set `Episode.problema_id` to a UUID that exists as a row in `tareas_practicas` and whose `template_id` field is populated. Each comision SHALL have at least 2 distinct `problema_id` values across its episodes (round-robin distribution between the 2 templates per comision), guaranteeing that every (student, template) pair accumulates `>= MIN_EPISODES_FOR_LONGITUDINAL = 3` episodes when the cohort has `>= 6 episodes per student`.

The legacy hardcoded constant `PROBLEMA_ID = "99999999-9999-9999-9999-999999999999"` MUST NOT appear in any `Episode.problema_id` row produced by the seed.

#### Scenario: Episode.problema_id resolves to a real TareaPractica

- **WHEN** the seed completes successfully
- **AND** the operator runs `SELECT DISTINCT problema_id FROM episodes WHERE tenant_id='aaaa...'` against `ctr_store`
- **THEN** the result returns 6 distinct UUIDs (one per TP instance: 3 comisiones x 2 templates per comision)
- **AND** none of them equals the legacy `99999999-9999-9999-9999-999999999999`

#### Scenario: CII evolution longitudinal returns non-trivial slope

- **WHEN** a docente requests `GET /api/v1/analytics/student/{any seeded student}/cii-evolution-longitudinal?comision_id={any seeded comision}` after seed
- **THEN** the response contains a `slope_per_template` map with at least 1 template entry having `insufficient_data: false` and a non-null `slope` value

#### Scenario: Cohort cuartiles meets privacy threshold

- **WHEN** a docente requests `GET /api/v1/analytics/cohort/{any seeded comision}/cii-quartiles` after seed
- **THEN** the response returns valid quartile statistics (no `insufficient_data: true`) since each comision has 6 students (>= MIN_STUDENTS_FOR_QUARTILES = 5)

### Requirement: Demo seed prompt_system_version aligns with runtime manifest

The `scripts/seed-3-comisiones.py` script SHALL register CTR events with `prompt_system_version` matching `Settings.default_prompt_version` in `apps/tutor-service/src/tutor_service/config.py` and the `tutor` entry of `ai-native-prompts/manifest.yaml`. The corresponding `prompt_system_hash` SHALL match the SHA-256 declared in `ai-native-prompts/prompts/tutor/{version}/manifest.yaml`.

This invariant (G12 in CLAUDE.md) keeps the manifest declarative source of truth aligned with what the seed and runtime emit. Bumping the runtime version requires bumping the seed in lockstep.

#### Scenario: Seed emits only the runtime-aligned prompt_system_version

- **WHEN** the seed completes successfully
- **AND** the operator runs `SELECT DISTINCT prompt_system_version FROM events WHERE tenant_id='aaaa...'` against `ctr_store`
- **THEN** the result contains exactly one value, equal to the current `Settings.default_prompt_version` (today: `v1.0.1`)

#### Scenario: Active configs endpoint matches first event sample

- **WHEN** the operator queries `GET /api/v1/active_configs` after seed
- **AND** queries `SELECT prompt_system_version FROM events WHERE tenant_id='aaaa...' ORDER BY ts ASC LIMIT 1`
- **THEN** both return the same prompt version string

### Requirement: Demo seed populates comision nombre

The `scripts/seed-3-comisiones.py` script SHALL persist the `nombre` field for each comision it creates, with values `"A-Manana"`, `"B-Tarde"`, `"C-Noche"` for comisiones with codigos `"A"`, `"B"`, `"C"` respectively. This requires the `comisiones.nombre` column from capability `academic-comisiones` to exist and accept the values.

#### Scenario: Frontend selector displays human label

- **WHEN** a docente loads the comision selector in `web-teacher` after seed and migration
- **THEN** the dropdown shows `"A-Manana"` instead of `"A"` for that comision
- **AND** equivalently for `"B-Tarde"` and `"C-Noche"`
