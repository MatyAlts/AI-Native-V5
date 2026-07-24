## ADDED Requirements

### Requirement: Lenguaje de programación como atributo del ejercicio

Todo `Ejercicio` del banco SHALL declarar el lenguaje de programación en el que se resuelve, mediante un campo `language` no nulo. El sistema SHALL tratar `python` como el lenguaje por omisión para preservar la semántica del banco existente, que es íntegramente Python.

#### Scenario: Ejercicio existente conserva su semántica tras la migración

- **WHEN** se aplica la migración sobre una base con ejercicios creados antes de este cambio
- **THEN** cada ejercicio existente queda con `language = "python"` sin requerir backfill manual
- **AND** ninguna fila queda con `language` nulo

#### Scenario: Crear un ejercicio sin declarar lenguaje

- **WHEN** un docente crea un ejercicio vía `POST /api/v1/ejercicios` sin incluir `language`
- **THEN** el ejercicio se crea con `language = "python"`

#### Scenario: Crear un ejercicio de Java

- **WHEN** un docente crea un ejercicio con `language = "java"`
- **THEN** el ejercicio se persiste con ese lenguaje
- **AND** `GET /api/v1/ejercicios/{id}` lo devuelve en la respuesta

#### Scenario: Rechazar un lenguaje no soportado

- **WHEN** se envía `language = "cobol"` al crear o editar un ejercicio
- **THEN** la API responde 422 sin persistir nada

### Requirement: Lenguaje de programación como atributo de la tarea práctica

Toda `TareaPractica` SHALL declarar un campo `language` no nulo con la misma semántica y el mismo valor por omisión que `Ejercicio`. Esto cubre las TPs monolíticas, que llevan su propio `inicial_codigo` y `test_cases` sin componerse de ejercicios del banco.

#### Scenario: TP existente conserva su semántica tras la migración

- **WHEN** se aplica la migración sobre una base con TPs creadas antes de este cambio
- **THEN** cada TP existente queda con `language = "python"`

#### Scenario: TP monolítica de Java

- **WHEN** un docente crea una TP con `language = "java"` y sus propios `test_cases`, sin ejercicios de banco
- **THEN** la TP se persiste con ese lenguaje

### Requirement: Filtrado del banco de ejercicios por lenguaje

`GET /api/v1/ejercicios` SHALL aceptar un parámetro opcional `language` que restrinja el resultado a los ejercicios de ese lenguaje. La ausencia del parámetro SHALL devolver ejercicios de todos los lenguajes, preservando el comportamiento actual.

#### Scenario: Filtrar por lenguaje

- **WHEN** se solicita `GET /api/v1/ejercicios?language=java`
- **THEN** la respuesta contiene únicamente ejercicios con `language = "java"`

#### Scenario: Sin filtro devuelve todo

- **WHEN** se solicita `GET /api/v1/ejercicios` sin el parámetro
- **THEN** la respuesta contiene ejercicios de todos los lenguajes

#### Scenario: El filtro compone con los existentes

- **WHEN** se solicita `GET /api/v1/ejercicios?language=java&dificultad=basica`
- **THEN** la respuesta contiene solo ejercicios que cumplen ambas condiciones

### Requirement: Tipo de caso de prueba para Java

El contrato de casos de prueba SHALL admitir el tipo `junit_assert`, además de los existentes `stdin_stdout` y `pytest_assert`. El tipo SHALL ser admitido tanto en los casos de prueba de un `Ejercicio` como en los de una `TareaPractica` monolítica, que hoy siguen caminos de validación distintos.

#### Scenario: Caso de prueba junit_assert en un ejercicio

- **WHEN** se crea un ejercicio con un caso de prueba de tipo `junit_assert`
- **THEN** el ejercicio se persiste sin error de validación

#### Scenario: Caso de prueba junit_assert en una TP monolítica

- **WHEN** se crea una TP con un caso de prueba de tipo `junit_assert` en su propio campo `test_cases`
- **THEN** la TP se persiste sin error de validación

#### Scenario: Rechazar un tipo de caso de prueba inexistente

- **WHEN** se envía un caso de prueba con tipo `mocha_assert` en un ejercicio o en una TP
- **THEN** la API responde 422 sin persistir nada

### Requirement: Neutralidad respecto de la trazabilidad de la tesis

La incorporación del campo `language` NO SHALL alterar el hash de configuración del clasificador, las etiquetas N1–N4 de eventos históricos, ni la versión del etiquetador. El clasificador no consume el lenguaje en ningún punto de su pipeline.

#### Scenario: El hash de configuración del clasificador no cambia

- **WHEN** se aplica esta change completa
- **THEN** `classifier_config_hash` para un mismo `tree_version` y `reference_profile` es idéntico al anterior
- **AND** `LABELER_VERSION` permanece en su valor vigente

#### Scenario: Las clasificaciones históricas siguen siendo reproducibles

- **WHEN** se recalcula una clasificación de un episodio anterior a esta change
- **THEN** el resultado es bit-a-bit idéntico al persistido
