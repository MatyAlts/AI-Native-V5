## ADDED Requirements

### Requirement: El alumno ejecuta su código Java desde el editor

El editor SHALL permitir ejecutar código Java y mostrar su salida, reemplazando el estado de "ejecución no disponible". La experiencia SHALL ser equivalente a la del lenguaje ya soportado en cuanto a los controles disponibles y la presentación de resultados.

#### Scenario: Ejecutar código Java correcto

- **WHEN** un alumno ejecuta código Java válido desde el editor
- **THEN** ve la salida producida en el panel de resultados
- **AND** la ejecución queda registrada en la trazabilidad del episodio

#### Scenario: Probar los casos de prueba de un ejercicio Java

- **WHEN** un alumno ejecuta los casos de prueba de un ejercicio Java
- **THEN** ve cuáles pasaron y cuáles no, con el mismo formato que en el otro lenguaje

#### Scenario: El lenguaje ya soportado no cambia

- **WHEN** un alumno ejecuta código en el lenguaje que ya funcionaba
- **THEN** el comportamiento es idéntico al previo a este cambio
- **AND** la ejecución sigue ocurriendo en el navegador

### Requirement: La espera de una ejecución en servidor se comunica

Mientras una ejecución en servidor está en curso, el editor SHALL indicar que se está compilando y ejecutando en el servidor. El mensaje SHALL distinguirse del que se usa para una ejecución local instantánea.

La espera en servidor ocurre en cada ejecución, no solo la primera, a diferencia de la carga inicial del entorno local.

#### Scenario: Indicación durante la espera

- **WHEN** un alumno ejecuta código Java y la ejecución demora
- **THEN** el editor indica que se está compilando y ejecutando en el servidor
- **AND** el control de ejecutar no admite una segunda solicitud simultánea

#### Scenario: La espera se resuelve

- **WHEN** la ejecución termina
- **THEN** el resultado reemplaza la indicación de espera

### Requirement: Los errores de Java se presentan de forma comprensible

El sistema SHALL analizar los mensajes de error de compilación y de ejecución de Java para señalar la línea correspondiente en el editor cuando sea posible. El análisis de errores del lenguaje ya soportado NO SHALL alterarse.

#### Scenario: Error de compilación con línea señalada

- **WHEN** un alumno ejecuta código Java con un error de compilación en una línea concreta
- **THEN** el editor señala esa línea
- **AND** muestra el mensaje del compilador

#### Scenario: Excepción en tiempo de ejecución

- **WHEN** el código de un alumno lanza una excepción no capturada
- **THEN** el editor muestra el tipo de excepción y el mensaje
- **AND** señala la línea de origen cuando la traza lo permite

#### Scenario: Error sin línea identificable

- **WHEN** un error no permite identificar una línea
- **THEN** el mensaje se muestra igual en el panel de resultados
- **AND** no se señala ninguna línea arbitraria

#### Scenario: Los errores del lenguaje ya soportado no cambian

- **WHEN** se produce un error en el lenguaje que ya funcionaba
- **THEN** el análisis y la señalización son idénticos a los previos a este cambio

### Requirement: El docente verifica un ejercicio Java antes de asignarlo

El panel de prueba de ejercicios del docente SHALL permitir ejecutar código Java contra los casos de prueba definidos, incluidos los ocultos. Sin esta capacidad el docente no puede comprobar que un ejercicio Java sea resoluble antes de asignarlo.

Este panel opera sobre una implementación de ejecución independiente de la del editor del alumno.

#### Scenario: Verificar un ejercicio Java

- **WHEN** un docente prueba un ejercicio Java con una solución de referencia
- **THEN** ve el resultado de todos los casos de prueba, públicos y ocultos

#### Scenario: Detectar un caso de prueba mal definido

- **WHEN** un docente prueba un ejercicio Java cuya solución de referencia no pasa un caso
- **THEN** identifica cuál caso falla y con qué salida

#### Scenario: El panel no produce resultados engañosos con Java

- **WHEN** un docente prueba un ejercicio Java
- **THEN** el resultado corresponde a una ejecución real de Java
- **AND** no se intenta interpretarlo con el entorno del otro lenguaje

### Requirement: La indisponibilidad del entorno degrada sin bloquear el episodio

Cuando el entorno de ejecución no está disponible, el alumno SHALL conservar el resto de las capacidades del episodio: leer el enunciado, escribir código, conversar con el tutor y registrar su actividad. Ejecutar es un complemento, no un requisito del episodio.

#### Scenario: Entorno caído durante un episodio

- **WHEN** un alumno intenta ejecutar y el entorno no está disponible
- **THEN** recibe un mensaje que lo distingue de un error de su código
- **AND** puede seguir escribiendo y conversando con el tutor

#### Scenario: La actividad se sigue registrando

- **WHEN** un alumno continúa trabajando con el entorno de ejecución caído
- **THEN** sus ediciones y su conversación con el tutor se registran normalmente
- **AND** el episodio puede cerrarse
