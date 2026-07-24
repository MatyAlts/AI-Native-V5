## ADDED Requirements

### Requirement: La coherencia estructural del código no se calcula sobre lenguajes que no puede analizar

El módulo de Coherencia Estructural del Código SHALL verificar el lenguaje del código antes de intentar analizarlo. Ante un lenguaje que no puede analizar, SHALL devolver una señal explícita de no aplicabilidad.

El módulo NO SHALL devolver valores por defecto ante un lenguaje no soportado. Esos valores agregan a una puntuación alta que resulta indistinguible de código bien estructurado, convirtiendo un dato faltante en un dato falso.

#### Scenario: Código de un lenguaje no soportado

- **WHEN** se solicita la coherencia estructural de un fragmento de código Java
- **THEN** el resultado indica que la métrica no es aplicable a ese lenguaje
- **AND** no se devuelve ninguna puntuación numérica

#### Scenario: Un episodio entero en un lenguaje no soportado

- **WHEN** se solicita la coherencia estructural de un episodio cuyos fragmentos son todos Java
- **THEN** el episodio queda marcado como no medible para esta métrica
- **AND** no queda marcado como estructuralmente coherente

#### Scenario: Código Python sigue midiéndose igual

- **WHEN** se solicita la coherencia estructural de un fragmento de código Python
- **THEN** el cálculo se realiza como antes de este cambio
- **AND** el resultado es idéntico al que producía previamente

#### Scenario: Un error de sintaxis puntual no se confunde con lenguaje no soportado

- **WHEN** se analiza un fragmento Python que el alumno dejó a medio escribir y no parsea
- **THEN** el módulo lo trata como error transitorio, con el comportamiento tolerante que ya tenía
- **AND** no lo reporta como lenguaje no soportado

### Requirement: La no aplicabilidad se distingue de la neutralidad

El contrato de resultados de esta métrica SHALL permitir distinguir tres situaciones: la métrica se calculó, la métrica no se pudo calcular por un error transitorio, y la métrica no aplica a este lenguaje. Un consumidor SHALL poder diferenciarlas sin inspeccionar los valores numéricos.

#### Scenario: Un consumidor distingue los tres casos

- **WHEN** un consumidor recibe resultados de coherencia estructural de tres episodios en las tres situaciones
- **THEN** puede determinar cuál se midió, cuál falló transitoriamente y cuál no aplica
- **AND** no necesita inferirlo a partir de los valores

#### Scenario: Los episodios no medibles no contaminan un agregado

- **WHEN** se calcula un promedio de coherencia estructural sobre una cohorte mixta
- **THEN** los episodios marcados como no aplicables quedan excluidos del promedio
- **AND** el resultado declara cuántos episodios se excluyeron

### Requirement: El guard opera con independencia de quién invoque la métrica

La verificación de lenguaje SHALL vivir en el módulo que calcula la métrica, no en sus invocadores. Debe protegerse el caso en que la métrica se conecte al pipeline de clasificación en el futuro, sin depender de que quien la conecte recuerde aplicar la verificación.

#### Scenario: Un invocador nuevo hereda la protección

- **WHEN** un componente nuevo invoca la métrica sobre código Java sin verificar el lenguaje por su cuenta
- **THEN** recibe igualmente la señal de no aplicabilidad
- **AND** no recibe valores por defecto
