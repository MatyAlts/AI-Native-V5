# Spec Delta

## Purpose

Entrena y calibra a los codificadores de un estudio con anclas persistidas que pertenecen a una versión del codebook, nunca tomadas de la muestra, y deja registro de cada respuesta de entrenamiento.

## ADDED Requirements

### Requirement: Anclas persistidas por versión del codebook
El investigador SHALL poder cargar anclas en una versión en borrador: episodio terminado (cerrado, o pausado por abandono), uso (`ejemplo` o `practica`), orden, respuesta esperada validada contra el esquema de esa versión, explicación y quiénes la consensuaron. Cada ancla SHALL tener un identificador opaco propio y su evidencia fija desde la carga.

#### Scenario: Alta de ancla válida
- **WHEN** el investigador carga un ancla de práctica con régimen y dimensiones esperadas válidas para el esquema de `v0` en borrador
- **THEN** el ancla queda guardada en `v0` con identificador opaco

#### Scenario: Ancla incompleta en borrador
- **WHEN** el investigador da de alta en una versión en borrador un ancla cuya respuesta esperada vale contra el esquema pero está incompleta (por ejemplo, con la cita de D1 en blanco)
- **THEN** el sistema responde 201, guarda el ancla y devuelve `faltantes` con los códigos que faltan (`cita:d1`); un ancla completa devuelve `faltantes` vacía

#### Scenario: Edición de un ancla incompleta
- **WHEN** el investigador edita un ancla incompleta sin completar la respuesta esperada, y después la edita con una respuesta esperada completa
- **THEN** la primera edición responde 200 con los mismos `faltantes`, la segunda responde 200 con `faltantes` vacía, y la versión se puede congelar

#### Scenario: Respuesta esperada fuera del esquema
- **WHEN** la respuesta esperada usa un régimen o un valor de dimensión que el esquema no define
- **THEN** el sistema responde 400

#### Scenario: Ancla en versión congelada
- **WHEN** el investigador agrega, edita o borra un ancla de una versión congelada
- **THEN** el sistema responde 409

#### Scenario: Episodio inexistente o no terminado
- **WHEN** el episodio del ancla no existe en el registro de episodios del tenant, está `open`, o está `paused` sin `episodio_abandonado` como último evento de cierre
- **THEN** el sistema responde 422

#### Scenario: Evidencia del ancla fija
- **WHEN** después de cargar el ancla el episodio recibe un evento nuevo
- **THEN** la traza del ancla no lo incluye

### Requirement: Enunciado de las anclas
Al crear un ancla, el sistema SHALL registrar la TP y el ejercicio de su episodio para exigir sus enunciados con el mismo criterio que la muestra. Un ancla SHALL mostrarse en Entrenamiento-Recalibración solo cuando sus enunciados estén cargados y revisados; las demás anclas no se bloquean.

#### Scenario: Ancla con enunciado faltante o sin revisar
- **WHEN** un ancla tiene un enunciado sin cargar o sin revisar y otra ancla tiene los suyos revisados
- **THEN** la primera no aparece en ejemplos ni en práctica y el investigador la ve como pendiente, y la segunda sí aparece

#### Scenario: Ancla con enunciado revisado
- **WHEN** un codificador abre una práctica cuyos enunciados están revisados
- **THEN** ve la consigna de la TP y, si corresponde, la del ejercicio, arriba de la traza

### Requirement: Exclusión entre anclas y muestra
El sistema SHALL rechazar con 409 un ancla cuyo episodio pertenece a la muestra del estudio, y SHALL validar la exclusión en el mismo bloqueo que la carga de la muestra, para que ninguna intercalación de operaciones la viole.

#### Scenario: Ancla tomada de la muestra
- **WHEN** el investigador carga un ancla con un `episode_id` que está en la muestra de 150
- **THEN** el sistema responde 409 y no guarda el ancla

#### Scenario: Muestra cargada después del ancla
- **WHEN** existe un ancla con un episodio y luego se sube una muestra que lo contiene
- **THEN** la carga de la muestra responde 409

### Requirement: Ejemplos visibles en el codebook
Las anclas de uso `ejemplo` de la versión vigente SHALL mostrarse en Entrenamiento-Recalibración junto al codebook, con su traza ciega, su respuesta esperada y su explicación.

#### Scenario: Ejemplo con explicación
- **WHEN** un codificador abre Entrenamiento-Recalibración y la vigente tiene un ancla de ejemplo
- **THEN** ve la traza ciega del ejemplo, el régimen y las dimensiones esperadas y la explicación

### Requirement: Práctica a ciegas con devolución después de responder
Las anclas de uso `practica` SHALL presentarse sin respuesta esperada. Recién la respuesta al envío del codificador SHALL incluir la respuesta esperada y la explicación de esa ancla.

#### Scenario: Pedir la práctica
- **WHEN** un codificador pide las anclas de práctica
- **THEN** recibe identificadores opacos y orden, sin respuesta esperada ni explicación

#### Scenario: Responder una práctica
- **WHEN** el codificador envía su respuesta a un ancla de práctica
- **THEN** recibe la respuesta esperada y la explicación de esa ancla, y de ninguna otra

### Requirement: Registro de respuestas de entrenamiento
Cada respuesta de entrenamiento SHALL guardarse como una fila nueva e inmutable con membresía, ancla, versión del codebook vigente, versión de la traza, contenido con el régimen derivado por la regla y el régimen propuesto si lo hay, y momento, separada de las etiquetas del estudio. Un nuevo intento SHALL agregar otra fila.

#### Scenario: Dos intentos sobre la misma ancla
- **WHEN** un codificador responde dos veces la misma ancla
- **THEN** existen dos respuestas de entrenamiento con sus momentos y ninguna etiqueta del estudio nueva

#### Scenario: Intento de modificar una respuesta
- **WHEN** se ejecuta un UPDATE o DELETE sobre una respuesta de entrenamiento
- **THEN** la base lo rechaza

#### Scenario: Respuesta con régimen propuesto
- **WHEN** el codificador responde una práctica con dimensiones que derivan reflexiva y propone superficial con nota
- **THEN** la respuesta se guarda con régimen reflexiva y propuesto superficial, y la devolución compara el régimen derivado con el esperado del ancla

#### Scenario: Entrenamiento con codebook en borrador
- **WHEN** la versión vigente está en borrador y un codificador responde una práctica
- **THEN** la respuesta se guarda con esa versión registrada

### Requirement: Estado vacío sin anclas
Si la versión vigente no tiene anclas, Entrenamiento-Recalibración SHALL mostrar un estado vacío que diga que todavía no hay ejemplos ni práctica cargados.

#### Scenario: Versión sin anclas
- **WHEN** un codificador abre Entrenamiento-Recalibración y la vigente no tiene anclas
- **THEN** ve el codebook, si existe, y el estado vacío de ejemplos y práctica

### Requirement: Retiro del entrenamiento del piloto
Entrenamiento-Recalibración SHALL NOT mostrar las anclas, ejemplos, reglas rápidas ni avisos del entrenamiento del piloto, ni exigir un umbral de aciertos para codificar.

#### Scenario: Apertura de la sección
- **WHEN** cualquier usuario abre Entrenamiento-Recalibración
- **THEN** no aparece ningún texto ni episodio del entrenamiento del piloto
