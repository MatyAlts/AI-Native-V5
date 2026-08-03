## ADDED Requirements

### Requirement: Cada alumno tiene un límite de ejecuciones por ventana de tiempo

El sistema SHALL limitar la cantidad de ejecuciones que un alumno puede solicitar en una ventana de tiempo. El límite SHALL ser configurable sin necesidad de modificar código.

Con ejecución en el navegador no hacía falta: el costo lo pagaba el equipo del alumno. Con ejecución en servidor, cada corrida consume procesador y dinero.

#### Scenario: Ejecuciones dentro del límite

- **WHEN** un alumno ejecuta su código una cantidad de veces por debajo del límite
- **THEN** todas las ejecuciones se realizan

#### Scenario: Alcanzar el límite

- **WHEN** un alumno supera el límite de ejecuciones de la ventana
- **THEN** la solicitud se rechaza indicando cuándo podrá volver a ejecutar
- **AND** el resto del episodio sigue disponible

#### Scenario: La ventana se renueva

- **WHEN** transcurre la ventana de tiempo tras haber alcanzado el límite
- **THEN** el alumno puede volver a ejecutar

#### Scenario: El límite es por alumno

- **WHEN** un alumno alcanza su límite
- **THEN** los demás alumnos no se ven afectados

### Requirement: Las cuotas de ejecución fallan cerradas

Si el mecanismo de conteo no está disponible, el sistema SHALL rechazar las solicitudes de ejecución en lugar de permitirlas sin contabilizar.

Otros límites del sistema fallan abiertos deliberadamente, porque protegen presupuesto y no seguridad crítica. Para la ejecución en servidor la consecuencia es distinta: sin conteo, un alumno puede saturar la infraestructura y generar costo sin techo.

#### Scenario: Mecanismo de conteo no disponible

- **WHEN** el mecanismo de conteo de cuotas no responde y un alumno solicita una ejecución
- **THEN** la solicitud se rechaza
- **AND** el mensaje distingue esta situación de haber alcanzado el límite

#### Scenario: El resto del episodio sobrevive

- **WHEN** el mecanismo de conteo no está disponible
- **THEN** el alumno puede seguir escribiendo código y conversando con el tutor

### Requirement: Cada ejecución individual tiene límites propios

Independientemente de las cuotas por alumno, cada ejecución SHALL estar acotada en tiempo de procesador, tiempo total, memoria y cantidad de procesos. Estos límites NO SHALL depender de ningún componente externo al entorno de ejecución.

Son dos capas: una protege de una corrida costosa, la otra de un alumno que solicita muchas.

#### Scenario: Límites aplicados sin depender del conteo de cuotas

- **WHEN** el mecanismo de conteo de cuotas no está disponible pero una ejecución llega al entorno
- **THEN** los límites por ejecución se aplican igualmente

#### Scenario: Los límites por ejecución son configurables

- **WHEN** se ajustan los límites de una ejecución
- **THEN** las siguientes ejecuciones los respetan sin necesidad de reconstruir el servicio

### Requirement: El consumo de ejecución es observable

El sistema SHALL registrar métricas de uso del entorno de ejecución que permitan detectar saturación y costo creciente antes de que se conviertan en un incidente.

#### Scenario: Detectar saturación

- **WHEN** la cantidad de ejecuciones en espera crece de forma sostenida
- **THEN** la métrica correspondiente lo refleja

#### Scenario: Detectar rechazos por cuota

- **WHEN** las solicitudes rechazadas por cuota aumentan
- **THEN** la métrica lo refleja, permitiendo distinguir un límite mal calibrado de un uso abusivo
