## ADDED Requirements

### Requirement: Los análisis declaran siempre qué lenguajes contienen

Todo endpoint de analytics que agregue datos de episodios SHALL declarar en su respuesta qué lenguajes de programación componen el resultado. La declaración NO SHALL ser opcional ni depender de que el consumidor la haya solicitado.

Alcanza a los análisis de concordancia entre evaluadores, progresión de cohorte, evolución longitudinal, eventos adversariales, alertas y distribución de niveles.

#### Scenario: Cohorte de un solo lenguaje

- **WHEN** se consulta la progresión de una cohorte cuyos episodios son todos Python
- **THEN** la respuesta declara que contiene únicamente `python`

#### Scenario: Cohorte mixta

- **WHEN** se consulta la progresión de una cohorte con episodios Python y Java
- **THEN** la respuesta declara ambos lenguajes
- **AND** la mezcla es visible sin necesidad de inspeccionar los episodios individuales

#### Scenario: La declaración no depende del filtro

- **WHEN** se consulta cualquier endpoint de analytics sin parámetro de lenguaje
- **THEN** la respuesta declara igualmente los lenguajes que contiene

### Requirement: Los análisis pueden restringirse a un lenguaje

Los endpoints de analytics SHALL aceptar un parámetro opcional que restrinja el análisis a los episodios de un lenguaje. Su ausencia SHALL preservar el comportamiento actual, sin romper consumidores existentes.

#### Scenario: Filtrar la progresión por lenguaje

- **WHEN** se consulta la progresión de una cohorte mixta restringiendo a `java`
- **THEN** el resultado agrega únicamente episodios Java
- **AND** la respuesta declara contener únicamente `java`

#### Scenario: Sin filtro se preserva el comportamiento actual

- **WHEN** se consulta un endpoint sin el parámetro de lenguaje
- **THEN** el resultado agrega episodios de todos los lenguajes, como antes del cambio

#### Scenario: Filtro sin resultados

- **WHEN** se restringe a `java` una cohorte que solo tiene episodios Python
- **THEN** la respuesta indica ausencia de datos suficientes
- **AND** no devuelve métricas calculadas sobre un conjunto vacío

### Requirement: El export académico incluye el lenguaje por episodio

El export académico anonimizado SHALL incluir el lenguaje de cada episodio exportado y declarar los lenguajes presentes en el conjunto. Un investigador que reciba el export SHALL poder segmentar sin acceso al sistema.

#### Scenario: Export de una cohorte mixta

- **WHEN** se exporta una cohorte con episodios Python y Java
- **THEN** cada episodio del export declara su lenguaje
- **AND** el encabezado del export declara los lenguajes presentes

#### Scenario: El export respeta la anonimización vigente

- **WHEN** se exporta incluyendo el lenguaje
- **THEN** las garantías de anonimización existentes se mantienen sin cambios
- **AND** el lenguaje no permite reidentificar a un estudiante

### Requirement: El sesgo de calibración queda declarado

El sistema SHALL documentar que los umbrales del clasificador fueron calibrados sobre comportamiento con ejecución en el navegador, y que la ejecución en servidor introduce latencia que reduce sistemáticamente la frecuencia de ejecuciones por unidad de tiempo.

Esta declaración SHALL ser accesible desde la documentación del análisis, no solo desde comentarios en el código, porque su destinatario es quien interpreta los datos.

#### Scenario: La limitación es consultable

- **WHEN** un investigador consulta la documentación de las métricas del clasificador
- **THEN** encuentra declarado el sesgo de calibración entre lenguajes con ejecución en navegador y en servidor
- **AND** encuentra qué métricas están afectadas y en qué dirección
