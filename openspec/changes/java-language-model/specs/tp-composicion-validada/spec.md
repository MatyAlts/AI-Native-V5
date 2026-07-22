## ADDED Requirements

### Requirement: Una tarea práctica se publica solo si su composición es válida

`POST /api/v1/tareas-practicas/{id}/publish` SHALL validar la composición de la TP antes de cambiar su estado a `published`. Una TP inválida NO SHALL llegar al alumno. Hoy `publish()` solo verifica que el estado sea `draft`, y existe un validador escrito para esto que nunca se invoca.

La validación SHALL resolver los ejercicios asociados mediante una consulta explícita, nunca iterando la relación diferida — el driver asíncrono falla con `MissingGreenlet` en ese camino.

#### Scenario: Publicar una TP bien compuesta

- **WHEN** se publica una TP cuyos ejercicios tienen órdenes únicos, sin duplicados, y pesos que suman 1.0
- **THEN** la TP pasa a estado `published`

#### Scenario: Rechazar pesos que no suman 1.0

- **WHEN** se intenta publicar una TP cuyos `peso_en_tp` suman 0.8
- **THEN** la API responde 422 indicando la suma real
- **AND** la TP permanece en estado `draft`

#### Scenario: Rechazar órdenes duplicados

- **WHEN** se intenta publicar una TP con dos ejercicios en el mismo `orden`
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: Rechazar ejercicios duplicados

- **WHEN** se intenta publicar una TP que referencia dos veces el mismo `ejercicio_id`
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: La validación no revienta por carga diferida

- **WHEN** se publica una TP compuesta por ejercicios de banco
- **THEN** la validación resuelve los ejercicios sin lanzar `MissingGreenlet`

### Requirement: Una tarea práctica publicada nunca está vacía

Una TP SHALL tener contenido resoluble para publicarse: al menos un ejercicio de banco asociado, o casos de prueba propios si es monolítica. Una TP sin ninguna de las dos cosas NO SHALL publicarse.

Esta regla es adicional al validador de composición existente, que retorna conforme ante una lista de ejercicios vacía y por lo tanto no cubre este caso.

#### Scenario: Rechazar una TP sin ejercicios ni casos de prueba propios

- **WHEN** se intenta publicar una TP sin ejercicios asociados y sin `test_cases` propios
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: Aceptar una TP monolítica sin ejercicios de banco

- **WHEN** se publica una TP sin ejercicios asociados pero con `test_cases` propios
- **THEN** la TP pasa a estado `published`

### Requirement: Una tarea práctica tiene un único lenguaje

Todos los ejercicios asociados a una TP SHALL compartir el mismo `language`, y ese lenguaje SHALL coincidir con el de la TP. El editor del alumno no puede cargar dos entornos de ejecución en un mismo episodio, de modo que una TP mixta es irresoluble, no meramente inconsistente.

La regla SHALL aplicarse en dos momentos: al agregar un ejercicio a la TP, para bloquear la mezcla en el momento de componer; y al publicar, como red final.

#### Scenario: Rechazar al agregar un ejercicio de otro lenguaje

- **WHEN** un docente agrega un ejercicio con `language = "java"` a una TP cuyos ejercicios son `python`
- **THEN** la API responde 422 nombrando ambos lenguajes
- **AND** la TP queda sin modificar

#### Scenario: Rechazar un ejercicio que no coincide con el lenguaje de la TP

- **WHEN** un docente agrega un ejercicio `python` a una TP declarada `java`, aún sin otros ejercicios
- **THEN** la API responde 422
- **AND** la TP queda sin modificar

#### Scenario: Aceptar un ejercicio del mismo lenguaje

- **WHEN** un docente agrega un ejercicio `java` a una TP `java`
- **THEN** el ejercicio queda asociado a la TP

#### Scenario: Rechazar al publicar una TP con lenguajes mezclados

- **WHEN** se intenta publicar una TP que quedó con ejercicios de distintos lenguajes
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: Las TPs ya publicadas no se revalidan retroactivamente

- **WHEN** existe una TP publicada antes de esta change que violaría alguna de estas reglas
- **THEN** la TP conserva su estado `published` y sigue siendo resoluble por los alumnos
- **AND** la validación solo se aplica si esa TP se vuelve a publicar
