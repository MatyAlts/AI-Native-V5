## Purpose

Garantiza que los workers de partición del ctr-service (los que drenan los streams `ctr.p0..ctr.p7` a Postgres) no mueran en silencio: arrancan sólo con Redis realmente listo, sobreviven a fallos transitorios de Redis, vuelven solos si mueren igual, y su ausencia se ve en el health del servicio — sin romper nunca el single-writer por partición (ADR-010).

## ADDED Requirements

### Requirement: El arranque espera a que Redis esté listo para atender comandos

Antes de correr migraciones o lanzar cualquier proceso, el arranque del ctr-service SHALL esperar a que Redis responda `PING` con éxito, autenticándose con las credenciales de `REDIS_URL`. Un puerto TCP abierto NO SHALL considerarse suficiente: una respuesta de error (incluida la de "cargando el dataset en memoria") o un fallo de conexión cuenta como "todavía no listo". La espera SHALL tener un tope de aproximadamente 2 minutos; al agotarlo, el arranque SHALL fallar con un mensaje que nombre a Redis y la última causa observada.

#### Scenario: Redis con puerto abierto pero cargando el dataset

- **WHEN** Redis acepta conexiones TCP pero responde `LOADING Redis is loading the dataset in memory` a `PING`
- **THEN** el arranque sigue esperando y registra en el log un intento con la causa, sin lanzar workers ni el servidor HTTP

#### Scenario: Redis termina de cargar dentro del tope

- **WHEN** Redis responde `LOADING` durante los primeros intentos y luego `PONG`
- **THEN** el arranque continúa con migraciones y procesos, y el log indica que Redis está disponible

#### Scenario: Redis nunca queda listo

- **WHEN** Redis no responde `PONG` durante todo el tope de espera
- **THEN** el arranque termina con código de salida distinto de cero y un mensaje de error que menciona a Redis

#### Scenario: Credenciales de Redis inválidas

- **WHEN** Redis rechaza la autenticación de `REDIS_URL`
- **THEN** el arranque no lo considera listo y, al agotar el tope, falla con un mensaje que incluye la causa de autenticación

### Requirement: Un worker no muere por un fallo transitorio de Redis al arrancar

Al iniciar, un worker de partición SHALL asegurar la existencia de su consumer group reintentando con backoff exponencial acotado (espera entre intentos con tope ≤ 30 s) ante fallos transitorios de infraestructura de Redis (Redis cargando el dataset, conexión rechazada o cortada, timeout, errores de red). Los reintentos ante transitorios SHALL ser sin límite de cantidad y cada uno SHALL quedar en el log con la partición y la causa. Un error de Redis que no sea transitorio ni "el grupo ya existe" SHALL seguir propagándose. La creación del grupo SHALL conservar su semántica actual: desde el inicio del stream (no se pierde ningún evento ya encolado) e idempotente si el grupo ya existe. Un pedido de detención SHALL interrumpir la espera entre reintentos.

#### Scenario: Redis cargando al arrancar el worker

- **WHEN** el worker intenta crear el consumer group y Redis responde "cargando el dataset" dos veces y luego acepta
- **THEN** el worker queda consumiendo su partición, sin haber terminado el proceso, y el log registra los dos reintentos

#### Scenario: El grupo ya existe

- **WHEN** el worker arranca y el consumer group de su partición ya existe
- **THEN** el worker continúa normalmente sin reintentar ni fallar

#### Scenario: Error permanente de Redis

- **WHEN** la creación del grupo devuelve un error de Redis que no es transitorio ni "el grupo ya existe"
- **THEN** el error se propaga y el worker no queda reintentando en silencio

#### Scenario: Eventos encolados mientras el worker estaba caído

- **WHEN** hay eventos en el stream de la partición publicados antes de que el worker lograra crear o recuperar su grupo
- **THEN** el worker los procesa una vez que arranca (no se descartan)

#### Scenario: Detención durante los reintentos

- **WHEN** el worker está esperando entre reintentos y recibe un pedido de detención
- **THEN** termina sin esperar a que se cumpla el backoff

### Requirement: Un worker caído vuelve a arrancar sin violar single-writer

En el modo de despliegue en que el ctr-service corre los workers dentro del mismo contenedor que el servidor HTTP, cada partición SHALL estar bajo supervisión: si el proceso del worker de esa partición termina por cualquier motivo, SHALL relanzarse automáticamente con una espera creciente entre relanzamientos (con tope) y cada salida SHALL quedar en el log con la partición y el código de salida. Para cada partición SHALL existir en todo momento como máximo un proceso worker vivo: un relanzamiento SHALL ocurrir sólo después de que el proceso anterior de esa partición haya terminado. En los modos de un solo rol (sólo HTTP, o un único worker por contenedor) este requisito no agrega procesos.

#### Scenario: Muere el worker de una partición

- **WHEN** el proceso worker de la partición 3 termina con error
- **THEN** se lanza un nuevo proceso worker para la partición 3 tras la espera de backoff, y el log registra la salida y el relanzamiento

#### Scenario: Nunca dos writers por partición

- **WHEN** el worker de una partición está vivo
- **THEN** la supervisión no lanza otro proceso para esa misma partición

#### Scenario: Fallo repetido

- **WHEN** el worker de una partición termina repetidamente al poco de arrancar
- **THEN** la espera entre relanzamientos crece hasta un tope y nunca se lanzan procesos en un loop sin espera

#### Scenario: Modo HTTP sin workers

- **WHEN** el ctr-service arranca en modo sólo-HTTP
- **THEN** no se lanza ningún worker ni supervisor de particiones

### Requirement: El health del ctr-service refleja a los workers

Cada worker de partición SHALL publicar en Redis una señal de vida por partición con vencimiento corto (del orden de un minuto), renovada en cada vuelta de su loop de consumo. El endpoint de readiness del ctr-service SHALL incluir un check `workers` que falle si falta la señal de vida de alguna de las 8 particiones, y en ese caso SHALL responder HTTP 503 identificando las particiones sin señal. El endpoint de liveness SHALL NO cambiar: sigue respondiendo 200 sin consultar dependencias.

#### Scenario: Los 8 workers vivos

- **WHEN** las 8 particiones tienen señal de vida vigente y DB y Redis responden
- **THEN** readiness responde 200 con el check `workers` en ok

#### Scenario: Workers caídos con HTTP vivo

- **WHEN** el servidor HTTP responde pero ninguna partición tiene señal de vida vigente
- **THEN** readiness responde 503 y el detalle del check `workers` lista las particiones faltantes

#### Scenario: Una sola partición caída

- **WHEN** 7 particiones tienen señal de vida y la partición 5 no
- **THEN** readiness responde 503 y el check `workers` nombra a la partición 5

#### Scenario: Liveness no se ve afectada

- **WHEN** faltan señales de vida de workers
- **THEN** liveness sigue respondiendo 200
