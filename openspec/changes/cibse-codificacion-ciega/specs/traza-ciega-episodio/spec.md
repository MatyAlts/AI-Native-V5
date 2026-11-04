# Spec Delta

## Purpose

Presenta a un codificador humano la línea de tiempo de un episodio con la evidencia de lo que hizo el alumno, fija desde la carga, sin ninguna información que revele decisiones o marcas automáticas del sistema ni la identidad del alumno.

## ADDED Requirements

### Requirement: Traza servida por identificador opaco y solo dentro del estudio
El sistema SHALL devolver la traza ciega de un ítem solo a miembros activos del estudio y solo si el identificador corresponde a un ítem de la muestra o a un ancla de ese estudio. Cualquier otro identificador SHALL responder 404.

#### Scenario: Codificador pide un ítem de la muestra
- **WHEN** un codificador pide la traza de un ítem de la muestra de su estudio
- **THEN** recibe 200 con la línea de tiempo del episodio

#### Scenario: Identificador de otro estudio
- **WHEN** un codificador pide la traza con el identificador de un ítem de otro estudio
- **THEN** recibe 404

#### Scenario: UUID de episodio en lugar de identificador opaco
- **WHEN** un codificador pide la traza usando un `episode_id` real de la muestra
- **THEN** recibe 404

#### Scenario: Usuario sin membresía
- **WHEN** un usuario sin membresía pide la traza de un ítem válido
- **THEN** recibe 403

### Requirement: Lista blanca versionada de eventos y campos
La traza SHALL construirse con una lista blanca identificada por una versión. `traza_v1` incluye inicio, lectura de la consigna, mensajes del alumno y del tutor (texto), estados del código, ejecuciones con salidas y conteos, corridas de pruebas (conteos), notas del alumno, intentos de copiar y de pegar (sin el texto pegado) y fin cerrado o abandonado (sin motivo). Todo otro tipo de evento, incluidos los desconocidos, y todo campo no listado SHALL omitirse.

#### Scenario: Episodio con detección de sobreuso
- **WHEN** el episodio tiene eventos `intento_adverso_detectado` de categoría `overuse` y `jailbreak_indirect`
- **THEN** la traza no contiene ningún elemento derivado de esos eventos ni los textos `overuse`, `jailbreak` ni `intento_adverso`

#### Scenario: Clasificación automática del prompt
- **WHEN** un `prompt_enviado` trae `prompt_kind="validacion"`
- **THEN** la traza muestra el texto del mensaje y no contiene `prompt_kind` ni su valor

#### Scenario: Metadatos del tutor
- **WHEN** un `tutor_respondio` trae `socratic_compliance`, `violations`, `model_used`, `provider`, tokens y costo
- **THEN** la traza muestra solo el texto de la respuesta

#### Scenario: Procedencia automática del código
- **WHEN** un `edicion_codigo` trae `origin="copied_from_tutor"`
- **THEN** la traza muestra el contenido del código y no contiene `origin` ni su valor

#### Scenario: Intento de pegar
- **WHEN** un `pega_intentada` trae `contenido_preview` con texto
- **THEN** la traza muestra el intento con su longitud y método, sin el texto pegado

#### Scenario: Fin abandonado
- **WHEN** el episodio termina con `episodio_abandonado` de motivo `timeout`
- **THEN** la traza muestra "fin: abandonado" sin el motivo, distinto de "fin: cerrado"

#### Scenario: Eventos posteriores al cierre, calificación y pestañas
- **WHEN** el episodio tiene `reflexion_completada`, `tp_entregada`, `tp_calificada`, `episodio_reabierto`, `pestana_perdida` o `pestana_recuperada`
- **THEN** la traza los omite

#### Scenario: Tipo de evento desconocido
- **WHEN** el episodio tiene un evento con un tipo que no está en la lista blanca
- **THEN** la traza lo omite

#### Scenario: Campos fuera del contrato
- **WHEN** un evento incluido trae claves que no están en la lista blanca, por ejemplo `execution_engine`
- **THEN** el elemento de la traza contiene exactamente las claves permitidas para su tipo

### Requirement: Evidencia acotada al tope fijado en la carga
La traza SHALL incluir solo eventos hasta el tope fijado al cargar el ítem. Si el evento del tope ya no coincide con lo registrado, o si la versión de lista blanca del sistema difiere de la del estudio, el sistema SHALL responder 409 con el motivo y registrarlo, sin servir eventos.

#### Scenario: Evento posterior al tope
- **WHEN** el episodio tiene un evento con secuencia mayor al tope del ítem
- **THEN** la traza no lo incluye

#### Scenario: Tope que no coincide
- **WHEN** el encadenamiento del evento del tope difiere del registrado al cargar
- **THEN** la traza responde 409 `evidencia_alterada` y se emite un evento de log con el identificador del ítem

#### Scenario: Versión de lista blanca distinta
- **WHEN** el estudio se dio de alta con `traza_v1` y el sistema sirve otra versión
- **THEN** la traza responde 409 `traza_version_distinta`

### Requirement: Enunciado del episodio en la traza
La traza SHALL incluir el enunciado de la TP del episodio y, si el episodio trabajó un ejercicio del banco, también el del ejercicio, en la versión revisada por el investigador y tal como se cargaron. Si alguno de los dos falta o no está revisado, la traza SHALL responder 409 `enunciado_pendiente`. SHALL NOT incluir título, código, fechas, rúbrica, casos de prueba ni material del tutor.

#### Scenario: Episodio de un ejercicio del banco
- **WHEN** el episodio abrió con un ejercicio de una TP
- **THEN** la traza trae la consigna de la TP y la del ejercicio, rotuladas, sin identificadores ni hashes

#### Scenario: TP monolítica
- **WHEN** el episodio no tiene ejercicio
- **THEN** la traza trae solo la consigna de la TP

#### Scenario: Enunciado pendiente
- **WHEN** el enunciado del ejercicio de un ítem no se cargó o no se revisó
- **THEN** la traza de ese ítem responde 409 `enunciado_pendiente`

#### Scenario: Versión editada por el investigador
- **WHEN** el investigador guardó una versión editada del enunciado al revisarlo
- **THEN** la traza muestra la versión editada y no la original

### Requirement: Sin identidad ni metadatos del episodio
La traza SHALL NOT contener `episode_id`, pseudónimo del alumno, comisión, problema, hashes de cadena o de configuración, números de secuencia originales, marcas de tiempo absolutas ni identificadores de usuario.

#### Scenario: Revisión de claves de la respuesta
- **WHEN** se recorre recursivamente la respuesta de la traza
- **THEN** no aparece ninguna de las claves `episode_id`, `student_pseudonym`, `comision_id`, `problema_id`, `seq`, `ts`, `self_hash`, `chain_hash`, `prev_chain_hash`, `user_id`, `curso_config_hash`, `classifier_config_hash` ni el valor del `episode_id`

### Requirement: Localizadores y tiempo relativo
Cada elemento de la traza SHALL llevar un localizador global contiguo desde 1, un localizador por tipo (turno k para mensajes del alumno y las respuestas del tutor que les siguen, código k, ejecución k, prueba k, nota k, lectura k) asignados después de omitir eventos, y los segundos transcurridos desde el inicio del episodio, en orden temporal.

#### Scenario: Eventos omitidos en el medio
- **WHEN** el episodio tiene seq 0 a 5 y el seq 3 es `intento_adverso_detectado`
- **THEN** la traza tiene 5 elementos con localizadores globales 1 a 5, sin huecos, en el orden original

#### Scenario: Turnos del chat
- **WHEN** el alumno manda dos mensajes y el tutor responde una vez a cada uno
- **THEN** el primer mensaje y su respuesta llevan turno 1, y el segundo mensaje y su respuesta llevan turno 2

#### Scenario: Latidos de lectura agrupados
- **WHEN** el episodio tiene tres `lectura_enunciado` seguidos de 30 segundos cada uno, luego un mensaje del alumno y luego otro `lectura_enunciado`
- **THEN** la traza muestra un elemento "lectura de la consigna" de 90 segundos, el mensaje y otro elemento de lectura, con localizadores lectura 1 y lectura 2

#### Scenario: Ejecuciones numeradas
- **WHEN** hay tres ejecuciones intercaladas con mensajes
- **THEN** llevan ejecución 1, 2 y 3 en orden temporal

### Requirement: Fallas del registro de episodios
Si el registro de episodios no responde o devuelve error, el sistema SHALL responder 502 con un mensaje genérico, sin reenviar el cuerpo del error.

#### Scenario: Registro caído
- **WHEN** el registro de episodios devuelve 500 o excede el tiempo de espera
- **THEN** la traza responde 502 con un mensaje genérico

#### Scenario: Respuesta con forma inválida
- **WHEN** el registro de episodios responde 200 con un episodio que coincide con la evidencia fija pero con un `ts` sin zona o que no es fecha, un `problema_id` o un `ejercicio_id` de apertura que no es UUID, un `duration_seconds` de lectura no numérico, un `integrity_compromised` no booleano o tipos incorrectos en los campos del episodio o de sus eventos
- **THEN** la traza responde 502 con el mismo mensaje genérico y sin contenido del episodio

### Requirement: Presentación en el panel docente
El panel SHALL mostrar la traza en orden temporal con tiempo relativo al inicio y localizadores, los mensajes como conversación, cada estado del código con sus diferencias respecto del anterior, y ejecuciones y pruebas con sus salidas y conteos. SHALL NOT mostrar el JSON crudo.

#### Scenario: Dos estados de código consecutivos
- **WHEN** la traza tiene dos estados de código donde cambió una línea
- **THEN** el panel marca esa línea como quitada y su reemplazo como agregado

#### Scenario: Ejecución con error
- **WHEN** la traza tiene una ejecución con salida de error
- **THEN** el panel muestra la salida de error junto con su localizador de ejecución y su tiempo relativo
