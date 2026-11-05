# Spec Delta

## Purpose

Define cómo dos o más codificadores humanos etiquetan a ciegas una muestra fija de episodios para construir una referencia de investigación, separada de las etiquetas oficiales y de las del piloto.

## ADDED Requirements

### Requirement: Carga de la muestra fija
El investigador SHALL cargar la muestra subiendo el CSV de origen. El sistema SHALL calcular el sha256 de los bytes recibidos, guardar solo la columna `episode_id` y el hash, y descartar las demás columnas sin persistirlas. La carga es todo o nada.

#### Scenario: Carga válida con hash esperado
- **WHEN** el investigador sube un CSV de 150 filas con columnas `estrato,origen,tp,episode_id` y `sha256_esperado` igual al hash del archivo
- **THEN** el estudio queda con 150 ítems, el hash guardado y ningún valor de `estrato`, `origen` ni `tp` persistido

#### Scenario: Hash distinto
- **WHEN** el `sha256_esperado` no coincide con el hash del archivo recibido
- **THEN** el sistema responde 422 y no carga nada

#### Scenario: Duplicados o UUID inválido
- **WHEN** el CSV repite un `episode_id` o trae uno que no es UUID
- **THEN** el sistema responde 422 indicando las filas con problema y no carga nada

#### Scenario: Falta la columna episode_id
- **WHEN** el CSV no tiene encabezado `episode_id`
- **THEN** el sistema responde 422 y no carga nada

#### Scenario: Episodio inexistente o no terminado
- **WHEN** un `episode_id` no existe en el registro de episodios del tenant, está `open`, está `paused` sin `episodio_abandonado` como último evento de cierre, o está marcado con integridad comprometida
- **THEN** el sistema responde 422 indicando cuáles y no carga nada

#### Scenario: Episodio abandonado en la muestra
- **WHEN** la muestra incluye un episodio en estado `paused` cuyo último evento de cierre es `episodio_abandonado`, y el resto está `closed`
- **THEN** la carga se acepta y ese ítem queda con su evidencia fija

#### Scenario: Registro de episodios con forma inválida
- **WHEN** al cargar la muestra el registro de episodios devuelve un episodio con `problema_id` que no es UUID u otra forma inválida
- **THEN** el sistema responde 502 con un mensaje genérico y no carga ningún ítem

#### Scenario: Episodio que es ancla
- **WHEN** un `episode_id` del CSV es ancla de entrenamiento del estudio en cualquier versión del codebook
- **THEN** el sistema responde 409 y no carga nada

#### Scenario: Reemplazo con etiquetas existentes
- **WHEN** ya existe al menos una etiqueta del estudio y el investigador sube otra muestra
- **THEN** el sistema responde 409 y la muestra anterior no cambia

#### Scenario: Codificador intenta cargar
- **WHEN** un codificador sube un CSV de muestra
- **THEN** el sistema responde 403

### Requirement: Evidencia fija desde la carga
Al cargar la muestra, el sistema SHALL fijar por ítem el tope de la evidencia (último evento existente y su encadenamiento). La versión de la lista blanca SHALL ser la fijada en el alta del estudio. Todo lo que los codificadores vean de ese ítem SHALL limitarse a ese tope.

#### Scenario: Evento agregado después de la carga
- **WHEN** después de cargar la muestra un episodio abandonado se reanuda y recibe mensajes y ediciones nuevos
- **THEN** la traza del ítem es idéntica a la de antes del evento nuevo y los localizadores no cambian

### Requirement: Carga manual de enunciados con cobertura
El investigador SHALL cargar los enunciados subiendo un CSV con `tipo`, `tp_id` o `ejercicio_id` y el texto, junto con la muestra o después. El sistema SHALL guardar cada texto con su sha256 y el del archivo, ignorar e informar filas que no correspondan a ningún ítem ni ancla, y devolver la cobertura respecto de los `problema_id` y `ejercicio_id` fijados en la muestra y las anclas.

#### Scenario: Carga completa
- **WHEN** la muestra tiene episodios de dos TPs, una con dos ejercicios distintos, y el investigador sube un CSV con esas dos TPs y esos dos ejercicios
- **THEN** quedan guardados cuatro enunciados con su sha256 y sus alertas, y la cobertura no informa faltantes

#### Scenario: Archivo inválido
- **WHEN** el CSV repite un `(tipo, id)`, trae un `tipo` desconocido, un id que no es UUID o un texto vacío
- **THEN** el sistema responde 422 indicando las filas y no guarda nada de ese archivo

#### Scenario: Faltante informado
- **WHEN** el CSV no trae el enunciado de un ejercicio requerido por la muestra
- **THEN** la carga guarda el resto y la cobertura lista ese ejercicio como faltante con los ítems afectados

#### Scenario: Fila sin uso
- **WHEN** el CSV trae una TP que no corresponde a ningún ítem ni ancla del estudio
- **THEN** esa fila no se guarda y se informa como ignorada

#### Scenario: Recarga de un enunciado ya revisado con otro texto
- **WHEN** el investigador sube un texto distinto para un enunciado que ya fue revisado
- **THEN** el sistema responde 409 y el enunciado revisado no cambia

#### Scenario: Codificador intenta cargar enunciados
- **WHEN** un codificador sube un CSV de enunciados
- **THEN** el sistema responde 403

### Requirement: Revisión de enunciados antes de codificar
El investigador SHALL revisar cada enunciado cargado, aprobándolo o guardando una versión editada. El sistema SHALL conservar el original y su hash, y SHALL rechazar con 409 el guardado de etiquetas de todo el estudio mientras algún enunciado requerido por la muestra falte o no esté revisado.

#### Scenario: Enunciado con alerta
- **WHEN** un enunciado contiene una fecha o "Prof." seguido de un nombre
- **THEN** el panel del investigador lo muestra con esa alerta

#### Scenario: Codificar con enunciados sin revisar
- **WHEN** queda un enunciado de la muestra sin revisar y un codificador guarda una etiqueta
- **THEN** el sistema responde 409

#### Scenario: Codificar con un enunciado faltante
- **WHEN** falta el enunciado de un solo ítem de la muestra y un codificador guarda una etiqueta de otro ítem completo
- **THEN** el sistema responde 409 `enunciados_pendientes`

#### Scenario: Edición del investigador
- **WHEN** el investigador guarda una versión editada de un enunciado
- **THEN** se guardan el texto mostrado, su sha256, autor y fecha, y el original y su hash no cambian

#### Scenario: Revisión cerrada
- **WHEN** se intenta modificar el texto mostrado de un enunciado ya revisado
- **THEN** el sistema y la base lo rechazan

### Requirement: Orden propio y reproducible por codificador
El sistema SHALL presentar a cada codificador todos los ítems de la muestra en un orden aleatorio derivado de una semilla persistida en su membresía, mediante un procedimiento documentado que no dependa del lenguaje ni de su versión. Dos codificadores del estudio SHALL tener semillas distintas.

#### Scenario: Orden estable entre sesiones
- **WHEN** un codificador pide su lista de ítems dos veces
- **THEN** recibe el mismo orden ambas veces

#### Scenario: Orden recomputable
- **WHEN** se toma la semilla y los identificadores de ítem exportados y se aplica el procedimiento documentado
- **THEN** se obtiene exactamente la posición exportada de cada ítem

#### Scenario: Órdenes distintos
- **WHEN** dos codificadores del mismo estudio piden su lista
- **THEN** ambos reciben el mismo conjunto de ítems y las semillas guardadas son distintas

### Requirement: Ítems sin identificadores ni etiquetas de máquina
La lista y el detalle de ítems para el codificador SHALL contener solo el identificador opaco del ítem, su posición y el estado de la etiqueta propia. SHALL NOT contener `episode_id`, comisión, materia, estrato, origen, TP, etiqueta de máquina, veredicto del juez, confianza del juez ni marcas de sobreuso.

#### Scenario: Lista del codificador
- **WHEN** un codificador pide su lista de ítems
- **THEN** ninguna entrada trae `episode_id` ni ninguna clave distinta de identificador opaco, posición y estado propio

### Requirement: Codificación habilitada solo con codebook congelado
El sistema SHALL rechazar con 409 cualquier guardado de etiqueta del estudio si la versión vigente del codebook no está congelada.

#### Scenario: Codebook vigente en borrador
- **WHEN** la versión vigente está en borrador y un codificador guarda una etiqueta
- **THEN** el sistema responde 409 y no guarda nada

### Requirement: Guardado incremental validado contra el esquema
Un codificador SHALL poder guardar su etiqueta de un ítem de forma parcial y volver a editarla mientras su codificación no esté cerrada. Cada dimensión se guarda como un valor del esquema y una cita en texto libre. Cada guardado SHALL registrar la versión del codebook y la versión de la traza, y actualizar su marca de tiempo.

#### Scenario: Guardado parcial
- **WHEN** un codificador guarda solo el valor y la cita de una dimensión
- **THEN** el sistema responde 200 y la etiqueta queda parcial con la versión del codebook y de la traza registradas

#### Scenario: Reedición
- **WHEN** el mismo codificador vuelve a guardar el mismo ítem con otro valor de D4
- **THEN** queda una sola etiqueta vigente para ese ítem y codificador, con el nuevo valor, el régimen derivado actualizado y `updated_at` posterior a `created_at`

#### Scenario: Valor fuera del esquema
- **WHEN** un codificador guarda un valor de dimensión o un régimen que el esquema no define, o una clave desconocida
- **THEN** el sistema responde 400 y no guarda nada

#### Scenario: Ítem ajeno a la muestra
- **WHEN** un codificador guarda una etiqueta sobre un identificador que no es ítem de la muestra del estudio
- **THEN** el sistema responde 404

### Requirement: Régimen derivado por la regla del codebook
Si el esquema vigente declara una regla de régimen, el régimen persistido SHALL ser siempre el que la regla da sobre las dimensiones, salvo un régimen exento elegido explícitamente. El régimen de la regla SHALL guardarse aparte siempre que sea calculable. El sistema SHALL rechazar con 422 un régimen no exento distinto del derivado o enviado con dimensiones incompletas, y SHALL devolver el régimen derivado en cada guardado.

#### Scenario: Régimen derivado
- **WHEN** con una regla que da reflexiva para D1 presente, D2 presente y D4 interlocutor, el codificador guarda esas dimensiones sin régimen
- **THEN** la etiqueta queda con régimen reflexiva y la respuesta lo informa

#### Scenario: Régimen distinto del de la regla
- **WHEN** el codificador guarda esas mismas dimensiones con régimen superficial
- **THEN** el sistema responde 422 y no guarda nada

#### Scenario: Régimen exento
- **WHEN** el codificador elige explícitamente el régimen de evidencia insuficiente con D1 presente, D2 presente y D4 interlocutor cargados
- **THEN** se guarda régimen evidencia insuficiente y, aparte, régimen de la regla reflexiva

#### Scenario: Dimensiones incompletas
- **WHEN** el codificador guarda solo D1 y D2 y la regla referencia D4
- **THEN** la etiqueta queda con régimen nulo

### Requirement: Régimen propuesto por desacuerdo con la regla
Un codificador que considera injusto el régimen de la regla SHALL poder registrar un régimen propuesto, uno de los regímenes del esquema, con nota obligatoria. El régimen propuesto SHALL NOT reemplazar al derivado; el desacuerdo se deriva de que ambos difieran.

#### Scenario: Desacuerdo con nota
- **WHEN** el régimen derivado es reflexiva y el codificador propone superficial con una nota
- **THEN** se guardan régimen reflexiva, régimen propuesto superficial y la nota, y la etiqueta figura con desacuerdo

#### Scenario: Desacuerdo sin nota
- **WHEN** el codificador propone un régimen y deja la nota vacía
- **THEN** el sistema responde 422 y no guarda nada

### Requirement: Historial de guardados
Cada guardado de etiqueta del estudio SHALL agregar una entrada inmutable al historial con el estado completo guardado y su marca de tiempo. El historial SHALL NOT admitir modificación ni borrado.

#### Scenario: Tres guardados
- **WHEN** un codificador guarda el mismo ítem tres veces
- **THEN** el historial de ese ítem y codificador tiene tres entradas en orden

#### Scenario: Intento de modificar el historial
- **WHEN** se ejecuta un UPDATE o DELETE sobre una entrada del historial
- **THEN** la base lo rechaza

### Requirement: Cierre de la codificación
Un codificador SHALL poder cerrar su codificación solo si todos los ítems cumplen la completitud del esquema vigente y tienen régimen, derivado por la regla o exento. Cerrada, el sistema SHALL rechazar con 409 todo guardado de ese codificador.

#### Scenario: Cierre con ítems incompletos
- **WHEN** un codificador pide cerrar con un ítem sin régimen
- **THEN** el sistema responde 422 indicando cuántos ítems faltan y no cierra

#### Scenario: Cita faltante
- **WHEN** un ítem tiene una dimensión con un valor que el esquema marca con cita requerida y la cita está vacía o solo tiene espacios
- **THEN** el cierre se rechaza con 422

#### Scenario: Notas obligatorias
- **WHEN** un ítem tiene el régimen de evidencia insuficiente o la marca de frontera y no tiene notas, y el esquema las exige en ese caso
- **THEN** el cierre se rechaza con 422

#### Scenario: Cierre con régimen propuesto
- **WHEN** todos los ítems están completos y uno tiene régimen propuesto distinto del derivado, con nota
- **THEN** el cierre se registra y ese ítem conserva el régimen de la regla y el propuesto

#### Scenario: Cierre sin muestra cargada
- **WHEN** un codificador pide cerrar con codebook vigente congelado y el estudio no tiene muestra cargada
- **THEN** el sistema responde 409 con `detail` igual a `sin_muestra` y la membresía sigue sin fecha de cierre

#### Scenario: Cierre exitoso y bloqueo posterior
- **WHEN** un codificador con todos los ítems completos cierra y después intenta guardar
- **THEN** el cierre queda registrado con fecha y el guardado posterior responde 409

### Requirement: Tablas inmutables protegidas contra TRUNCATE
La base SHALL rechazar `TRUNCATE` sobre `codebook_version`, `estudio_ancla`, `estudio_etiqueta_historial`, `entrenamiento_respuesta`, `estudio_muestra` y `estudio_enunciado`, también cuando se alcanzan en cascada, con un error `estudio_inmutable: TRUNCATE de <tabla> rechazado`, sin borrar filas de ningún tenant.

#### Scenario: TRUNCATE directo
- **WHEN** se ejecuta `TRUNCATE <tabla> CASCADE` sobre cualquiera de esas seis tablas
- **THEN** la base lo rechaza con el mensaje que nombra esa tabla

#### Scenario: TRUNCATE en cascada desde el estudio
- **WHEN** se ejecuta `TRUNCATE estudio_codificacion CASCADE`
- **THEN** la base lo rechaza

#### Scenario: El historial sobrevive
- **WHEN** existe una entrada de historial y se ejecuta `TRUNCATE estudio_etiqueta_historial`
- **THEN** la base lo rechaza y la entrada sigue existiendo

### Requirement: Operaciones concurrentes serializadas
Guardados, cierre, cambio de versión vigente y carga de muestra SHALL serializarse de modo que ninguna intercalación deje una codificación cerrada incompleta, una etiqueta guardada después del cierre o una etiqueta con una versión distinta de la vigente.

#### Scenario: Guardado concurrente con el cierre
- **WHEN** un guardado que borra el régimen de un ítem y el cierre del mismo codificador llegan a la vez
- **THEN** o el guardado entra primero y el cierre responde 422, o el cierre entra primero y el guardado responde 409

#### Scenario: Guardado concurrente con cambio de vigente
- **WHEN** el primer guardado del estudio y un cambio de versión vigente llegan a la vez
- **THEN** o el cambio entra primero y el guardado usa la nueva vigente, o el guardado entra primero y el cambio responde 409

### Requirement: Aislamiento entre codificadores
Un codificador SHALL ver solo sus propias etiquetas. Ningún endpoint accesible a codificadores SHALL devolver etiquetas, conteos por categoría ni medidas de acuerdo de otro codificador.

#### Scenario: Pedir la etiqueta de otro
- **WHEN** el codificador A pide su etiqueta de un ítem que solo codificó B
- **THEN** recibe la etiqueta vacía de A, no la de B

#### Scenario: Progreso del investigador
- **WHEN** el investigador pide el progreso del estudio
- **THEN** recibe por codificador solo cantidades de ítems completos, parciales y con régimen propuesto, y si cerró, sin valores de etiquetas

### Requirement: Separación de etiquetas oficiales y del piloto
Ninguna operación del estudio SHALL crear, modificar ni borrar filas de `classifications`, `classification_reviews` ni `interrater_ratings`, ni cambiar lo que otras pantallas muestran a docentes o alumnos. Los endpoints y agregados del piloto SHALL seguir respondiendo igual que antes del cambio.

#### Scenario: Flujo completo del estudio
- **WHEN** se carga una muestra, se guardan etiquetas, se cierra y se exporta
- **THEN** la cantidad y el contenido de filas de `classifications`, `classification_reviews` e `interrater_ratings` no cambian

#### Scenario: Agregado del piloto
- **WHEN** existen etiquetas del estudio y se pide el agregado inter-jueces del piloto de una materia
- **THEN** la respuesta es idéntica a la que se obtenía sin etiquetas del estudio
