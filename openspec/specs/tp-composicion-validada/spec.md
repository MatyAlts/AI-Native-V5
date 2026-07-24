## ADDED Requirements

### Requirement: Una tarea práctica se publica solo si su composición es válida

`POST /api/v1/tareas-practicas/{id}/publish` SHALL validar la composición de la TP antes de cambiar su estado a `published`. Una TP inválida NO SHALL llegar al alumno. Hoy `publish()` solo verifica que el estado sea `draft`.

La validación SHALL resolver los ejercicios asociados mediante una consulta explícita con carga anticipada, nunca iterando la relación diferida — el driver asíncrono falla en ese camino.

La validación NO SHALL exigir que los pesos de los ejercicios sumen un valor determinado. Ver "Alcance deliberadamente excluido" al final de este documento.

#### Scenario: Publicar una TP bien compuesta

- **WHEN** se publica una TP cuyos ejercicios tienen órdenes únicos y sin duplicados
- **THEN** la TP pasa a estado `published`

#### Scenario: Rechazar órdenes duplicados

- **WHEN** se intenta publicar una TP con dos ejercicios en el mismo `orden`
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: Rechazar ejercicios duplicados

- **WHEN** se intenta publicar una TP que referencia dos veces el mismo `ejercicio_id`
- **THEN** la API responde 422
- **AND** la TP permanece en estado `draft`

#### Scenario: Los pesos no condicionan la publicación

- **WHEN** se publica una TP cuyos pesos de ejercicio suman un valor distinto de 1.0
- **THEN** la TP pasa a estado `published`
- **AND** no se emite ningún error relativo a los pesos

#### Scenario: La validación no falla por carga diferida

- **WHEN** se publica una TP compuesta por ejercicios de banco
- **THEN** la validación resuelve los ejercicios sin error del driver asíncrono

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

#### Scenario: Aceptar una TP con un único ejercicio

- **WHEN** se publica una TP con exactamente un ejercicio asociado
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

## Alcance deliberadamente excluido

**La regla de que los pesos de los ejercicios sumen 1.0 queda fuera de esta especificación**, aunque el validador existente la contempla y nunca se haya invocado.

Medición sobre la base del piloto (2026-07-23), previa a escribir código:

- **169 de 169** asociaciones ejercicio–TP tienen peso `1.0000`. Sin excepciones.
- **25 de 27** TPs publicadas tienen una suma de pesos igual a su cantidad de ejercicios, no a 1.0.
- Las 2 restantes cumplen la regla por accidente: tienen un único ejercicio, de modo que 1 × 1.0 da 1.0.
- El valor proviene del formulario del docente, que propone `1.0` y nadie modifica.
- **Ningún cálculo de calificación consume el campo**: el servicio de evaluación no lo menciona en ningún punto.

Aplicar la regla habría impedido republicar prácticamente todas las TPs del piloto, para proteger la consistencia de un campo que no participa de ningún cálculo. La decisión de qué hacer con ese campo —implementar la ponderación en la calificación o retirarlo— es independiente del soporte multi-lenguaje y merece su propio tratamiento.
