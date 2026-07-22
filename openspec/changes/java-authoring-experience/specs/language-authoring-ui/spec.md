## ADDED Requirements

### Requirement: El docente elige el lenguaje al crear un ejercicio

El formulario de creación y edición de ejercicios SHALL permitir seleccionar el lenguaje de programación. El formulario SHALL preseleccionar el lenguaje por omisión del sistema, de modo que el flujo actual del docente no requiera pasos adicionales.

#### Scenario: Crear un ejercicio de Java

- **WHEN** un docente abre el formulario de creación, elige Java y guarda
- **THEN** el ejercicio se crea con lenguaje Java
- **AND** el listado del banco lo muestra identificado como tal

#### Scenario: Crear un ejercicio sin tocar el selector

- **WHEN** un docente crea un ejercicio sin modificar el selector de lenguaje
- **THEN** el ejercicio se crea con el lenguaje por omisión
- **AND** el flujo no requiere pasos adicionales respecto del comportamiento previo

#### Scenario: El listado identifica el lenguaje

- **WHEN** un docente consulta el banco de ejercicios con ejercicios de más de un lenguaje
- **THEN** puede distinguir el lenguaje de cada uno sin abrir el detalle

### Requirement: La composición de una tarea práctica impide mezclar lenguajes

Al componer una TP seleccionando ejercicios del banco, la interfaz SHALL impedir seleccionar ejercicios de un lenguaje distinto al ya elegido. El impedimento SHALL ocurrir en el momento de la selección, no al confirmar ni al publicar.

#### Scenario: Bloquear la selección de otro lenguaje

- **WHEN** un docente selecciona un ejercicio Java y luego intenta seleccionar uno Python en la misma TP
- **THEN** la interfaz impide la segunda selección
- **AND** explica que una tarea práctica admite un solo lenguaje

#### Scenario: Selección libre mientras no haya lenguaje elegido

- **WHEN** un docente abre la composición sin ningún ejercicio seleccionado
- **THEN** puede seleccionar un ejercicio de cualquier lenguaje

#### Scenario: Liberar el bloqueo al deseleccionar todo

- **WHEN** un docente deselecciona todos los ejercicios de una composición en curso
- **THEN** vuelve a poder elegir cualquier lenguaje

### Requirement: El alumno ve el lenguaje antes y durante el episodio

El alumno SHALL poder identificar el lenguaje de una tarea práctica en el selector de tareas, antes de abrir el episodio, y en la cabecera del editor mientras trabaja. Ninguna de las dos superficies SHALL mostrar un lenguaje fijo.

#### Scenario: Lenguaje visible en el selector de tareas

- **WHEN** un alumno consulta sus tareas pendientes y alguna es de Java
- **THEN** puede identificar el lenguaje de cada tarea sin abrirla

#### Scenario: Lenguaje visible en el editor

- **WHEN** un alumno abre un episodio de una tarea Java
- **THEN** la cabecera del editor indica Java

#### Scenario: Ninguna superficie muestra un lenguaje fijo

- **WHEN** se abre un episodio de cualquier lenguaje
- **THEN** el lenguaje mostrado corresponde al del ejercicio, en todas las superficies

### Requirement: El editor asiste en el lenguaje correcto

El editor de código SHALL aplicar el resaltado de sintaxis correspondiente al lenguaje del ejercicio.

#### Scenario: Resaltado de Java

- **WHEN** un alumno abre un episodio de un ejercicio Java
- **THEN** el editor resalta la sintaxis de Java

#### Scenario: Resaltado de Python sin cambios

- **WHEN** un alumno abre un episodio de un ejercicio Python
- **THEN** el editor se comporta igual que antes de este cambio

### Requirement: La ejecución no disponible se comunica explícitamente

Mientras un lenguaje no tenga entorno de ejecución, el control de ejecutar SHALL presentarse deshabilitado y acompañado de una explicación. El sistema NO SHALL ofrecer un control que al accionarse no produzca ningún efecto ni mensaje.

Hoy el control queda habilitado y su accionamiento no produce efecto alguno, sin mensaje ni registro.

#### Scenario: Ejecutar en un lenguaje sin entorno

- **WHEN** un alumno abre un episodio de un ejercicio Java
- **THEN** el control de ejecutar aparece deshabilitado
- **AND** se indica que la ejecución todavía no está disponible para ese lenguaje

#### Scenario: Probar casos en un lenguaje sin entorno

- **WHEN** un alumno abre un episodio Java con casos de prueba definidos
- **THEN** el control de probar aparece deshabilitado con la misma explicación

#### Scenario: El tutor sigue disponible

- **WHEN** un alumno trabaja en un episodio Java sin entorno de ejecución
- **THEN** puede conversar con el tutor socrático y recibir orientación normalmente
- **AND** sus ediciones de código se registran en la trazabilidad

#### Scenario: Python conserva su comportamiento

- **WHEN** un alumno abre un episodio Python
- **THEN** los controles de ejecutar y probar funcionan como antes de este cambio

### Requirement: El rótulo accesible refleja el lenguaje real

Los rótulos accesibles de los controles de ejecución SHALL nombrar el lenguaje del ejercicio. NO SHALL nombrar un lenguaje fijo.

#### Scenario: Rótulo en un ejercicio Java

- **WHEN** un lector de pantalla anuncia el control de ejecutar en un episodio Java
- **THEN** el rótulo nombra Java

#### Scenario: Estado de error anunciado

- **WHEN** se produce un error de ejecución o se comunica que la ejecución no está disponible
- **THEN** el mensaje se anuncia a las tecnologías de asistencia sin requerir navegación manual hasta el panel de salida

### Requirement: Los casos de prueba se rotulan por su tipo real

La interfaz del docente SHALL rotular cada caso de prueba según su tipo real. Con la incorporación de un tercer tipo, un rótulo derivado de una condición binaria pasa a ser incorrecto.

#### Scenario: Rotular un caso de prueba de Java

- **WHEN** un docente visualiza un ejercicio con un caso de prueba del tipo propio de Java
- **THEN** el rótulo corresponde a ese tipo
- **AND** no se lo rotula con el tipo propio de Python

#### Scenario: Los tipos existentes conservan su rótulo

- **WHEN** un docente visualiza casos de prueba de los dos tipos preexistentes
- **THEN** cada uno conserva el rótulo que tenía antes de este cambio
