## ADDED Requirements

### Requirement: El código de los alumnos se ejecuta en un entorno aislado

El sistema SHALL ejecutar el código de los alumnos en un entorno aislado que limite tiempo de procesador, memoria, cantidad de procesos y acceso a la red. El entorno NO SHALL tener acceso a las bases de datos de la plataforma ni a la red interna.

#### Scenario: Ejecutar código correcto

- **WHEN** un alumno ejecuta código Java válido
- **THEN** recibe la salida estándar producida
- **AND** el resultado incluye el tiempo y la memoria consumidos

#### Scenario: Código que no compila

- **WHEN** un alumno ejecuta código Java con un error de sintaxis
- **THEN** recibe el mensaje del compilador
- **AND** el resultado se distingue de un error de ejecución

#### Scenario: Código que excede el tiempo permitido

- **WHEN** un alumno ejecuta código con un ciclo infinito
- **THEN** la ejecución se interrumpe al alcanzar el límite
- **AND** el alumno recibe una indicación de que se excedió el tiempo

#### Scenario: Código que intenta acceder a la red

- **WHEN** el código de un alumno intenta abrir una conexión de red
- **THEN** el intento falla
- **AND** ningún recurso interno de la plataforma resulta alcanzable

#### Scenario: Código que excede la memoria permitida

- **WHEN** un alumno ejecuta código que consume memoria sin límite
- **THEN** la ejecución se interrumpe
- **AND** el resto de las ejecuciones en curso no se ven afectadas

### Requirement: Los casos de prueba ocultos nunca llegan al cliente

Cuando se ejecutan los casos de prueba de un ejercicio, el sistema SHALL incorporar los casos ocultos del lado del servidor. El cliente NO SHALL recibir el contenido, el nombre ni la salida esperada de un caso oculto en ninguna circunstancia.

#### Scenario: Ejecutar casos de prueba con casos ocultos

- **WHEN** un alumno ejecuta los casos de prueba de un ejercicio que tiene casos públicos y ocultos
- **THEN** todos se ejecutan
- **AND** el alumno recibe el detalle únicamente de los públicos
- **AND** de los ocultos recibe solo el resultado agregado

#### Scenario: El contenido de un caso oculto no viaja al cliente

- **WHEN** se inspecciona la respuesta de una ejecución de casos de prueba
- **THEN** no contiene el código, el nombre ni la salida esperada de ningún caso oculto

### Requirement: La ejecución es asíncrona

El sistema SHALL aceptar una solicitud de ejecución y responder de inmediato con un identificador, permitiendo consultar el estado y el resultado por separado. NO SHALL bloquear al cliente hasta terminar.

#### Scenario: Solicitar una ejecución

- **WHEN** un alumno solicita ejecutar su código
- **THEN** recibe de inmediato un identificador de la ejecución
- **AND** puede consultar su estado

#### Scenario: Consultar una ejecución en curso

- **WHEN** se consulta una ejecución que todavía no terminó
- **THEN** el estado indica que está en curso
- **AND** no se devuelve un resultado parcial ni engañoso

#### Scenario: Consultar una ejecución terminada

- **WHEN** se consulta una ejecución terminada
- **THEN** se obtiene el resultado completo

### Requirement: Los resultados se expresan en el formato existente del sistema

El resultado de ejecutar casos de prueba SHALL expresarse con la misma estructura que produce la ejecución en el navegador, de modo que el evento de trazabilidad tenga idéntica forma para todos los lenguajes.

#### Scenario: Resultado de casos de prueba equivalente entre lenguajes

- **WHEN** se ejecutan los casos de prueba de un ejercicio Java
- **THEN** la estructura del resultado es la misma que la de un ejercicio Python
- **AND** la interfaz que muestra resultados no requiere adaptación por lenguaje

#### Scenario: El registro de trazabilidad no revela el motor

- **WHEN** se analiza un evento de ejecución de casos de prueba
- **THEN** su forma es idéntica a la de un evento equivalente del otro lenguaje
- **AND** el motor utilizado queda registrado como un dato más, sin alterar la estructura

### Requirement: Un fallo de infraestructura no se registra como un fallo del alumno

El sistema SHALL distinguir explícitamente entre "los casos de prueba se ejecutaron y fallaron" y "los casos de prueba no pudieron ejecutarse". Una indisponibilidad del entorno de ejecución NO SHALL registrarse como casos fallidos.

Esta distinción es crítica: el conteo de casos fallidos alimenta la clasificación pedagógica del episodio, de modo que un problema de infraestructura registrado como fallo del alumno degradaría datos de investigación.

#### Scenario: El entorno de ejecución no responde

- **WHEN** un alumno ejecuta casos de prueba y el entorno de ejecución no está disponible
- **THEN** el registro indica que la ejecución no pudo realizarse
- **AND** no se registra ningún caso como fallido
- **AND** el alumno recibe un mensaje que distingue este caso de un error en su código

#### Scenario: Los casos se ejecutan y algunos fallan

- **WHEN** un alumno ejecuta casos de prueba y dos no pasan
- **THEN** el registro indica dos casos fallidos
- **AND** la ejecución consta como realizada

#### Scenario: La clasificación no se degrada por indisponibilidad

- **WHEN** se clasifica un episodio en el que hubo un intento de ejecución fallido por infraestructura
- **THEN** ese intento no cuenta como casos fallidos del alumno

### Requirement: Una ejecución realizada se registra una sola vez

El registro del evento de ejecución SHALL ser idempotente. Un reintento del cliente ante una respuesta perdida NO SHALL producir un segundo evento en la cadena de trazabilidad.

Con ejecución en el navegador, perder un evento era inocuo. Con ejecución en servidor, la corrida ya consumió cómputo y cuota del alumno.

#### Scenario: Reintento tras una respuesta perdida

- **WHEN** el cliente reintenta registrar una ejecución que ya fue registrada
- **THEN** no se agrega un segundo evento a la cadena
- **AND** la respuesta confirma el registro existente

#### Scenario: Dos ejecuciones distintas se registran por separado

- **WHEN** un alumno ejecuta su código dos veces
- **THEN** se registran dos eventos distintos
