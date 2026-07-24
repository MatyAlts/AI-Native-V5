## ADDED Requirements

### Requirement: El episodio registra su lenguaje al abrirse

El evento de apertura de episodio SHALL incluir el lenguaje de programación en el que se resuelve, de modo que el corpus pueda segmentarse por lenguaje sin inspeccionar eventos repetidos ni resolver joins entre bases.

El lenguaje SHALL resolverse en el servidor a partir del ejercicio o la tarea práctica asociada. El sistema NO SHALL aceptar el lenguaje declarado por el cliente para este evento.

#### Scenario: Abrir un episodio sobre un ejercicio de Java

- **WHEN** un alumno abre un episodio sobre un ejercicio con `language = "java"`
- **THEN** el evento de apertura registra el lenguaje `java`
- **AND** el valor proviene del ejercicio, no de la petición del cliente

#### Scenario: Abrir un episodio sobre una TP monolítica

- **WHEN** un alumno abre un episodio sobre una TP sin ejercicios de banco
- **THEN** el evento de apertura registra el lenguaje declarado en la TP

#### Scenario: El cliente no puede declarar el lenguaje

- **WHEN** una petición de apertura de episodio incluye un lenguaje en su cuerpo
- **THEN** el valor enviado se ignora
- **AND** el evento registra el lenguaje resuelto desde el ejercicio

#### Scenario: El lenguaje es un snapshot, no una referencia viva

- **WHEN** el lenguaje del ejercicio se modifica después de abierto un episodio
- **THEN** el evento de apertura ya emitido conserva el lenguaje que tenía al abrirse
- **AND** la cadena de trazabilidad no se altera

### Requirement: Los episodios previos al cambio se interpretan como Python

Los episodios abiertos antes de la existencia de este campo NO SHALL considerarse de lenguaje desconocido. El sistema solo admitía Python, de modo que la ausencia del campo es interpretable sin ambigüedad.

#### Scenario: Episodio histórico sin el campo

- **WHEN** se analiza un episodio abierto antes de este cambio
- **THEN** se interpreta como lenguaje `python`
- **AND** no se lo excluye de los análisis por falta de dato

### Requirement: El registro del lenguaje no altera la trazabilidad existente

La incorporación de este campo NO SHALL modificar el hash de configuración del clasificador, las etiquetas N1–N4 de eventos históricos, ni la versión del etiquetador. Los eventos ya persistidos SHALL conservar su hash original.

#### Scenario: Los eventos históricos conservan su integridad

- **WHEN** se verifica la cadena criptográfica de un episodio anterior a este cambio
- **THEN** la verificación pasa sin discrepancias

#### Scenario: El clasificador no consume el lenguaje

- **WHEN** se clasifica un episodio que declara lenguaje
- **THEN** el hash de configuración del clasificador es idéntico al de un episodio equivalente sin el campo
- **AND** las métricas resultantes son idénticas
