## ADDED Requirements

### Requirement: Calificar una re-entrega desde el panel del docente
El panel de corrección del docente SHALL permitir calificar una entrega en estado `submitted` que ya tiene una calificación previa (re-entrega tras una devolución), actualizando la calificación existente y dejando la entrega en `graded`, sin exponer al docente el error 409 de "ya tiene una calificacion".

#### Scenario: Re-entrega se califica por actualización
- **WHEN** el docente abre una entrega `submitted` que ya tiene una calificación
- **AND** completa nota y feedback y confirma
- **THEN** el panel actualiza la calificación existente (no crea una segunda)
- **AND** la entrega queda `graded`

#### Scenario: Se informa que es una re-entrega
- **WHEN** el docente abre una entrega `submitted` que ya tiene una calificación
- **THEN** el panel indica que es una re-entrega y muestra la nota anterior como referencia
- **AND** los campos de nota y feedback arrancan vacíos

#### Scenario: Primera calificación sin cambios
- **WHEN** el docente califica una entrega `submitted` sin calificación previa
- **THEN** el panel crea la calificación (comportamiento actual)

#### Scenario: Conflicto inesperado se resuelve por actualización
- **WHEN** la creación de la calificación responde 409 porque ya existía una
- **THEN** el panel reintenta actualizando la calificación existente
- **AND** el docente no ve el error 409
