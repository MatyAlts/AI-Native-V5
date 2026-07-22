## ADDED Requirements

### Requirement: El prompt del tutor no ejemplifica en un único lenguaje

El prompt del tutor socrático SHALL expresar sus ejemplos de forma independiente del lenguaje de programación. El método —los movimientos socráticos, los principios y los límites de lo que el tutor no hace— NO SHALL modificarse: solo se generalizan las referencias a un lenguaje concreto.

#### Scenario: El ejemplo de contradicción no nombra un lenguaje

- **WHEN** se lee el ejemplo que ilustra cómo confrontar afirmaciones incompatibles
- **THEN** el ejemplo es válido cualquiera sea el lenguaje del ejercicio
- **AND** no nombra un lenguaje en particular

#### Scenario: La instrucción contra la invención de datos no nombra un lenguaje

- **WHEN** se lee la instrucción sobre no afirmar detalles de la biblioteca estándar sin certeza
- **THEN** la instrucción refiere a la biblioteca estándar del lenguaje del ejercicio

#### Scenario: El método permanece intacto

- **WHEN** se compara la versión nueva con la anterior
- **THEN** la única diferencia es la generalización de las referencias a un lenguaje
- **AND** los movimientos socráticos, principios y restricciones son idénticos

### Requirement: Toda versión de prompt declara el hash de su contenido

Cada versión de un prompt SHALL declarar el hash de su contenido, verificable al cargarse. Una versión sin hash declarado permite que su contenido se modifique sin que el sistema lo detecte, y su identificador deja de designar un texto único.

#### Scenario: Cargar una versión con hash declarado

- **WHEN** el sistema carga la versión nueva del prompt del tutor
- **THEN** verifica el hash del contenido contra el declarado
- **AND** la carga tiene éxito

#### Scenario: Detectar una modificación no versionada

- **WHEN** el contenido de una versión con hash declarado se modifica sin actualizar el hash
- **THEN** la carga falla de forma ruidosa
- **AND** el sistema no sirve el contenido modificado bajo el identificador anterior

#### Scenario: El contenido queda cubierto por una verificación automática

- **WHEN** se ejecuta la batería de verificación del proyecto
- **THEN** una comprobación detecta cualquier cambio del contenido de la versión activa

### Requirement: La versión declarada y la efectiva se mantienen alineadas

La versión declarada en el manifiesto y la que el tutor usa en tiempo de ejecución SHALL coincidir. El servicio del tutor no consulta el manifiesto en tiempo de ejecución, de modo que una divergencia haría que las interfaces informen una versión y la trazabilidad registre otra.

#### Scenario: Activar una versión nueva

- **WHEN** se activa una versión nueva del prompt del tutor
- **THEN** el manifiesto y la configuración efectiva quedan actualizados de forma conjunta

#### Scenario: Detectar una divergencia

- **WHEN** el manifiesto y la configuración efectiva declaran versiones distintas
- **THEN** la verificación automática del proyecto falla

### Requirement: La generación asistida produce ejercicios en el lenguaje solicitado

El generador de ejercicios por IA SHALL producir ejercicios en el lenguaje solicitado por el docente, con una progresión de dificultad basada en construcciones propias de ese lenguaje y casos de prueba del tipo que le corresponde.

#### Scenario: Generar un ejercicio de Java

- **WHEN** un docente solicita generar un ejercicio de Java de dificultad básica
- **THEN** el ejercicio propuesto usa construcciones básicas propias de Java
- **AND** sus casos de prueba son del tipo correspondiente a Java
- **AND** el código inicial propuesto es Java

#### Scenario: La progresión de dificultad es propia del lenguaje

- **WHEN** se generan ejercicios de Java de dificultad básica, intermedia y avanzada
- **THEN** cada nivel usa construcciones apropiadas para ese nivel en Java
- **AND** no se exigen construcciones inexistentes en el lenguaje

#### Scenario: La generación en el lenguaje preexistente no cambia

- **WHEN** un docente genera un ejercicio en el lenguaje que ya estaba soportado
- **THEN** el resultado es equivalente al que producía antes de este cambio

### Requirement: La generación de tareas prácticas completas respeta el lenguaje

El generador de tareas prácticas completas SHALL producir todos los ejercicios de la tarea en el lenguaje solicitado, con progresión coherente entre ellos.

#### Scenario: Generar una tarea práctica de Java

- **WHEN** un docente solicita generar una tarea práctica de Java
- **THEN** todos los ejercicios propuestos son de Java
- **AND** ninguno mezcla construcciones de otro lenguaje

#### Scenario: La tarea generada es publicable

- **WHEN** se acepta una tarea práctica generada en Java
- **THEN** la tarea cumple la regla de un único lenguaje y puede publicarse

### Requirement: El contexto del ejercicio se rotula en su lenguaje

Al inyectar el código inicial del ejercicio en el contexto del tutor, el bloque SHALL rotularse con el lenguaje del ejercicio.

#### Scenario: Contexto de un ejercicio Java

- **WHEN** se abre un episodio de un ejercicio Java con código inicial
- **THEN** el bloque de código inyectado al tutor se rotula como Java

#### Scenario: Contexto de un ejercicio sin código inicial

- **WHEN** se abre un episodio de un ejercicio sin código inicial
- **THEN** no se inyecta ningún bloque de código y el contexto se arma sin error
