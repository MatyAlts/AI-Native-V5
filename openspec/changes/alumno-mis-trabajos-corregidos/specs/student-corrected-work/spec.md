## Purpose

Que el alumno conserve su trabajo una vez corregido: ver y descargar, en sólo
lectura, su nota y la devolución por criterio de cada TP, y el código que entregó
en cada ejercicio, sin que mirarlo deje rastro en la traza cognitiva de la tesis.

## ADDED Requirements

### Requirement: El alumno ve su trabajo corregido por TP
El web-student SHALL ofrecer, para cada entrega propia en estado `graded` o
`returned`, una vista de sólo lectura que muestre: el código y título del TP,
la `nota_final`, el `feedback_general` y la lista de criterios con
`puntaje / max_puntaje` y comentario. La vista SHALL estar disponible aunque la
TP esté archivada.

#### Scenario: Entrega calificada de una TP publicada
- **WHEN** el alumno abre su trabajo corregido de una entrega `graded`
- **THEN** ve el título del TP, la nota final, la devolución general y cada criterio con su puntaje y comentario

#### Scenario: Entrega calificada de una TP archivada
- **WHEN** la TP de la entrega está `archived`
- **AND** el alumno abre su trabajo corregido
- **THEN** ve la nota, la devolución por criterio y el código entregado igual que si la TP estuviera publicada

#### Scenario: Entrega devuelta
- **WHEN** la entrega está `returned` y el alumno todavía no la re-entregó
- **THEN** la vista muestra la nota y la devolución, y dice con palabras que el docente la devolvió para revisar

#### Scenario: Entrega sin corregir
- **WHEN** la entrega está `submitted` o `draft`
- **THEN** la vista de trabajo corregido no se ofrece para esa entrega

### Requirement: El alumno ve el código que entregó, por ejercicio
La vista SHALL mostrar, por cada ejercicio de la entrega y en el orden de la TP,
el código **sellado al entregar** (el artefacto de la entrega), en modo sólo
lectura. Cuando el título del ejercicio no se pueda resolver, SHALL mostrarse
"Ejercicio N" con su número de orden, nunca un identificador interno.

#### Scenario: TP con varios ejercicios
- **WHEN** la entrega tiene artefactos para los ejercicios 1, 2 y 3
- **THEN** la vista muestra tres bloques, en ese orden, cada uno con el código entregado de ese ejercicio

#### Scenario: Título no resoluble
- **WHEN** el título de un ejercicio no se puede obtener (por ejemplo, la TP está archivada)
- **THEN** el bloque se rotula "Ejercicio N" y el código igual se muestra

#### Scenario: Entrega sin código guardado
- **WHEN** la entrega no tiene artefactos (entrega `legacy`)
- **THEN** la vista dice con palabras que esa entrega es anterior a que la plataforma guardara el código entregado
- **AND** no ofrece botón de descarga para ningún ejercicio
- **AND** la nota y la devolución se siguen mostrando

#### Scenario: El código no se pudo cargar
- **WHEN** la lectura del código entregado falla por red o por el servidor
- **THEN** la vista lo dice con palabras y no lo presenta como "sin código"

### Requirement: Sólo el último intento por ejercicio
La vista SHALL mostrar, por ejercicio, únicamente el código sellado en la entrega
vigente. Los intentos previos a una reapertura NO SHALL mostrarse ni ofrecerse
para descarga en esta versión.

#### Scenario: Ejercicio reabierto y re-entregado
- **WHEN** el docente devolvió la entrega, el alumno reabrió un ejercicio y volvió a entregar
- **AND** el docente la calificó de nuevo
- **THEN** la vista muestra sólo el código de la última entrega, no el del intento anterior

#### Scenario: Re-entregada y todavía sin recalificar
- **WHEN** la entrega pasó de `returned` a `submitted`
- **THEN** no se ofrece como trabajo corregido, para no atribuir la nota vieja al código nuevo

### Requirement: El alumno descarga cada ejercicio
La vista SHALL ofrecer, por ejercicio con código entregado, un botón "Descargar"
que genere un archivo de código fuente con la misma forma que la descarga
existente del episodio: encabezado comentado, el código entregado, y la charla
alumno–tutor del episodio de ese artefacto comentada al pie. La extensión SHALL
seguir el lenguaje del artefacto (`.py` o `.java`).

#### Scenario: Descarga de un ejercicio Python
- **WHEN** el alumno aprieta "Descargar" en un ejercicio cuyo artefacto es Python
- **THEN** el navegador descarga un `.py` cuyo cuerpo es exactamente el código entregado

#### Scenario: Descarga de un ejercicio Java
- **WHEN** el artefacto es Java
- **THEN** el archivo descargado es `.java` y la charla va comentada con `//`

#### Scenario: La charla no se puede recuperar
- **WHEN** la lectura del episodio del artefacto falla
- **THEN** la descarga igual entrega el código, sin la charla, y avisa con palabras que la charla no se pudo incluir

#### Scenario: Error en un ejercicio no bloquea a los demás
- **WHEN** falla la descarga del ejercicio 2
- **THEN** el error se muestra junto a ese ejercicio y los botones de los demás siguen operativos

### Requirement: Ver y descargar no altera la traza ni los resultados de la tesis
Abrir la vista, recorrerla y descargar SHALL ser estrictamente de sólo lectura:
NO SHALL emitir eventos al CTR, NO SHALL escribir en la cadena, NO SHALL abrir,
reanudar, cerrar ni crear episodios, NO SHALL crear ni modificar entregas o
calificaciones, y NO SHALL disparar clasificación ni analytics. Toda llamada de
red de la vista SHALL ser un `GET`.

#### Scenario: Recorrido completo sin escrituras
- **WHEN** el alumno abre la vista, la recorre y descarga todos sus ejercicios
- **THEN** todas las requests de red que hizo la vista son `GET`
- **AND** ninguna apunta a `/api/v1/episodes/{id}/events/*`, `/close`, `/abandoned`, `/resume`, `/message`, `/reflection`, `/classify_episode/*` ni al `POST /api/v1/entregas`

#### Scenario: Salir de la pestaña dentro de la vista
- **WHEN** el alumno cambia de pestaña o cierra la ventana estando en la vista
- **THEN** no se emite `pestana_perdida`, `pestana_recuperada` ni `episodio_abandonado`

### Requirement: Sólo lo propio
La vista SHALL mostrar únicamente entregas, calificaciones, código y charlas del
alumno autenticado. Un identificador ajeno NO SHALL devolver contenido.

#### Scenario: Entrega de otro alumno
- **WHEN** se pide el trabajo corregido de una entrega que no es del alumno autenticado
- **THEN** no se muestra código, nota ni charla, y la vista lo informa como no disponible

### Requirement: Accesible por teclado
Todo control de la vista (volver, descargar) SHALL ser operable por teclado con
foco visible, y la nota NO SHALL comunicarse sólo por color.

#### Scenario: Navegación por teclado
- **WHEN** el alumno recorre la vista con Tab
- **THEN** llega a cada botón "Descargar" y al de volver, con foco visible, y los activa con Enter
