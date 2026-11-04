# Spec Delta

## Purpose

Guarda el codebook de un estudio de codificación como versiones con texto y esquema de formulario, distingue borradores de versiones congeladas inmutables y fija cuál rige el entrenamiento y la codificación.

## ADDED Requirements

### Requirement: Versiones de codebook con texto y esquema
El investigador SHALL poder crear versiones de codebook del estudio con una etiqueta, un texto Markdown y un esquema de formulario. Una versión nueva SHALL nacer en estado borrador, vacía o clonando texto, esquema y anclas de otra versión del mismo estudio.

#### Scenario: Carga del borrador v0
- **WHEN** el investigador crea la versión `v0` y sube un archivo Markdown y un esquema válido
- **THEN** la versión queda en borrador con ese texto y ese esquema

#### Scenario: Clonado
- **WHEN** el investigador crea `v1` clonando `v0`
- **THEN** `v1` queda en borrador con el mismo texto, esquema y anclas que `v0`, y `v0` no cambia

#### Scenario: Etiqueta repetida
- **WHEN** el investigador crea una versión con una etiqueta que ya existe en el estudio
- **THEN** el sistema responde 409

### Requirement: Validación del esquema de formulario
El sistema SHALL rechazar con 400 un esquema que no cumpla el meta-esquema cerrado: dimensiones con clave, nombre, valores y valores que exigen cita; regímenes con clave y nombre; régimen de evidencia insuficiente incluido entre los regímenes; reglas de dimensiones opcionales y notas obligatorias que referencian regímenes existentes; confianza nula o con valores; regla de régimen ordenada cuyas condiciones solo referencian dimensiones, valores y regímenes declarados.

#### Scenario: Régimen de evidencia insuficiente inexistente
- **WHEN** el esquema declara como evidencia insuficiente una clave que no está entre sus regímenes
- **THEN** el sistema responde 400

#### Scenario: Clave desconocida en el esquema
- **WHEN** el esquema trae una clave que el meta-esquema no define
- **THEN** el sistema responde 400

#### Scenario: Regla de régimen con referencia inexistente
- **WHEN** una regla de régimen usa una dimensión, un valor o un régimen que el esquema no declara
- **THEN** el sistema responde 400

#### Scenario: Regla de régimen válida
- **WHEN** el esquema declara reglas ordenadas (reflexiva si D1 presente, D2 o D3 presente y D4 interlocutor; pasiva si D4 transferencia con cita y D1, D2 y D3 ausentes), un régimen por defecto y evidencia insuficiente como exento
- **THEN** el esquema se acepta

#### Scenario: Dimensión con un solo valor
- **WHEN** una dimensión declara un solo valor posible
- **THEN** el sistema responde 400

### Requirement: Congelamiento e inmutabilidad
El investigador SHALL poder congelar una versión en borrador con texto no vacío y esquema válido. Al congelar, el sistema SHALL registrar fecha, autor y un sha256 del texto, el esquema y las anclas en forma canónica. Una versión congelada SHALL NOT poder editarse ni borrarse, y sus anclas SHALL NOT poder agregarse, editarse ni borrarse, ni por la API ni por la base.

#### Scenario: Congelar
- **WHEN** el investigador congela `v1`
- **THEN** `v1` queda congelada con fecha, autor y sha256

#### Scenario: Anclas idénticas dan el mismo sha
- **WHEN** dos versiones tienen el mismo texto, esquema y anclas con los mismos datos y distinto identificador opaco
- **THEN** al congelarlas sus sha256 son iguales

#### Scenario: El sha cubre las anclas
- **WHEN** dos versiones tienen el mismo texto y esquema y difieren en una explicación de ancla
- **THEN** al congelarlas sus sha256 son distintos

#### Scenario: Editar una versión congelada por la API
- **WHEN** el investigador envía un cambio de texto, de esquema o de anclas sobre `v1` congelada
- **THEN** el sistema responde 409 y nada cambia

#### Scenario: Editar una versión congelada en la base
- **WHEN** se ejecuta un UPDATE o DELETE directo sobre la fila de `v1` congelada, o un INSERT, UPDATE o DELETE directo de un ancla de `v1`
- **THEN** la base lo rechaza

#### Scenario: Congelar texto vacío
- **WHEN** el investigador intenta congelar una versión con texto vacío
- **THEN** el sistema responde 422 y la versión sigue en borrador

### Requirement: Revalidación de anclas al editar el esquema y al congelar
Al guardar el esquema de una versión en borrador, el sistema SHALL guardarlo y devolver en `anclas_invalidas` cada ancla de esa versión cuya respuesta esperada no valga contra el esquema guardado o no esté completa según él (la completitud del cierre, motivos con prefijo `incompleta:`), con `item_id`, `uso`, `orden` y `motivos`, sin rechazar. Congelar con alguna ancla así SHALL responder 422 y dejar la versión en borrador.

#### Scenario: Esquema que invalida un ancla
- **WHEN** una versión en borrador tiene un ancla de práctica con D4 interlocutor y el investigador guarda un esquema cuya regla de reflexiva exige D4 oráculo, o que renombra una dimensión, quita un valor o deja de mirar D4
- **THEN** el sistema responde 200 con el esquema guardado y `anclas_invalidas` con esa ancla (`item_id`, `uso` practica, `orden` 1) y un motivo que nombra el régimen o la dimensión afectada

#### Scenario: Esquema que deja incompleta un ancla
- **WHEN** una versión en borrador tiene un ancla con D2 presente sin cita y el investigador guarda un esquema que exige cita para D2 presente
- **THEN** el sistema responde 200 y `anclas_invalidas` trae esa ancla con el motivo `incompleta: cita:d2`

#### Scenario: Congelar con un ancla incompleta
- **WHEN** el investigador congela una versión con un ancla sin régimen, sin una dimensión, con una cita en blanco o exenta sin notas
- **THEN** el sistema responde 422 con `codigo` `anclas_invalidas` y, en los motivos de esa ancla, `incompleta:` seguido del código faltante (`regimen`, `dimension:<clave>`, `cita:<clave>`, `notas`), y la versión sigue en borrador sin sha256

#### Scenario: Esquema que no invalida anclas
- **WHEN** el investigador guarda un esquema nuevo y la única ancla es exenta (régimen de evidencia insuficiente con nota)
- **THEN** el sistema responde 200 con `anclas_invalidas` vacía, y congelar después responde 200

#### Scenario: Congelar con anclas inválidas
- **WHEN** el investigador congela una versión con un ancla que no vale contra su esquema
- **THEN** el sistema responde 422 con `detail` igual a `{codigo: "anclas_invalidas", anclas: [{item_id, uso, orden, motivos}], errores: [texto por ancla]}`, y la versión sigue en borrador sin sha256

### Requirement: Versión vigente del estudio
El investigador SHALL poder fijar cuál versión del estudio es la vigente, en borrador o congelada. El sistema SHALL rechazar con 409 cambiar la vigente cuando ya existen etiquetas de codificación del estudio.

#### Scenario: Fijar vigente antes de codificar
- **WHEN** no hay etiquetas del estudio y el investigador fija `v1` como vigente
- **THEN** `v1` pasa a ser la vigente

#### Scenario: Cambiar vigente con etiquetas
- **WHEN** existe al menos una etiqueta del estudio y el investigador fija otra versión como vigente
- **THEN** el sistema responde 409 y la vigente no cambia

### Requirement: Lectura del codebook vigente
Todo miembro activo del estudio SHALL poder leer la versión vigente: etiqueta, estado, texto Markdown, esquema y, si está congelada, su sha256. Sin versión vigente, el sistema SHALL responder que no hay codebook.

#### Scenario: Codificador lee el codebook
- **WHEN** un codificador abre Entrenamiento-Recalibración con `v0` en borrador vigente
- **THEN** ve el texto de `v0` renderizado y una marca visible de que es un borrador

#### Scenario: Sin codebook
- **WHEN** el estudio no tiene versión vigente y un miembro abre Entrenamiento-Recalibración
- **THEN** ve un estado vacío que dice que todavía no hay codebook cargado

### Requirement: Sin contenido de codebook en el código
El código entregado SHALL NOT contener texto de definiciones de regímenes o dimensiones, reglas de decisión ni esquema de formulario por defecto; todo eso SHALL venir de la versión cargada.

#### Scenario: Revisión del código entregado
- **WHEN** se buscan en el código del panel y del servicio los textos del entrenamiento del piloto ("la trampa", "sobreuso manda", "Si ves que sobreusa al tutor, es pasivo") y los `episode_id` de las 7 anclas del piloto
- **THEN** no aparece ninguno
