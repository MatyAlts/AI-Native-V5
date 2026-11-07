# Spec Delta

## Purpose

Producir, para un ancla de un estudio de codificación con codebook vigente congelado, un veredicto del juez LLM que use la misma entrada, el mismo esquema de dimensiones y la misma regla de régimen que un codificador humano, con citas verificadas, el modelo efectivo registrado y guardado separado de las etiquetas de producción y de las humanas.

## ADDED Requirements

### Requirement: Entrada idéntica a la de un codificador humano y ciega a etiquetas
El sistema SHALL construir el prompt del juez con el texto del `contenido_md` del codebook vigente congelado, un encuadre fijo de formato y de citas, el contrato de salida derivado del esquema del estudio, el enunciado mostrado y los elementos de la traza ciega del ítem (mismos localizadores y `t_seg`), y SHALL excluir el `episode_id`, el `item_id`, toda etiqueta humana o respuesta esperada, las explicaciones de las anclas y todo veredicto de producción.

#### Scenario: Ancla con codebook vigente congelado
- **WHEN** el motor procesa un ancla de un estudio con versión vigente congelada
- **THEN** los mensajes enviados al modelo contienen el enunciado del TP y del ejercicio, el `contenido_md` y los elementos con su `n` y `k`, y no contienen el valor real del `episode_id` ni del `item_id` de la fixture, ni claves ni valores de `respuesta_esperada`, ni el texto `explicacion_md` de ninguna ancla

#### Scenario: El encuadre no lleva ejemplos
- **WHEN** se inspecciona el encuadre fijo del prompt
- **THEN** solo contiene instrucciones de formato de salida y de citas, y ningún valor de dimensión ni clave de régimen del esquema (comparación por palabra completa), ni ejemplo de resultado

#### Scenario: El contrato de salida viaja en el prompt
- **WHEN** el motor arma los mensajes para un ancla, sea cual sea el proveedor del modelo
- **THEN** el mensaje de sistema contiene el esquema de salida con los nombres exactos de las claves (`respuestas`, `valor`, `cita`, `regimen`, `confianza`, `es_frontera`, `notas`, cada clave de dimensión del esquema, cada valor permitido y cada régimen), de modo que el modelo conoce el formato aunque el proveedor no aplique `response_format`, y el contrato no contiene datos de ningún ítem

#### Scenario: Una respuesta de formato esperado se interpreta
- **WHEN** un modelo cuya única fuente de formato es el contenido de los mensajes recibidos responde con un objeto que cumple el contrato (incluida una de evidencia insuficiente con dimensiones omitidas)
- **THEN** la respuesta atraviesa la validación de forma y la evaluación y termina `ok`; y si los mensajes no contenían el contrato, esa misma prueba falla

#### Scenario: Sin esquema estricto
- **WHEN** se inspecciona el pedido enviado al ai-gateway
- **THEN** el `response_format` es de tipo `json_schema` sin `strict`, las dimensiones no son requeridas en el esquema y la garantía del formato no depende de que el proveedor lo aplique

#### Scenario: Codebook vigente sin congelar
- **WHEN** el estudio no tiene una versión vigente congelada
- **THEN** el sistema rechaza el pedido antes de leer el CTR o llamar al modelo y no produce veredicto

### Requirement: Régimen y completitud por la misma regla que el formulario humano
El sistema SHALL declarar `ok` un veredicto solo si pasa, en el orden único de design D7b (forma, presencia de dimensiones, citas, coherencia con la regla, completitud), usando `evaluar_pedido` y `faltantes_cierre` de `estudio_esquema.py` sin una segunda implementación de la regla, y SHALL admitir dimensiones vacías cuando el esquema lo declara para el régimen elegido.

#### Scenario: Dimensiones completas y coherentes
- **WHEN** el modelo devuelve valores, citas válidas y un régimen que coincide con el derivado por la regla, y no faltan cita requerida, notas ni confianza
- **THEN** el veredicto queda `ok` con ese régimen y `regimen_regla` igual a `regimen`

#### Scenario: Régimen afirmado distinto del derivado
- **WHEN** el modelo afirma un régimen no exento distinto del que deriva la regla sobre sus dimensiones
- **THEN** el veredicto queda `inconsistente` con ambos regímenes en la razón y sin régimen válido

#### Scenario: Evidencia insuficiente sin dimensiones
- **WHEN** el modelo elige el régimen que el esquema declara en `dimensiones_opcionales_si_regimen`, deja las dimensiones vacías o nulas, y entrega las `notas` que ese régimen exige y la `confianza` (obligatoria en el esquema)
- **THEN** el veredicto queda `ok`, sin exigir dimensiones ni coincidencia con la regla

#### Scenario: Evidencia insuficiente sin notas o sin confianza
- **WHEN** el modelo elige ese régimen exento pero no entrega las `notas` exigidas, o no entrega la `confianza`
- **THEN** el veredicto queda `incompleto` con la lista de faltantes (`notas`, `confianza`) en la razón

#### Scenario: Dimensión faltante con régimen no exento
- **WHEN** el modelo elige un régimen no exento y omite o deja nula una dimensión (con el esquema real, `evaluar_pedido` levantaría 422 en este caso)
- **THEN** el veredicto queda `incompleto` con la dimensión faltante en la razón, y no `respuesta_malformada` ni `inconsistente`, porque la presencia de dimensiones se evalúa antes de la coherencia

#### Scenario: Clave regimen_propuesto
- **WHEN** la respuesta del modelo incluye `regimen_propuesto`
- **THEN** el veredicto queda `respuesta_malformada`, porque el contrato del juez no lo admite (design D7, decisión 9)

#### Scenario: Cita requerida vacía, notas o confianza exigidas ausentes
- **WHEN** el valor elegido exige cita y está vacía, o el esquema exige `notas` o `confianza` y faltan
- **THEN** el veredicto queda `incompleto` con la lista de faltantes y no cuenta como `ok`

#### Scenario: Régimen omitido
- **WHEN** la respuesta del modelo no incluye `regimen`
- **THEN** el veredicto queda `respuesta_malformada`, sin inferir el régimen de las dimensiones

### Requirement: Citas con gramática compatible con las humanas y validadas contra la traza
El sistema SHALL aceptar en las citas las formas con que citan los humanos (palabra de tipo en singular o plural, listas, rangos, `mensaje` como sinónimo de `turno` y el localizador global `#n`), SHALL validar cada localizador contra los elementos servidos del ítem y SHALL guardar la forma canónica además del texto original.

#### Scenario: Las cinco citas literales de las anclas
- **WHEN** se validan `mensaje 1`, `mensaje 4 y ejecución 1`, `ejecuciones 2 y 3`, `ejecuciones 7 a 9` y `mensajes 1, 3 y 5` contra una traza fixture donde esos localizadores existen
- **THEN** todas validan y la forma canónica enumera cada elemento citado con su `tipo`, `k` y `n`

#### Scenario: Turno con varios elementos
- **WHEN** se cita `turno k` y existen un mensaje del alumno y una respuesta del tutor con ese `k`
- **THEN** la forma canónica guarda todos los elementos que resuelven ese `k`

#### Scenario: Un localizador inexistente en una cita con varios
- **WHEN** una cita incluye un localizador inexistente (por ejemplo `ejecuciones 2 y 30` con solo 12 ejecuciones)
- **THEN** el veredicto queda `cita_invalida` y la razón nombra la dimensión y el localizador

#### Scenario: Palabra de tipo seguida de número en prosa
- **WHEN** el texto de la cita contiene una palabra de tipo seguida de un número aunque sea prosa libre (por ejemplo "la lectura 3 veces") y ese localizador no existe
- **THEN** el veredicto queda `cita_invalida`, porque toda palabra de tipo seguida de número es un localizador

#### Scenario: Elementos sin k
- **WHEN** el modelo cita una copia, un pegado o un fin con `#n` existente
- **THEN** la cita valida; sin `#n` esos elementos no son citables

#### Scenario: Cita requerida sin localizador y rango inválido
- **WHEN** el valor elegido exige cita y el texto no contiene ningún localizador, o contiene un rango con extremo inicial mayor que el final o de más de 200 elementos
- **THEN** el veredicto queda `cita_invalida`

### Requirement: Traza sin contenido no llama al modelo
El sistema SHALL producir un veredicto `sin_contenido` con el régimen de evidencia insuficiente del esquema, sin invocar al modelo, cuando la traza servida no tiene ningún elemento de mensaje del alumno, código, ejecución, prueba, nota, copia o pegado, y SHALL no contarlo como llamada real al modelo.

#### Scenario: Episodio sin contenido
- **WHEN** los elementos servidos de un ítem son solo `inicio`, `lectura` o `fin`
- **THEN** el veredicto queda `sin_contenido`, no se registra ninguna llamada al modelo y `modelo_respondio` queda nulo

#### Scenario: Solo copias o pegados
- **WHEN** los elementos servidos incluyen copias o pegados pero ningún otro elemento con contenido
- **THEN** el ítem se envía al modelo, porque el codebook usa los intentos de copiar como marcador de pasiva

### Requirement: Respuesta malformada o truncada no se infiere
El sistema SHALL rechazar como veredicto válido una respuesta del modelo que no parsee como JSON, esté truncada, incumpla la forma del esquema o traiga claves ajenas, sin reintentarla y sin inferir un régimen, validando la forma con código propio del servicio.

#### Scenario: JSON inválido o truncado
- **WHEN** el modelo devuelve JSON inválido, o su salida alcanza el tope de tokens
- **THEN** el veredicto queda `respuesta_malformada`, no se reintenta la llamada y no hay régimen válido

#### Scenario: Clave ajena o valor fuera del enum
- **WHEN** la respuesta incluye una clave no declarada o un valor de dimensión o de régimen fuera de los permitidos
- **THEN** el veredicto queda `respuesta_malformada`

### Requirement: Caída del proveedor y presupuesto no se inventan
El sistema SHALL distinguir un error de infraestructura de la llamada al ai-gateway de una respuesta del modelo, reintentar una vez solo errores de infraestructura, dejar el par con veredicto `llm_caido` si se agota, y abortar la corrida sin reintentos si el ai-gateway responde que el presupuesto está excedido.

#### Scenario: El ai-gateway no responde
- **WHEN** la llamada falla por error de red o HTTP y se agota el reintento
- **THEN** el veredicto queda `llm_caido`, distinguible de `respuesta_malformada`, con `modelo_respondio` nulo y sin régimen válido

#### Scenario: Presupuesto excedido
- **WHEN** el ai-gateway responde HTTP 429 por presupuesto
- **THEN** la corrida queda `abortada` con motivo `presupuesto_excedido`, no se reintenta la llamada y no se guarda veredicto de ese par

### Requirement: Se registra y se exige el modelo que respondió, sin caché
El sistema SHALL persistir el modelo, el proveedor, la marca de caché y el costo tal como los devuelve el ai-gateway, SHALL rechazar como no válida toda respuesta de un modelo distinto del pedido, del proveedor `mock` o de caché, y SHALL enviar en cada intento de llamada una referencia aleatoria que no contenga ningún identificador.

#### Scenario: Responde otro modelo
- **WHEN** el modelo devuelto por el ai-gateway difiere del pedido, aun tras normalizar un único prefijo de namespace
- **THEN** el veredicto queda `modelo_no_pinneado`, guarda ambos nombres y bloquea el congelado

#### Scenario: Proveedor mock
- **WHEN** el proveedor devuelto es `mock`
- **THEN** el veredicto queda `modelo_no_pinneado`

#### Scenario: Respuesta de caché
- **WHEN** el ai-gateway devuelve `cache_hit` verdadero
- **THEN** el veredicto queda `respuesta_de_cache` y no cuenta como repetición válida

#### Scenario: Modelo coincide
- **WHEN** el modelo devuelto coincide con el pedido y no hay caché ni mock
- **THEN** el veredicto sigue su evaluación normal y registra `modelo_respondio` igual al pedido

#### Scenario: Referencia distinta por intento
- **WHEN** se hace una llamada, incluido un reintento del mismo par
- **THEN** cada intento lleva una referencia aleatoria distinta al final del mensaje de usuario, que se guarda en el veredicto, no deriva de `item_id`, `episode_id` ni de ordinales, y no forma parte del `prompt_sha256`

### Requirement: Reproducibilidad registrada por veredicto
Cada veredicto SHALL registrar, en cualquier estado, el modelo pedido, el respondido (nulo si no hubo llamada), `prompt_version`, `prompt_sha256`, el identificador y el `contenido_sha256` de la versión de codebook, la `traza_version` y la `validador_version` de citas.

#### Scenario: Veredicto en cualquier estado
- **WHEN** se produce un veredicto, incluidos los de error
- **THEN** queda registrado con esos campos

#### Scenario: Cambio del texto del encuadre sin nueva versión
- **WHEN** alguien modifica el texto del encuadre sin cambiar `PROMPT_VERSION`
- **THEN** una prueba que fija el `sha256` del encuadre para esa versión falla

#### Scenario: Cambio del armado de mensajes o de los parámetros
- **WHEN** alguien cambia cómo `armar_mensajes` serializa la traza, el orden o la plantilla de los mensajes, el contrato de salida, `max_tokens` o la temperatura, sin tocar el encuadre
- **THEN** el `prompt_sha256` cambia y una prueba que fija el `sha256` de los mensajes completos sobre una fixture fija falla

### Requirement: Todo veredicto se guarda aparte, ligado a su corrida, y la salida cruda no sale por la API
El sistema SHALL persistir todo veredicto, en cualquier estado, en tablas propias del juez ligado a la corrida que lo produjo, SHALL rechazar un segundo veredicto para el mismo par ancla-repetición de una corrida, SHALL no escribir ni leer `classifications`, `interrater_ratings`, `classification_reviews`, `estudio_etiqueta` ni `estudio_etiqueta_historial` desde el juez, y SHALL no devolver `raw_llm_output` por ningún endpoint ni escribirlo en logs.

#### Scenario: Persistencia de un veredicto
- **WHEN** se produce cualquier veredicto, en cualquier estado
- **THEN** se inserta en su propia transacción en `estudio_juez_veredicto` con su `corrida_id`, de forma que un fallo posterior (incluido el del cierre de la corrida) no lo pierde

#### Scenario: Presupuesto excedido persiste el aborto
- **WHEN** el paso recibe HTTP 429 de presupuesto del ai-gateway
- **THEN** la corrida queda `abortada` con `presupuesto_excedido`, leída desde otra sesión, aunque la respuesta al cliente sea el error 409

#### Scenario: Par duplicado
- **WHEN** dos pasos concurrentes producen un veredicto para el mismo par ancla-repetición de la misma corrida
- **THEN** la base rechaza el segundo y el servicio responde 409 `par_ya_procesado`

#### Scenario: Separación de tablas
- **WHEN** corre una prueba estática sobre `src/`
- **THEN** las tablas y modelos del juez solo se referencian desde los módulos permitidos y ningún endpoint del codificador, de progreso o de exportación los consulta

#### Scenario: La salida cruda no sale
- **WHEN** un investigador lee el detalle de una corrida o una configuración, o se procesa un ítem
- **THEN** la respuesta de la API no contiene `raw_llm_output`, y la salida cruda del modelo y el contenido de la traza no aparecen en ningún log

### Requirement: El juez de producción no cambia de comportamiento
El sistema SHALL dejar sin modificar el comportamiento del juez de producción y de sus consumidores existentes.

#### Scenario: Suites existentes
- **WHEN** se ejecutan las suites ya existentes del juez de producción, de `classify_ep` y de F15
- **THEN** pasan sin modificación y sin que `juez_estudio` sea importado desde un archivo de producción existente
