# Spec Delta

## Purpose

Definir quién puede disparar y leer el juez del estudio, qué ítems puede leer (solo las anclas del propio estudio), cómo se protege la muestra de 150, qué modelos puede usar y con qué validaciones se arma la entrada de cada ítem.

## ADDED Requirements

### Requirement: Solo un investigador activo del estudio dispara y lee el juez
El sistema SHALL exigir, en cada endpoint del juez, una membresía ACTIVA de rol `investigador` del estudio indicado, atada al `X-User-Id` firmado por el gateway, y SHALL rechazar a todo otro caller con un 403 de cuerpo idéntico sin importar el motivo, antes de leer el CTR o llamar al modelo.

#### Scenario: Caller sin membresía en el estudio
- **WHEN** un usuario autenticado sin membresía en el estudio llama, con un cuerpo válido, a cualquier endpoint del juez
- **THEN** recibe 403 con el mismo cuerpo que recibe por un estudio inexistente, y no se realiza ninguna lectura del CTR ni llamada al modelo

#### Scenario: Codificador, membresía revocada o investigador de otro estudio
- **WHEN** llama al juez un usuario con membresía de rol `codificador`, con membresía revocada, o investigador de un estudio distinto del de la ruta
- **THEN** recibe el mismo 403, no ve veredictos ni reportes, y no se lee el CTR

#### Scenario: Cuerpo inválido de un no miembro
- **WHEN** un usuario sin membresía envía un cuerpo que no valida contra el esquema del endpoint
- **THEN** recibe 422 de validación de FastAPI, que no revela la existencia del estudio, y no se realiza ninguna lectura del CTR

#### Scenario: Investigador activo
- **WHEN** un investigador con membresía activa crea una corrida con un modelo permitido
- **THEN** el sistema responde 201 con el identificador de la corrida, la cantidad de ítems y de pares pendientes

#### Scenario: Corrida de otro estudio
- **WHEN** un investigador con membresía en el estudio A pide el detalle o el paso siguiente de una corrida que pertenece al estudio B
- **THEN** recibe 404 y no se revela contenido ni estado de esa corrida

### Requirement: El servidor decide qué ítems se procesan
El sistema SHALL resolver los ítems de cada corrida únicamente desde las anclas de la versión vigente congelada del estudio del caller, y SHALL rechazar todo pedido que traiga identificadores de episodio o de ítem, repeticiones, criterio o cualquier campo no declarado.

#### Scenario: Pedido con campos ajenos
- **WHEN** el cuerpo de un pedido de corrida o de congelado incluye `episode_id`, `item_id`, `items`, `repeticiones`, `criterio` o cualquier otro campo no declarado
- **THEN** el sistema responde 422 y no lee el CTR

#### Scenario: Ítems de una corrida
- **WHEN** un investigador crea una corrida
- **THEN** los ítems procesados son las anclas de la versión vigente congelada de ese estudio, y ningún otro; las anclas de otro estudio o de una versión no vigente no aportan ítems

#### Scenario: Sin versión vigente congelada
- **WHEN** el estudio no tiene una versión vigente congelada o ésta no tiene anclas
- **THEN** el sistema responde 409 antes de leer el CTR o llamar al modelo y no crea la corrida

#### Scenario: Cantidad de anclas distinta de la prevista
- **WHEN** la versión vigente congelada tiene una cantidad de anclas distinta de la constante `N_ANCLAS_V1` (5), por ejemplo 4
- **THEN** el sistema responde 409 `anclas_distintas_de_lo_previsto` antes de leer el CTR o llamar al modelo y no crea la corrida

### Requirement: La muestra de 150 no se procesa
El sistema SHALL no ofrecer ningún modo, columna ni camino de código que procese un ítem de `estudio_muestra`, y SHALL verificar contra la base, con una lectura nueva para cada par procesado y antes de leer el CTR, que el episodio del ancla no esté en `estudio_muestra` de NINGÚN estudio del tenant (sin filtrar por estudio).

#### Scenario: Estructura de datos y contrato
- **WHEN** se inspeccionan las tablas y el contrato del juez
- **THEN** ninguna tabla tiene columna ni clave foránea hacia `estudio_muestra`, el pedido no admite `modo` y el veredicto referencia solo anclas

#### Scenario: Ancla presente en la muestra
- **WHEN** al procesar el paso siguiente de una corrida el episodio del ancla figura en `estudio_muestra` del mismo estudio
- **THEN** la corrida queda `abortada` con motivo `firewall_muestra` (persistido aunque la respuesta sea un error), la respuesta es 409 `firewall_muestra`, no se lee el CTR, no se llama al modelo y no se guarda veredicto de ese par

#### Scenario: Ancla presente en la muestra de otro estudio del mismo tenant
- **WHEN** el episodio del ancla figura en `estudio_muestra` de OTRO estudio del mismo tenant (las escrituras de cada estudio filtran por `estudio_id` y no lo impiden)
- **THEN** la corrida queda `abortada` con motivo `firewall_muestra` igual que en el caso anterior, sin CTR, sin modelo y sin veredicto de ese par

#### Scenario: Muestra que cambia durante la corrida
- **WHEN** entre dos pasos de una misma corrida se inserta en `estudio_muestra` una fila con el episodio de una ancla pendiente
- **THEN** el paso siguiente lo detecta porque lee la base en cada par, y la corrida queda `abortada` con `firewall_muestra`

#### Scenario: Muestra con otros episodios
- **WHEN** `estudio_muestra` (de cualquier estudio del tenant) contiene episodios que no son los de las anclas, o está vacía
- **THEN** el paso procede con normalidad; dentro de un estudio la superposición ya la impiden la carga de la muestra y el alta de anclas, y esta verificación es la defensa adicional que además cubre la superposición entre estudios

#### Scenario: Congelado con una ancla que pasó a la muestra
- **WHEN** se pide congelar una corrida y alguna de sus anclas figura ahora en `estudio_muestra`
- **THEN** el sistema responde 409 `firewall_muestra` y no crea configuración

### Requirement: Solo modelos de una lista permitida
El sistema SHALL aceptar únicamente modelos que figuren en la lista permitida de la configuración del servicio y SHALL rechazar el pedido si la lista está vacía.

#### Scenario: Modelo fuera de la lista
- **WHEN** un investigador crea una corrida con un `modelo` que no está en la lista permitida
- **THEN** el sistema responde 422 `modelo_no_permitido`, no crea corrida y no hace ninguna llamada al proveedor

#### Scenario: Lista vacía
- **WHEN** la lista permitida no está configurada
- **THEN** el sistema responde 503 `sin_modelos_permitidos` y no crea corrida

### Requirement: La entrada se arma con las mismas validaciones que ve el codificador
El sistema SHALL armar la entrada de cada ítem con la misma implementación de enunciado revisado y de evidencia fija que usa el endpoint de traza del codificador, SHALL aplicar el mismo filtro de traza con el `seq_tope` fijado en el ancla (ningún evento posterior al tope ni fuera de la lista blanca llega al prompt), y SHALL negarse a llamar al modelo si alguna validación falla.

#### Scenario: Evidencia alterada
- **WHEN** el tope de `seq` o de cadena fijado en el ancla no coincide con lo leído del CTR
- **THEN** el par queda con veredicto `entrada_no_disponible` y razón `evidencia_alterada`, y no se llama al modelo

#### Scenario: Enunciado sin revisar, episodio inexistente o CTR caído
- **WHEN** falta el enunciado revisado, el episodio no existe o el CTR no responde
- **THEN** el par queda `entrada_no_disponible` con la razón correspondiente y no se llama al modelo

#### Scenario: Versión de traza distinta al crear la corrida
- **WHEN** al crear una corrida la `traza_version` del estudio no es la del código
- **THEN** el sistema responde 409 `traza_version_distinta`, no se crea ninguna fila (no hay corrida que abortar) y no se lee ningún episodio

#### Scenario: Versión de traza distinta en un paso
- **WHEN** al procesar el paso siguiente de una corrida `en_curso` la `traza_version` del estudio no es la del código
- **THEN** la corrida queda `abortada` con motivo `traza_version_distinta` y ese estado queda persistido aunque la respuesta sea el error 409 `traza_version_distinta`; no se lee ningún episodio

#### Scenario: Prompt distinto al reanudar
- **WHEN** al procesar el paso siguiente el `prompt_sha256` calculado por el código difiere del de la corrida (por ejemplo tras un deploy)
- **THEN** la corrida queda `abortada` con motivo `prompt_distinto`, persistido aunque la respuesta sea 409, y no se lee ningún episodio ni se llama al modelo

#### Scenario: Evento posterior al tope o fuera de la lista blanca
- **WHEN** el CTR devuelve eventos con `seq` posterior al `seq_tope` del ancla o con campos fuera de la lista blanca de `traza_v1`
- **THEN** los mensajes enviados al modelo no contienen esos eventos ni esos campos

#### Scenario: Misma implementación para el codificador
- **WHEN** se ejecutan las pruebas existentes del endpoint de traza del codificador tras la extracción
- **THEN** pasan sin ser modificadas

### Requirement: Esquema del juez verificado en runtime
El sistema SHALL comprobar, antes de crear una corrida, de procesar un paso o de congelar, que las tablas del juez existen, y SHALL rechazar el pedido si no.

#### Scenario: Migración no aplicada
- **WHEN** se crea una corrida, se procesa un paso o se congela y falta alguna de las tablas del juez
- **THEN** el sistema responde 503 `esquema_juez_incompleto` sin leer el CTR ni llamar al modelo
