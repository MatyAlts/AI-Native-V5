# Spec Delta

## Purpose

Definir la prueba técnica del juez sobre las cinco anclas, el criterio técnico medible que habilita congelar su configuración, y el rastro de cada corrida. No hay calibración: el prompt se fija de antemano desde el codebook y la coincidencia de contenido con la respuesta consensuada se registra pero no decide nada.

## ADDED Requirements

### Requirement: Corrida de prueba técnica paso a paso
El sistema SHALL ejecutar una corrida como una secuencia de pasos solicitados por el cliente, cada uno procesando exactamente un par ancla-repetición pendiente en orden determinista, con un número fijo de repeticiones definido por el servicio y no por el pedido, y SHALL poder reanudarse desde el estado persistido.

#### Scenario: Creación de la corrida
- **WHEN** un investigador crea una corrida con un modelo permitido
- **THEN** se inserta una fila `en_curso` con el modelo pedido, `prompt_version`, `prompt_sha256`, `contenido_sha256`, `validador_version`, `repeticiones` igual a la constante del servicio, `n_items` igual a la cantidad de anclas prevista y los parámetros de llamada, y no se llama al modelo

#### Scenario: Versión ya congelada
- **WHEN** la versión vigente de codebook ya tiene una configuración congelada y se pide crear otra corrida
- **THEN** el sistema responde 409 `ya_congelada` y no crea la corrida

#### Scenario: Paso siguiente
- **WHEN** el investigador pide el paso siguiente de una corrida `en_curso` con pares pendientes
- **THEN** el servicio procesa un solo par pendiente, guarda su veredicto y responde con el estado del par sin contenido de la traza y la cantidad de pares que quedan

#### Scenario: Cierre
- **WHEN** se guarda el veredicto del último par pendiente
- **THEN** la corrida pasa a `cerrada` con `cerrada_at` y un `resumen` calculado desde los veredictos persistidos, y no admite más pasos

#### Scenario: Reanudación
- **WHEN** el cliente se interrumpe y vuelve a pedir pasos de la misma corrida más tarde
- **THEN** el servicio continúa con los pares que no tienen veredicto, sin repetir los ya hechos

#### Scenario: Corrida cerrada o abortada
- **WHEN** se pide un paso de una corrida `cerrada` o `abortada`
- **THEN** el sistema responde 409 `corrida_no_en_curso` y no llama al modelo

### Requirement: La coincidencia de contenido se registra y no decide
El sistema SHALL calcular y mostrar, por ancla y repetición, si el régimen y cada dimensión del veredicto coinciden con la respuesta consensuada del ancla, SHALL incluir ese cálculo en el resumen de la corrida marcado como informativo, y SHALL no usarlo en ningún criterio, umbral ni condición de congelado.

#### Scenario: Reporte informativo
- **WHEN** una corrida se cierra
- **THEN** el resumen incluye conteos de coincidencia de régimen y de cada dimensión contra la respuesta consensuada, rotulados `informativo`, junto con los conteos por estado

#### Scenario: Baja coincidencia no bloquea
- **WHEN** una corrida cumple el criterio técnico pero su coincidencia de régimen con lo consensuado es baja
- **THEN** el congelado se permite igual, y la coincidencia queda guardada en la configuración como informativa

### Requirement: Congelar exige un criterio técnico medido en el servidor
El sistema SHALL crear la configuración congelada solo si el servidor, recalculando desde los veredictos persistidos, comprueba las condiciones técnicas del design D8: corrida cerrada y vigente, hashes y parámetros vigentes, cantidad exacta de anclas y de veredictos, todos `ok` con llamada real, modelo efectivo correcto sin mock ni caché, y régimen estable entre repeticiones según el umbral del servicio.

#### Scenario: Corrida que cumple
- **WHEN** un investigador pide congelar una corrida cerrada que cumple todas las condiciones
- **THEN** se crea una fila inmutable en `estudio_juez_config` con fecha, `congelado_por`, `prompt_sha256`, `contenido_sha256`, modelo, proveedores que respondieron, parámetros de llamada, resultado de cada condición y la coincidencia informativa, y se responde 201

#### Scenario: Repeticiones por debajo del mínimo
- **WHEN** se intenta congelar una corrida cuya cantidad de repeticiones es menor que la constante del servicio, o cuyos veredictos son menos que anclas previstas por repeticiones previstas (por ejemplo 14 de 15)
- **THEN** el sistema responde 409 con la condición incumplida y no crea configuración

#### Scenario: Menos anclas que las previstas
- **WHEN** se intenta congelar una corrida cuyas anclas distintas son menos que `N_ANCLAS_V1` (por ejemplo una sola ancla con tres repeticiones, o 4 anclas), aunque todos sus veredictos sean `ok` y estables
- **THEN** el sistema responde 409 con la condición incumplida y no crea configuración

#### Scenario: Parámetros o prompt distintos de los vigentes
- **WHEN** el `prompt_sha256`, los `parametros` de llamada o el `prompt_sha256` de algún veredicto de la corrida difieren de los vigentes del código
- **THEN** el sistema responde 409 con la condición incumplida y no crea configuración

#### Scenario: Veredictos sin llamada real
- **WHEN** algún veredicto de la corrida es `sin_contenido` o `entrada_no_disponible`
- **THEN** no cuenta como éxito, la condición de llamadas reales falla y no se crea configuración

#### Scenario: Estados no válidos, otro modelo, mock o caché
- **WHEN** algún veredicto tiene estado distinto de `ok`, o proveedor `mock`, o `cache_hit` verdadero, o modelo distinto del pedido
- **THEN** el sistema responde 409 con la condición incumplida y no crea configuración

#### Scenario: Inestabilidad entre repeticiones
- **WHEN** la proporción de anclas con el mismo régimen en todas sus repeticiones es menor que `ESTABILIDAD_MIN_V1`
- **THEN** el sistema responde 409 `inestable`, nombra las anclas inestables y no crea configuración

#### Scenario: Corrida abortada, abierta, de otro estudio o con hashes distintos
- **WHEN** la corrida está `abortada` o `en_curso`, es de otro estudio, o su `prompt_sha256`, `contenido_sha256` o `validador_version` difieren de los vigentes
- **THEN** el sistema responde 409 o 404 y no crea configuración

#### Scenario: El cliente no aporta el resultado
- **WHEN** el cuerpo del pedido de congelado incluye un criterio, un resultado o cualquier campo distinto de `corrida_id`
- **THEN** el sistema responde 422, y el resultado del criterio se calcula siempre en el servidor

#### Scenario: Volver a congelar
- **WHEN** se pide congelar una corrida (la misma u otra) de una versión de codebook que ya tiene configuración congelada
- **THEN** el sistema responde 409 `ya_congelada` y la configuración existente no se modifica

### Requirement: Cada corrida y cada cambio de prompt dejan rastro
El sistema SHALL persistir toda corrida aunque se aborte o no cumpla, SHALL exigir un motivo con texto cuando el prompt o el modelo de una corrida nueva difiera del de la anterior de la misma versión de codebook, y SHALL guardar en la configuración el rastro de corridas, prompts, modelos y cambios previos.

#### Scenario: Corrida que no cumple
- **WHEN** una corrida se cierra sin cumplir el criterio técnico
- **THEN** la corrida y todos sus veredictos quedan persistidos y no se crea configuración

#### Scenario: Cambio de prompt sin motivo
- **WHEN** se crea una corrida con un `prompt_sha256` distinto del de la corrida anterior de la misma versión de codebook y sin `motivo`
- **THEN** el sistema responde 422 y no crea la corrida

#### Scenario: Cambio de modelo sin motivo
- **WHEN** se crea una corrida con un modelo distinto del de la corrida anterior de la misma versión de codebook y sin `motivo`, o con un `motivo` de solo espacios
- **THEN** el sistema responde 422 y no crea la corrida

#### Scenario: Cambio de prompt o de modelo con motivo
- **WHEN** se crea esa corrida con un `motivo` declarado
- **THEN** la corrida guarda el `motivo` y queda visible en el listado, junto con el hash y el modelo anteriores

#### Scenario: Rastro en la configuración
- **WHEN** se congela una corrida
- **THEN** la configuración guarda `n_corridas_previas`, `n_prompts_previos`, `n_modelos_previos`, `n_cambios_tras_cumplir` y `corridas_previas` (por corrida: hash, modelo, si cumplió el criterio técnico y qué condiciones falló) de esa versión de codebook

#### Scenario: Cambio después de una corrida que ya cumplía
- **WHEN** se crea una corrida con otro prompt o modelo cuando la corrida anterior ya cumplía todas las condiciones técnicas
- **THEN** la configuración que eventualmente se congele cuenta ese cambio en `n_cambios_tras_cumplir`

### Requirement: No existe calibración
El sistema SHALL no ofrecer conjuntos de ajuste o prueba, sorteo de episodios, registro de ítems de calibración, umbrales de acuerdo con la referencia humana ni variantes de prompt en el contrato.

#### Scenario: Contrato público
- **WHEN** se inspeccionan las rutas y los modelos de cuerpo del juez
- **THEN** no existe ruta ni campo para registrar episodios, elegir partición, fijar umbrales ni elegir variantes de prompt, y las únicas entradas de una corrida son `modelo` y, si corresponde, `motivo`

### Requirement: Las corridas y configuraciones se leen sin contenido de la traza
El sistema SHALL permitir al investigador activo listar y leer corridas y configuraciones con conteos, estados, razones y citas guardadas, y SHALL no devolver el `episode_id`, el texto de la traza ni la salida cruda del modelo.

#### Scenario: Detalle de una corrida
- **WHEN** un investigador lee el detalle de una corrida
- **THEN** recibe el estado, el avance, los veredictos con `item_id` opaco del ancla, estado, razón, régimen, citas canónicas y metadatos del modelo, y no recibe `episode_id` ni `raw_llm_output`
