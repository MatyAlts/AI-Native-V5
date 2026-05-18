## ADDED Requirements

### Requirement: TareaPractica almacena test cases como JSONB

El sistema SHALL persistir test cases asociados a una TareaPractica como columna `test_cases JSONB DEFAULT '[]'` en `tareas_practicas` y `tareas_practicas_templates`. Cada test case SHALL contener: `id` (UUID), `name` (string), `type` (`stdin_stdout` | `pytest_assert`), `code` (string), `expected` (string), `is_public` (boolean), `weight` (integer ≥1).

#### Scenario: Test cases viajan en versionado de TP

- **WHEN** un docente crea una nueva versión de una TP publicada con `POST /api/v1/tareas-practicas/{id}/new-version`
- **THEN** la nueva instancia SHALL clonar `test_cases` íntegro del padre
- **AND** modificar `test_cases` SHALL setear `has_drift=true` solo en la instancia, sin propagarse al template

#### Scenario: Template auto-instancia con test cases

- **WHEN** un docente crea un `TareaPracticaTemplate` con N test cases
- **THEN** las instancias auto-creadas en cada comisión de la materia+periodo SHALL heredar los N test cases con `is_public` y `weight` preservados

### Requirement: Endpoint filtra test cases hidden por rol

El sistema SHALL exponer `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden={bool}` que retorna test cases respetando el rol del caller. Estudiantes SHALL recibir `403` si pasan `include_hidden=true`. Docentes/JTP/auxiliares SHALL poder consultar con `include_hidden=true`. Cuando `include_hidden=false`, el response SHALL omitir cualquier test con `is_public=false`.

#### Scenario: Estudiante intenta acceder a tests hidden

- **WHEN** un estudiante autenticado pega `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden=true`
- **THEN** el sistema SHALL retornar `403 Forbidden`

#### Scenario: Docente accede a tests completos

- **WHEN** un docente autenticado pega `GET /api/v1/tareas-practicas/{id}/test-cases?include_hidden=true`
- **THEN** el response SHALL incluir todos los test cases (públicos + hidden) con sus campos completos

### Requirement: Ejecución de tests en Pyodide client-side

El sistema SHALL permitir al alumno ejecutar tests públicos en Pyodide dentro del browser sin round-trip al servidor. Tests hidden SHALL NO ser enviados al cliente — quedan deferidos a piloto-2 cuando se implemente `sandbox-service` server-side.

#### Scenario: Alumno corre tests públicos

- **WHEN** el alumno escribe código y presiona "Correr tests" en `web-student/EpisodePage`
- **THEN** Pyodide SHALL ejecutar los test cases con `is_public=true` y mostrar pass/fail por test
- **AND** la ejecución SHALL ser cancelable si el alumno presiona "Detener"

#### Scenario: Tests hidden no salen del servidor en piloto-1

- **WHEN** el cliente pide test cases via `GET /api/v1/tareas-practicas/{id}/test-cases` (sin `include_hidden`)
- **THEN** el response SHALL omitir test cases con `is_public=false` aunque existan en la TP

### Requirement: Evento CTR `tests_ejecutados` con conteos agregados

El sistema SHALL emitir un evento CTR `tests_ejecutados` cada vez que el alumno corre tests, con payload conteniendo: `test_count_total`, `test_count_passed`, `test_count_failed`, `tests_publicos`, `tests_hidden` (siempre 0 en piloto-1), `chunks_used_hash` (propagado del último `prompt_enviado` del episodio), `ejecucion_ms`. La lista detallada de tests individuales SHALL NO incluirse — solo conteos.

#### Scenario: Evento se appendea al CTR sin mutar eventos previos

- **WHEN** el alumno corre tests y 2 de 5 fallan
- **THEN** el ctr-service SHALL appendear un evento `tests_ejecutados` con `test_count_total=5, test_count_passed=3, test_count_failed=2`
- **AND** el `self_hash` y `chain_hash` SHALL computarse según las fórmulas canónicas (sort_keys=true, separators=(",", ":"), sin ensure_ascii=False para self_hash)
- **AND** ningún evento previo SHALL mutar

### Requirement: Classifier IGNORA resultados de tests hidden

El classifier-service SHALL excluir explícitamente cualquier feature derivada de test cases con `is_public=false`. Solo tests públicos pueden contribuir a features del classifier. Esta exclusión SHALL ser auditable via `classifier_config_hash` (configuración versionada).

#### Scenario: Pipeline classifier ignora hidden

- **WHEN** el classifier procesa un episodio con eventos `tests_ejecutados` que incluyen tests hidden
- **THEN** el feature extractor SHALL filtrar `tests_hidden=0` siempre en piloto-1 (solo público cuenta)
- **AND** el `classifier_config_hash` SHALL reflejar la decisión de exclusión via flag versionado en config

### Requirement: Etiquetado N4 de `tests_ejecutados`

El event_labeler SHALL etiquetar `tests_ejecutados` como N4 si todos los tests pasaron Y el tiempo desde el último `tutor_respondio` es ≥60s (apropiación reflexiva). En cualquier otro caso SHALL etiquetar como N3 (validación funcional). Esta regla SHALL bumpear `LABELER_VERSION` a 1.2.0.

#### Scenario: Tests todos pass, sin tutor reciente → N4

- **WHEN** el labeler v1.2.0 procesa un `tests_ejecutados` con `test_count_failed=0` y el último `tutor_respondio` ocurrió hace 120s
- **THEN** el evento SHALL etiquetarse como N4

#### Scenario: Tests con fallos → N3

- **WHEN** el labeler v1.2.0 procesa un `tests_ejecutados` con `test_count_failed=2`
- **THEN** el evento SHALL etiquetarse como N3 independientemente del timing del tutor
