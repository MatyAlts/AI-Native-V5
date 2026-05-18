# academic-comisiones

## Purpose

Capability that owns the `Comision` entity within the academic plane: a scheduled offering of a `Materia` for a given `Periodo`, distinguished by `codigo` within the (`tenant_id`, `materia_id`, `periodo_id`) triple. Comisiones own their `cupo_maximo`, `horario`, `curso_config_hash`, `ai_budget_monthly_usd` and the human-readable `nombre` label used by frontends.

## Requirements

### Requirement: Comisiones expose human-readable nombre field

The `Comision` entity SHALL persist a `nombre` field (VARCHAR(100), NOT NULL, no UNIQUE constraint) in addition to the existing `codigo` field. All read endpoints (`GET /api/v1/comisiones`, `GET /api/v1/comisiones/{id}`, `GET /api/v1/comisiones/mis`) SHALL return `nombre` in their response payloads. Write endpoints (`POST /api/v1/comisiones`, `PATCH /api/v1/comisiones/{id}`) SHALL accept `nombre` with validation `min_length=1, max_length=100`.

The `nombre` field is a human-readable label intended for UI display (e.g. "A-Manana", "B-Tarde", "C-Noche"). It MUST NOT be part of any UNIQUE constraint — uniqueness remains scoped to `(tenant_id, materia_id, periodo_id, codigo)`.

#### Scenario: GET comisiones returns nombre

- **WHEN** a docente authenticated against tenant `aaaa...` issues `GET /api/v1/comisiones`
- **THEN** every item in the response array contains a non-empty `nombre` field of type string

#### Scenario: POST comision rejects empty nombre

- **WHEN** a docente_admin issues `POST /api/v1/comisiones` with body `{"codigo": "X", "nombre": "", "materia_id": "...", "periodo_id": "..."}`
- **THEN** the response is HTTP 422 with a validation error pointing at field `nombre` (min_length=1)

#### Scenario: Existing comisiones backfill nombre from codigo

- **WHEN** the Alembic migration `20260430_0001_comision_nombre` runs against a database with pre-existing rows in `comisiones`
- **THEN** every pre-existing row has `nombre = codigo` after the migration completes
- **AND** the column is `NOT NULL`

#### Scenario: Two comisiones with same nombre but distinct codigo are accepted

- **WHEN** a docente_admin creates two comisiones with the same `nombre = "Manana"` but different `codigo` values within the same `(tenant_id, materia_id, periodo_id)`
- **THEN** both creations succeed
- **AND** the existing `uq_comision_codigo` constraint applies only to `(tenant_id, materia_id, periodo_id, codigo)`

#### Scenario: PATCH comision updates nombre without touching codigo

- **WHEN** a docente_admin issues `PATCH /api/v1/comisiones/{id}` with body `{"nombre": "A-Manana"}`
- **THEN** the comision's `nombre` is updated and `codigo` remains unchanged
