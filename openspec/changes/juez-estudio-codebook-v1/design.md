# Design: juez-estudio-codebook-v1

## Context

Motivación en `proposal.md`. Base: worktree con HEAD `178c343` (código de `cibse-codificacion-ciega` en `main`; su change de OpenSpec sin archivar). Esta es la versión 4 del plan (vuelta extra acotada, autorizada por Juani el 06/11/2026, que corrige solo los hallazgos de `informes/propose-3-plan-reviewer.md`); la versión 3 eliminó la calibración tras la decisión humana de la opción B. Hechos verificados por lectura de código (planner intentos 1 a 4 y revisor, `informes/propose-2-plan-reviewer.md` E2-E22 y `informes/propose-3-plan-reviewer.md` E1-E23):

- **Codebook v1** y **anclas v1** (fuera del repo, `~/Documentos/MTAC/CIbSE2027_muestra_150/`): 4 dimensiones, 4 regímenes, régimen por §4. Las 5 anclas consensuadas citan `"mensaje 1"`, `"mensaje 4 y ejecución 1"`, `"ejecuciones 2 y 3"`, `"ejecuciones 7 a 9"`, `"mensajes 1, 3 y 5"`. El esquema declara `dimensiones_opcionales_si_regimen: ["evidencia_insuficiente"]`, `notas_obligatorias_si_regimen: ["evidencia_insuficiente"]`, `notas_obligatorias_si_frontera`, `confianza.obligatoria`.
- **`services/estudio_esquema.py`**: `evaluar_pedido` rechaza con 422 un `regimen` no exento con `regimen_regla is None`; `faltantes_cierre` no reporta dimensión faltante si el régimen está en `dimensiones_opcionales_si_regimen`.
- **`services/traza_ciega.py::filtrar_traza(events, seq_tope)`**: todo elemento tiene `n`; `k` por tipo para `lectura, mensaje_alumno, codigo, ejecucion, prueba, nota`; `respuesta_tutor` hereda el `k` del turno (un `turno k` resuelve a dos o más elementos); `inicio, copia, pegado, fin_*` sin `k`.
- **`routes/estudio_trabajo.py`**: `traza_ciega` (líneas ~155-191) valida `traza_version`, enunciado revisado y evidencia fija; `_enunciados_revisados` y `_enunciado_del_item` (líneas ~121-152) aceptan `EstudioMuestra | EstudioAncla`. `cargar_muestra` verifica que ningún episodio sea ancla; `crear_ancla` rechaza episodios que están en la muestra. Ambas escrituras filtran por `estudio_id`: dentro de UN estudio la superposición ancla-muestra queda impedida; entre dos estudios del mismo tenant no hay ninguna barrera (revisor del intento 3, E6 y E7), por eso D5 consulta a nivel tenant.
- **ai-gateway**: la clave de caché incluye `messages`, `model`, `temperature`, `max_tokens`, no `response_format`; `CompleteResponse` trae `model`, `provider`, `cache_hit`; todos los proveedores devuelven `model=request.model` (eco del pedido, no confirmación del proveedor); presupuesto excedido da 429; `mock` si no hay keys; fallback a `llm_fallback_model`. `CompleteResult` en `services/clients.py` ya trae `cost_usd`.
- **Ruta del proveedor** (revisor del intento 3, E13): un modelo con namespace (`google/gemini-2.5-flash`) va por OpenRouter si hay key; si no, se le quita el namespace y va al proveedor nativo. `response_format` solo se reenvía en Mistral, OpenAI y OpenRouter; Gemini solo fija `response_mime_type` y Anthropic no lo usa (E12). De ahí D7: el contrato de salida viaja en el prompt, no depende de `response_format`.
- **Gateway**: `/api/v1/interrater` ya apunta a classifier-service (`proxy.py:64`); timeout del proxy 120 s; `AIGatewayClient` timeout por defecto 60 s.
- **CI**: `apps/classifier-service/tests/integration/` NO corre en CI; `make check-rls` y `test-rls` (solo `ctr_store`) tampoco cubren `classifier_db` en CI; `migrations-dry-run` no migra classifier (revisor E14).
- Lecciones L-NNN: no existen.

## Goals / Non-Goals

**Goals:** un juez con la misma entrada, esquema (el modelo ve el esquema de salida con los nombres exactos de claves) y regla que un codificador humano, disparable solo por un investigador del estudio, sobre las anclas del propio estudio; prompt fijado de antemano desde el codebook; prueba técnica medible; configuración congelada auditable (hashes, modelo efectivo, parámetros, fecha); cero cambio en producción.

**Non-Goals:** calibrar o validar el juez contra humanos; correr sobre los 150 (T-002); kappa o exportación humano+juez; editar el codebook; UI; tocar ai-gateway; procesos de fondo.

## Decisiones

### D1. El juez no es una membresía ni escribe en tablas de etiquetas humanas

`EstudioMembresia` ata un email a un `user_id` firmado; un proceso del servicio no es una persona. El juez se guarda aparte (D8). Lo que sí exige membresía es quién lo dispara: un humano investigador (D2).

### D2. Vía de acceso: endpoints del estudio, membresía de investigador (SUPOSICIÓN hasta la firma de Juani)

Módulo nuevo `routes/estudio_juez.py`, mismo prefijo y auth que `estudio_trabajo.py`. Endpoints:

| Método y ruta | Quién | Qué |
|---|---|---|
| `POST /{clave}/juez/corridas` | investigador | Crea una corrida. Body `{modelo, motivo?}` |
| `POST /{clave}/juez/corridas/{id}/siguiente` | investigador | Procesa UN par ancla-repetición pendiente (D6) |
| `GET /{clave}/juez/corridas` y `/{id}` | investigador | Lista y detalle (avance, resumen, veredictos sin contenido) |
| `POST /{clave}/juez/configuraciones` | investigador | Congela. Body `{corrida_id}`. 409 `ya_congelada` si la versión ya tiene configuración |
| `GET /{clave}/juez/configuraciones` | investigador | Lista |

Reglas: (1) `require_membresia(session, user, clave, (INVESTIGADOR,))` dentro del handler, 403 idéntico (`_prohibido()`), antes de cualquier lectura del CTR o llamada al LLM. FastAPI valida el body antes del handler: un no miembro con body inválido recibe 422, que no revela el estudio (se prueba). (2) Bodies con `extra="forbid"`: `episode_id`, `item_id`, `items`, `repeticiones`, `criterio` dan 422. (3) Los ítems salen de `estudio_ancla` con `estudio_id = estudio.id` y `codebook_version_id = vigente`; no hay otra fuente. (4) El `ROUTE_MAP` no cambia (prefijo ya ruteado); la barrera es la membresía. La premisa de ruteo se cubre con un comentario en `main.py` y una línea en el ADR, no con test (el revisor R4). (5) La cuenta de servicio del CTR (`get_ctr_lector`) se usa en este módulo solo con el `episode_id` de una fila de `estudio_ancla` del estudio del caller, después del firewall (D5). No hay ningún pedido que lleve un `episode_id`. (6) Con la opción B desaparecen el registro de episodios, la lectura fuera del estudio y el proceso de fondo; la superficie nueva es: 5 episodios que los codificadores ya vieron, hacia el proveedor LLM.

Alternativas descartadas: script directo a base y CTR (secretos, sin caller que acote IDs); reutilizar los endpoints del codificador (membresía de máquina, sin trazabilidad).

### D3. Una sola fuente de enunciado y de evidencia: extracción mínima a `services/estudio_traza.py`

Se mueven, sin cambio de lógica, tres piezas de `routes/estudio_trabajo.py`: `enunciados_revisados`, `enunciado_del_item` y `comprobar_evidencia(eventos, seq_tope, chain_hash_tope)` (levanta `EvidenciaAlteradaError`; es el bloque inline de `traza_ciega`). **`_item_del_estudio` NO se mueve** (resuelve ítems de la muestra; llevarlo a un servicio compartido acerca al juez el único resolvedor que no debe usar): el juez resuelve anclas con su propia consulta (D2.3). `traza_ciega` llama a las tres piezas. Criterio: `test_estudio_traza_db.py` y `test_estudio_separacion_db.py` pasan SIN editarse. Alcance a aprobar (decisión 4). Si Juani no lo aprueba, el plan alternativo es duplicar las tres piezas en el juez (peor: dos implementaciones de "la fuente"); vuelve al planner.

Por par, casos sin llamada al LLM con veredicto `entrada_no_disponible` y `razon` en {`evidencia_alterada`, `enunciado_pendiente`, `episodio_inexistente`, `ctr_no_disponible`}. `traza_version_distinta` aborta la corrida (409).

### D4. Gramática de citas (paso 3 de D7b)

`parsear_citas(texto)` y `resolver_citas(parseadas, elementos)`. Normalización: minúsculas, sin tildes, espacios colapsados; el texto alrededor se ignora.

- Palabras de tipo (singular o plural): `mensaje|turno` -> `turno`; `codigo`; `ejecucion|ejecuciones`; `prueba`; `nota`; `lectura`. Toda palabra de tipo seguida de número es un localizador (también en prosa: "la lectura 3 veces" valida `lectura 3`; si no existe es `cita_invalida`, comportamiento declarado).
- Lista de números: `N`, `N a M`, `N-M`, `N hasta M`, separados por `,`, `y`, `e`, `;`; rango con `N <= M` y a lo sumo 200 elementos. Una palabra de tipo nueva corta la lista.
- Global: `#N` (`#N, #M`, `#N-#M`): único modo de citar `copia`, `pegado`, `inicio`, `fin_*`.
- Resolución contra los elementos servidos de ESE ítem: `turno k` es válido si existe un `mensaje_alumno` o `respuesta_tutor` con ese `k` y se guardan TODOS los elementos que resuelven (`respuesta_tutor` hereda `k`); los demás tipos exigen un elemento de ese tipo con ese `k`; `#n` exige un elemento con ese `n`. Multi-token: todos deben existir.
- Cita con texto (no vacía ni solo espacios), requerida (`cita_requerida_si`) y sin localizador: `cita_invalida`. Cita requerida VACÍA: no es `cita_invalida`; la detecta `faltantes_cierre` (`cita:<clave>`) y da `incompleto` (D7b paso 5). Cita no requerida sin localizador: texto libre, forma canónica vacía. Cita no requerida con localizador inexistente: `cita_invalida`.
- Forma canónica: `citas[clave] = [{"tipo","k","n"}, ...]` ordenada por `n`, sin duplicados, más el texto original.
- `VALIDADOR_VERSION` (constante) se persiste en corrida y veredicto, porque no entra en `prompt_sha256`.
- Con la opción B **desaparece el preflight de citas humanas** (I6): las citas de la respuesta consensuada no se usan para decidir nada; no pueden bloquear la prueba técnica. Las cinco citas literales siguen como test de gramática (el juez debería poder emitir esas formas).
- **SUPOSICIÓN** `mensaje k` = `turno k` en cómo citaron los humanos; solo afecta la lectura de la coincidencia informativa y la compatibilidad de gramática; no bloquea nada.

### D5. Firewall ancla-muestra (qué queda de B-N2 con 5 anclas)

La única entrada son las anclas del estudio. Hechos: `cargar_muestra` rechaza una muestra que incluya un ancla de SU estudio, `crear_ancla` rechaza un episodio que esté en la muestra de SU estudio, y las anclas de una versión congelada son inmutables. **Dentro de un estudio** esas dos escrituras impiden la superposición. **Entre dos estudios del mismo tenant no hay barrera**: ambas filtran por `estudio_id`. Un admin puede crear un segundo estudio y un investigador de ese estudio puede cargar como ancla un episodio de la muestra del primero. Es poco probable y no silencioso, pero el change es CRITICAL y la defensa es barata:

- `ancla_en_muestra(session, episode_id) -> bool`: una consulta `EXISTS` fresca a `estudio_muestra` (columna `episode_id` solamente) **sin filtro de `estudio_id`** (la RLS ya acota al tenant del caller), por cada par, ejecutada ANTES de la lectura del CTR y del LLM. Sin foto en memoria; sin lock, porque la ventana es de milisegundos y requiere un estado que las escrituras del propio estudio ya impiden.
- Si da `True` (muestra del mismo estudio o de otro estudio del tenant): la corrida se cierra `abortada` con `firewall_muestra` (HTTP 409 `firewall_muestra`, persistido: ver D6), sin CTR, sin LLM, sin veredicto de ese par.
- `congelar` repite la consulta para todas las anclas de la corrida (409 `firewall_muestra`).
- Muestra no cargada o vacía: NO es error (no hay nada que proteger); se declara y se prueba que el paso procede. "Fail-closed con muestra vacía" bloquearía la prueba técnica temprana sin proteger nada.
- Sin `MUESTRA_ESPERADA`, sin `muestra_sha256` en la corrida, sin bloqueo del estudio.
- Lo que sigue prohibido por construcción: ninguna tabla del juez tiene FK ni columna hacia `estudio_muestra`; no existe `modo`.

### D6. Corrida paso a paso, sin proceso de fondo (I1, I3, R1)

- Constantes del servicio (no están en el pedido): `REPETICIONES_V1 = 3` y `N_ANCLAS_V1 = 5` (PROPUESTAS; decide Juani), 15 pares. No existe forma de bajarlas sin cambiar código, y el criterio de congelado compara con las constantes (D8).
- **Fase síncrona de `POST /corridas`** (4xx/503, sin fila): membresía, esquema del juez, versión vigente congelada con esquema y **exactamente `N_ANCLAS_V1` anclas** (si no, 409 `anclas_distintas_de_lo_previsto`), versión sin configuración congelada (si ya la tiene, 409 `ya_congelada`, D8), `traza_version`, modelo en lista permitida (D10), `motivo` (D8). Después inserta la fila `en_curso`. No llama al modelo ni lee el CTR. En este endpoint un rechazo no deja corrida ni fila `abortada`: no hay nada que abortar.
- **`POST /corridas/{id}/siguiente`**: tres sesiones `tenant_session` y un tramo sin sesión. `tenant_session` hace `commit` al salir y `rollback` ante excepción (`db/__init__.py`), y el tenant dura lo que la transacción; por eso las fases son explícitas y **ningún error HTTP se levanta dentro de un bloque `tenant_session` que tenga algo que persistir**: el bloque devuelve un resultado, se cierra (commit) y recién entonces el handler levanta la excepción.
  1. **Sesión 1** (carga y decisiones; escribe solo abortos): corrida del estudio del caller (404 si no); 409 `corrida_no_en_curso` si no está `en_curso`; `verificar_esquema_juez`; las anclas salen de `corrida.codebook_version_id`, NO de la vigente (que puede cambiar mientras no haya etiquetas); `traza_version` del código contra la del estudio y `prompt_sha256` del código contra el de la corrida; primer par pendiente en el orden `(repeticion, item_id)`; si no hay pendientes, va a la sesión 3; firewall (D5). Abortos de esta fase, todos con `UPDATE` de cierre y commit antes de responder: `traza_version_distinta`, `prompt_distinto` (reanudar tras un deploy con otro prompt mezclaría prompts) y `firewall_muestra`, los tres HTTP 409 con `{codigo: <motivo>}`.
  2. **Sin sesión**: lectura del CTR con `get_ctr_lector` (timeout 15 s), `comprobar_evidencia`, `filtrar_traza(eventos, seq_tope)`, `armar_mensajes` y llamada al modelo (D7). Nada se mantiene abierto durante el LLM.
  3. **Sesión 2** (veredicto): inserta el veredicto del par (`UNIQUE` violado: 409 `par_ya_procesado`, levantado tras cerrar la sesión). Si la llamada devolvió HTTP 429 de presupuesto: en esta sesión se cierra la corrida `abortada` `presupuesto_excedido` SIN veredicto del par, commit, y recién después se responde 409 `presupuesto_excedido`.
  4. **Sesión 3** (cierre): si ya no quedan pendientes, calcula el `resumen` (incluido `criterio`, D8) desde los veredictos persistidos y ejecuta `UPDATE ... SET estado='cerrada', ... WHERE id=:id AND estado='en_curso'`; si afecta 0 filas no es un error (otro `siguiente` cerró primero). Si esta sesión falla, el veredicto ya está persistido y el siguiente `siguiente` ve cero pendientes y cierra.
  Un paso = una llamada al LLM (timeout 40 s, un reintento solo ante infraestructura). Peor caso: 15 s del CTR + 40 s + 40 s = 95 s, dentro de los 120 s del proxy (el 80 s anterior omitía el CTR).
- **Duplicados**: `UNIQUE(corrida_id, ancla_item_id, repeticion)`. Dos pasos concurrentes pueden gastar una llamada de más (acotado: 15 pares); el segundo insert falla y responde 409 `par_ya_procesado`. No hay índice parcial de "una `en_curso` por estudio": una corrida abandonada no consume nada ni bloquea; se reanuda o se ignora.
- **Reanudación**: el estado pendiente se deduce de los veredictos persistidos. Un deploy en medio no deja zombis. El runbook dice no deployar classifier-service con un paso en vuelo (un paso perdido se repite).
- Resumen (`resumen` JSONB, calculado por el servidor desde los veredictos persistidos): conteos por estado; por ancla, regímenes por repetición y `estable`; costo total (`sum(cost_usd)`); `criterio` (resultado de cada condición de D8 y `cumple_tecnico`, calculado con los hashes vigentes al cierre); y bloque `informativo` con la coincidencia (D8).

### D7. Contrato con el LLM y modelo efectivo

Protocol propio `JuezCompleteFn` (misma firma que `AIGatewayClient.complete`; no se importa `CompleteFn` de `regimen_llm.py`). Se inyecta `AIGatewayClient(base_url=settings.ai_gateway_url, timeout=40)` por `Depends` sobreescribible.

**Contrato de salida en el prompt, en todos los proveedores (B1).** `esquema_salida = construir_json_schema(esquema)` es la fuente única del formato. Entra en `armar_mensajes` como parámetro y se escribe en el mensaje de sistema (sección "Contrato de salida", JSON con `sort_keys=True`, `ensure_ascii=False`), con los nombres exactos de las claves (`respuestas`, `valor`, `cita`, `regimen`, `confianza`, `es_frontera`, `notas`, las claves de dimensión del esquema, los valores permitidos y los regímenes). Sin ejemplos. Esto no depende de que el proveedor aplique `response_format` (Gemini y Anthropic no lo hacen) y no abre el prompt a datos de ítems: el esquema no trae episodio, ancla ni etiqueta. Las claves de dimensión (`d1_verbalizacion`, etc.) no aparecen en el texto del codebook (revisor del intento 3, E3): solo el contrato las nombra. El `FRAMING` no copia claves a mano (segunda fuente sin test): dice "devolvé únicamente un objeto JSON que cumpla el contrato de salida".

**`response_format` y `strict`.** Cada llamada manda `response_format = {"type":"json_schema","json_schema":{"name":"veredicto_juez","schema":<esquema_salida>}}` **SIN `strict`**, el mismo sobre no estricto que usa `regimen_llm.py` en producción (revisor, E14). Razón: la regla de OpenAI para esquemas estrictos exige todas las claves en `required` (SUPOSICIÓN: no la probé contra el proveedor; el SDK la refleja, E16), incompatible con dimensiones no requeridas, y el plan no puede depender de ella. `response_format` es una ayuda para los proveedores que lo aplican; la garantía la dan, de forma independiente del proveedor, (1) el contrato en el prompt y (2) el validador local. Las dimensiones quedan NO requeridas en el esquema (la presencia es el paso 2 de D7b, para poder distinguir `incompleto` de `respuesta_malformada`). Si algún proveedor rechazara el sobre, el 502 llega como `llm_caido` en el primer `siguiente` y se ve en el paso 1; no se corrige en silencio. Una respuesta envuelta en un cercado de código (```json) NO se tolera: es `respuesta_malformada` (no se infiere; riesgo declarado, visible en el primer paso).

Cada llamada: `temperature=0.0`, `model=<pedido>`, `feature="estudio_juez"`, `max_tokens=6000`, `tenant_id` del caller, `materia_id=None` (decisión explícita: el juez de producción pasa la materia del episodio para resolver la key BYOK por facultad; resolver la materia de un ancla exigiría una llamada a academic-service que este change no hace. Con `None` la key cae a tenant y luego a env. Test que captura el valor. Si no hay key, el primer paso da `modelo_no_pinneado` o `llm_caido`; la respuesta de Juani sobre proveedor y credenciales cierra esto). Reintentos: 1, solo ante excepción HTTP/red (-> `llm_caido` si se agota); 0 ante JSON inválido o truncado (`output_tokens >= max_tokens`); **HTTP 429 de presupuesto: aborta la corrida `presupuesto_excedido`, sin reintento** (en `/complete` el único 429 es el de presupuesto; un error del proveedor tras reintentos llega como 502).

**`regimen_propuesto` queda fuera del contrato del juez.** El codificador humano puede discrepar de la regla con `regimen_propuesto` (se persiste y se exporta). El esquema de salida del juez no lo incluye (`additionalProperties:false`): un juez que afirma un régimen no exento distinto del que deriva la regla recibe `inconsistente`, que ya registra la discrepancia con ambos regímenes y cuenta contra la condición 4. Consecuencia: la comparación de T-002 no tiene ese canal del juez. Recomendación del planner: dejarlo fuera (el juez aplica la regla, no la discute; la rama "discrepa" de un LLM sería ruido para el paper). Decisión 9 de Juani; si decide incluirlo: el campo nulo entra al contrato, a `armar_mensajes`, a `evaluar_item` y a `estudio_juez_veredicto` (columna nueva), con tests; el hash y la migración lo reflejan.

Validación de forma **local con validador propio** (`validar_forma(schema_dict, obj)`, ~30 líneas: objeto, claves permitidas y requeridas, enums, tipos). No se agrega `jsonschema` (classifier no lo declara).

Referencia anti caché: cada INTENTO de llamada agrega al final del mensaje de usuario `Referencia: <nonce>` con `nonce = secrets.token_hex(8)`. No deriva de `item_id`, `episode_id`, corrida ni ordinal; distinto en cada reintento; se guarda en el veredicto (solo la del ÚLTIMO intento); fuera de `prompt_sha256`. La defensa real sigue siendo el chequeo de `cache_hit`. Efecto declarado: la `referencia` cambia en cada repetición, así que las tres repeticiones NO son entradas idénticas; la estabilidad mide sensibilidad a ese texto, no determinismo puro.

Registro tras cada respuesta: `modelo_respondio = res.model`, `proveedor = res.provider`, `cache_hit`, tokens y `cost_usd`. **Límites declarados**: `res.model` es el eco del modelo pedido, no una confirmación del proveedor; detecta fallback al `llm_fallback_model` y `mock`, no alias ni ruteo interno. El costo de un intento cortado por timeout no entra en `cost_usd`. El timeout de 40 s es menor que los 60 s por defecto de producción y no está medido con 6000 tokens de salida (más el "thinking" de Gemini 2.5): un corte aparece como `llm_caido`, visible, no silencioso. `provider == "mock"` -> `modelo_no_pinneado`; `mismo_modelo(pedido, respondio)` falso (tras normalizar un único prefijo de namespace) -> `modelo_no_pinneado`; `cache_hit` -> `respuesta_de_cache`. En la configuración se guardan `proveedores_respondieron` y el modelo. Temperatura 0 no garantiza determinismo bit a bit; por eso la estabilidad se mide (D8).

### D7b. Evaluación de un veredicto: un solo orden (I1)

`evaluar_item(esquema, elementos, raw)` aplica estos pasos en este orden y se detiene en el primero que falla. La regla de régimen y la completitud son las de `estudio_esquema.py` (`evaluar_pedido`, `faltantes_cierre`); el módulo no define otra. Verificado sobre el código (revisor del intento 3, E2): `evaluar_pedido` con régimen no exento y dimensiones incompletas levanta 422; con `regimen=None` y dimensiones vacías no levanta y `faltantes_cierre` lista `regimen` y `dimension:*`; con un régimen en `dimensiones_opcionales_si_regimen` no lista dimensiones.

1. **Forma** (`validar_forma`, sin tocar el esquema de reglas): JSON inválido o truncado, clave ajena, enum o tipo erróneo, `regimen` ausente -> `respuesta_malformada`.
2. **Dimensiones omitidas con régimen no exento**: si el `regimen` afirmado NO está en `dimensiones_opcionales_si_regimen`, se llama `evaluar_pedido` con el mismo pedido pero `regimen=None` (no levanta por dimensiones) y se toman de `faltantes_cierre` los códigos `dimension:*`; si hay alguno -> `incompleto` con esos códigos. (Es lo que evita el 422 del paso 4 para este caso.)
3. **Citas**: `parsear_citas` y `resolver_citas` sobre cada cita con texto (D4) -> `cita_invalida`.
4. **Coherencia**: `evaluar_pedido` con el régimen afirmado. `PedidoInvalidoError` 422 -> `inconsistente` (con ambos regímenes en la razón); 400 (por ejemplo `es_frontera` cuando el esquema no ofrece la marca) -> `respuesta_malformada`.
5. **Completitud**: `faltantes_cierre` sobre la `Evaluacion` (cita requerida vacía, `notas`, `confianza`) -> `incompleto` con la lista.
6. Si no falló nada: `ok`, `regimen_regla` desde la `Evaluacion`.

`sin_contenido` no pasa por acá: lo decide `hay_contenido(elementos)` antes de armar el prompt (sin llamada). Un `evidencia_insuficiente` válido necesita `notas` Y `confianza` (obligatoria en el esquema v1): sin alguna, paso 5 -> `incompleto`.

### D8. Prompt fijado, criterio técnico y congelado (B-N3, opción B)

**Prompt.** `FRAMING` (constante versionada con `PROMPT_VERSION`) más `contenido_md` del codebook congelado más el contrato de salida (D7), armados por `armar_mensajes(framing, contenido_md, esquema_salida, enunciado, elementos, referencia)`: mensaje de sistema = `FRAMING`, `contenido_md` y contrato; mensaje de usuario = enunciado, elementos y `Referencia`. El `FRAMING` contiene SOLO: (a) rol (aplicar el codebook como codificador del estudio); (b) formato de salida (un objeto JSON que cumpla el contrato de salida, sin texto fuera del JSON); (c) formato de citas (`turno k`, `código k`, `ejecución k`, `prueba k`, `nota k`, `lectura k`, `#n`, como la UI del codificador); (d) usar solo la traza y el enunciado; (e) no inventar localizadores. Sin ejemplos, sin resultados, sin umbrales. Test del `FRAMING` sin ejemplos: no contiene ningún valor de dimensión ni clave de régimen del esquema fixture, comparando por palabra completa (límite de palabra), con valores de la fixture de al menos 6 caracteres y guarda de lista no vacía, para que el test discrimine y no pase por subcadenas cortas.

**`prompt_sha256` cubre todo lo que define la entrada (I7).** `prompt_sha256 = sha256(json canónico de {"framing": FRAMING, "mensajes_referencia": armar_mensajes(FRAMING, contenido_md_de_la_version, esquema_salida, ENUNCIADO_REF, ELEMENTOS_REF, "REF"), "parametros": PARAMETROS_LLAMADA})`, donde `ENUNCIADO_REF` y `ELEMENTOS_REF` son constantes sintéticas del módulo (un elemento de cada tipo, sin datos reales) y `PARAMETROS_LLAMADA` es el dict que también se guarda como `parametros` (`temperature`, `max_tokens`, `feature`, `response_format` = "json_schema_no_estricto", `materia_id` nulo, `timeout_s`, `reintentos`). Así cambiar la serialización de la traza, el orden o la plantilla del armado, el contrato, `max_tokens` o la temperatura mueve el hash, sin depender de que alguien acuerde subir una versión. El hash del codebook es `contenido_sha256` de la versión. Tests golden con literal: `sha256(FRAMING)` para el `PROMPT_VERSION` vigente y `sha256` del `messages` completo de `armar_mensajes` sobre una fixture fija (esquema, `contenido_md`, enunciado, elementos, referencia fijos).

**`contenido_md` es el texto central de la opción B y se verifica antes de la primera corrida (I8).** `contenido_sha256` NO es el hash del texto: cubre `{contenido_md, esquema, anclas}` y nunca coincidirá con el de un archivo. La comprobación definida es sobre un único texto: una persona lee `contenido_md` con `GET /{clave}/codebook/vigente`, calcula `sha256` de ese string codificado en UTF-8 y lo compara con el `sha256` del archivo del codebook elegido, leído tal cual (sin normalizar). La carpeta del codebook tiene dos candidatos (`codebook_v1.md` y `codebook_v1_para_codificadores.md`; el revisor del intento 3 contó 11 y 10 encabezados de nivel 1 o 2, E3): la persona registra en el ADR cuál es y, si el texto cargado es un recorte (secciones 1 a 9), qué recorte. Es la tarea 8.0. Si no coinciden, se lee la diferencia y se decide antes de correr nada. El aviso del test 3.4 sobre `explicacion_md` corre sobre fixtures; sobre el dato real lo cubre esa misma persona en 8.0 (que ninguna `explicacion_md` de las anclas figure copiada en `contenido_md`).

**Regla de no ajuste y su límite (I4).** El texto que firma Juani está en `proposal.md` ("Decisión humana"); acá se define el mecanismo.
- Antes de congelar solo se corrigen fallas técnicas de formato. Crear una corrida cuyo `prompt_sha256` **o `modelo`** difiera de los de la corrida anterior de la misma versión de codebook (la última creada para ese estudio y esa versión, en cualquier estado) exige un `motivo` con texto (422 si falta o es solo espacios). La primera corrida no necesita motivo.
- La corrida guarda `corrida_anterior_id`, `prompt_sha256_anterior` y `modelo_anterior`.
- Dato objetivo para distinguir un cambio técnico de uno de contenido: el `resumen` de cada corrida cerrada trae `criterio.cumple_tecnico`. Si la corrida anterior ya cumplía todas las condiciones técnicas, no había falla técnica que corregir, y un cambio de prompt o de modelo a continuación es un ajuste que el paper debe declarar.
- La configuración guarda `n_corridas_previas`, `n_prompts_previos`, `n_modelos_previos` (distintos de los de la corrida congelada), `n_cambios_tras_cumplir` (corridas que cambiaron prompt o modelo cuando la anterior cumplía) y `corridas_previas` (lista de `{corrida_id, prompt_sha256, modelo, cumple_tecnico, condiciones_falladas}`), para que se vea cuántas veces se repitió una configuración hasta que pasó.
- **Límite honesto**: el código no impide que alguien que ve la coincidencia (se muestra en cada corrida, antes de decidir) cambie el prompt o el modelo; solo impide que sea silencioso. **Regla para el paper**: se puede decir "prompt y modelo fijados antes de ver resultados" únicamente si `n_prompts_previos`, `n_modelos_previos` y `n_cambios_tras_cumplir` son 0; si no, el paper declara esos números y que los cambios se hicieron con la coincidencia a la vista.
- **Una sola configuración por versión de codebook** (decisión 10; recomendación del planner): congelar una segunda vez, sea la misma corrida u otra, responde 409 `ya_congelada` (`UNIQUE(estudio_id, codebook_version_id)` y `UNIQUE(corrida_id)` en la config, el `IntegrityError` mapeado a 409 y con test). Con configuración ya congelada, `POST /corridas` de esa versión responde 409 `ya_congelada`: lo congelado no se ajusta. Alternativa, si Juani la prefiere: reemplazo con `motivo`; rige la fila con `congelado_at` más reciente, las anteriores quedan visibles y la regla del paper cuenta cada reemplazo como ajuste.

**Criterio técnico** (`CRITERIO_TECNICO_V1`, se recalcula en el servidor al cerrar y al congelar, nunca se acepta del cliente). Para la corrida pedida:
1. `estado = cerrada`, de este estudio, sobre la versión de codebook vigente; modelo en la lista permitida.
2. `prompt_sha256`, `contenido_sha256`, `validador_version` y `parametros` de la corrida iguales a los vigentes del código y del estudio, y `prompt_sha256` de cada veredicto igual al de la corrida (reanudar tras un deploy no mezcla prompts).
3. **Cantidad exacta de anclas y de pares**: `corrida.n_items == N_ANCLAS_V1`, `corrida.repeticiones == REPETICIONES_V1`, `count(distinct ancla_item_id) == N_ANCLAS_V1` y `count(veredictos) == N_ANCLAS_V1 * REPETICIONES_V1` con cada ancla en las repeticiones `1..REPETICIONES_V1` (una sola ancla no cumple; el `n_items` ya no se toma de la propia corrida como referencia).
4. Todos los veredictos `ok` y con llamada real (`modelo_respondio` no nulo); `sin_contenido` y `entrada_no_disponible` no suman como éxito.
5. Modelo efectivo: `mismo_modelo(pedido, respondio)` en todos, `proveedor != mock`, `cache_hit` falso en todos.
6. Estabilidad: por ancla, el régimen es idéntico en las `REPETICIONES_V1` repeticiones, y la proporción de anclas estables es `>= ESTABILIDAD_MIN_V1` (0.8, decisión 3 de Juani del 06/11/2026).
7. Firewall repetido (D5), al congelar.

La **coincidencia informativa** (régimen y cada dimensión contra `respuesta_esperada`, por ancla y repetición) va en `resumen.informativo` y se copia a la configuración; no interviene en 1 a 7. Un `sin_contenido` en un ancla haría el criterio inalcanzable: SUPOSICIÓN de que las 5 anclas tienen contenido; si no, vuelve al planner.

**Fragilidad de la estabilidad y qué se hace si falla (I5).** (a) Dos de las 5 anclas son `es_frontera` (dato del intento 1, sin reverificar): son donde más se espera variación. (b) La `referencia` cambia en cada repetición (D7): se mide sensibilidad a ese texto, no determinismo. (c) La condición 4 exige 15 de 15 `ok`: cualquier `cita_invalida`, `incompleto` o `llm_caido` transitorio la rompe (ilustrativo, independencia asumida, sin medir ningún modelo: con 95% de éxito por llamada, 15 de 15 ocurre ~46% de las veces; con 2 anclas de frontera que dan su régimen modal 90% de las veces, ambas estables en 3 repeticiones ~53%). (d) Sin tope de corridas, la barrera se pasa repitiendo (con 20% por corrida, al menos una de 5 pasa ~67%); por eso la configuración guarda `corridas_previas` y la regla del paper arriba. **Regla fijada de antemano ante un ancla de frontera inestable**: NO se toca el prompt ni el modelo (sería un ajuste de contenido, que la opción B prohíbe). La corrida queda como no cumplida, se registra, y se puede repetir la MISMA configuración; cada repetición queda en `corridas_previas`. Si Juani elige `ESTABILIDAD_MIN_V1 = 0.8`, una ancla inestable no impide congelar y queda nombrada en el criterio; si elige 1.0, la salida es repetir. Un tope de corridas por configuración (recomendado, si se quiere, 3) es una decisión de Juani; el plan no lo incluye porque Juani eligió no topar y dejar rastro.

**Reruns.** No hay tope de corridas (Juani, intento 2: "dejando rastro de cada cambio y de cada corrida"; el tope queda como opción de la decisión 3). Congelar usa la corrida pedida, no "la primera evaluable": la elección queda visible por `corridas_previas`.

### D9. Persistencia: 3 tablas (R5, sin `corrida_ajuste_id`)

En `classifier_db`, `models/estudio_juez.py` (SQLite-compatibles en modelos; CHECK, UNIQUE parcial y triggers en la migración), todas con `tenant_id` (`TenantMixin`) y `apply_tenant_rls`:

| Tabla | Contenido clave | Mutabilidad |
|---|---|---|
| `estudio_juez_corrida` | `id`, `estudio_id`, `codebook_version_id`, `contenido_sha256`, `modelo_pedido`, `prompt_version`, `prompt_sha256`, `validador_version`, `repeticiones`, `n_items`, `parametros` (JSONB), `motivo`, `corrida_anterior_id`, `prompt_sha256_anterior`, `modelo_anterior`, `iniciada_at`, `iniciada_por`, `estado` (`en_curso`/`cerrada`/`abortada`), `motivo_aborto`, `cerrada_at`, `resumen` | inmutable salvo UN cierre `en_curso -> cerrada|abortada` que cambia solo `estado`, `cerrada_at`, `motivo_aborto`, `resumen` |
| `estudio_juez_veredicto` | `id`, `estudio_id`, `corrida_id` (FK), `ancla_item_id` (FK), `repeticion`, `respuestas`, `citas`, `regimen`, `regimen_regla`, `confianza`, `es_frontera`, `notas`, `estado`, `razon`, `raw_llm_output` (nullable), `referencia`, `modelo_pedido`, `modelo_respondio` (nullable), `proveedor`, `cache_hit`, `input_tokens`, `output_tokens`, `cost_usd`, `prompt_version`, `prompt_sha256`, `validador_version`, `codebook_version_id`, `contenido_sha256`, `traza_version`, `creado_at`. `UNIQUE(corrida_id, ancla_item_id, repeticion)` | append-only (UPDATE/DELETE/TRUNCATE rechazados) |
| `estudio_juez_config` | `id`, `estudio_id`, `codebook_version_id`, `contenido_sha256`, `modelo`, `proveedores_respondieron`, `prompt_version`, `prompt_sha256`, `validador_version`, `parametros`, `corrida_id` (FK, UNIQUE), `n_corridas_previas`, `n_prompts_previos`, `n_modelos_previos`, `n_cambios_tras_cumplir`, `corridas_previas` (JSONB), `criterio` (resultado de cada condición), `coincidencia_informativa`, `congelado_at`, `congelado_por`; `UNIQUE(estudio_id, codebook_version_id)` | inmutable |

Reglas: todo veredicto se guarda ligado a su corrida, en cualquier estado; una corrida que no cumple deja corrida y veredictos y no crea config. `raw_llm_output` se guarda bajo RLS y NUNCA sale por la API (schemas de respuesta explícitos sin ese campo; test) ni por logs (test). Migración `2026110X_0008_estudio_juez.py`, patrón de 0007: `apply_tenant_rls`, triggers de fila `BEFORE UPDATE/DELETE` con `estudio_inmutable` y trigger de SENTENCIA `BEFORE TRUNCATE` por tabla. Registro estructurado (sin contenido) del alta de cada corrida y de cada config.

**`verificar_esquema_juez(session)`** (R3): en Postgres comprueba con `to_regclass` que existen las 3 tablas; si no, 503 `esquema_juez_incompleto`. Los triggers y `alembic_version` se verifican por el runbook post-deploy y por tests de integración. En SQLite es no-op.

### D10. Lista permitida de modelos y presupuesto

`settings.juez_modelos_permitidos` (tupla de strings, env `JUEZ_MODELOS_PERMITIDOS`, vacía por defecto): el modelo del pedido debe estar en la lista (422 `modelo_no_permitido`); vacía -> 503 `sin_modelos_permitidos`. Lista fijada por Juani el 06/11/2026: `google/gemini-2.5-flash-lite`, único modelo (la tabla de precios nativa del gateway no lo lista: el constructor verifica cómo llega `cost_usd`); por cada modelo de la lista se anota por qué ruta sale (OpenRouter o proveedor nativo, según las keys; el contrato en el prompt vale en las dos rutas, D7). Presupuesto: bucket `estudio_juez` del ai-gateway (default 100 USD/mes, freno suficiente); `cost_usd` por veredicto y suma en el resumen.

### D11. Ceguera del prompt y contrato de salida

`armar_mensajes(framing, contenido_md, esquema_salida, enunciado, elementos, referencia)` es pura; su firma no recibe ancla ni etiqueta. Dos pruebas, ambas antes de la sección 4 y sin esperar al recorrido real (B1):
- **Ceguera**: sobre los `messages` capturados, con valores reales de la fixture (UUIDs completos, no literales cortos): ausencia de `episode_id`, `item_id`, claves y valores de `respuesta_esperada` y de `explicacion_md`; presencia de enunciado, `contenido_md`, `n`/`k`.
- **Contrato presente y respuesta parseable**: los `messages` contienen cada clave de dimensión, cada valor permitido, cada régimen y las claves `respuestas`, `valor`, `cita`, `regimen`, `confianza`, `es_frontera`, `notas` del esquema fixture. Esta prueba usa un `complete` falso que NO devuelve un JSON armado por el test: construye su respuesta SOLO leyendo del `messages` recibido el contrato (extrae las claves de dimensión y los valores que encuentra ahí); si el contrato falta, no puede armar nada y el test falla por aserción. Aparte, una respuesta literal del formato esperado (fixture en texto, escrita a mano con las claves del contrato, incluida una con `evidencia_insuficiente` y dimensiones omitidas) atraviesa `validar_forma` y `evaluar_item` y termina `ok`.

Aislamiento del autor del `FRAMING`: el brief del constructor para escribirlo no incluye veredictos de producción, resultados del juez ni etiquetas de los 150; el `FRAMING` se redacta desde el codebook y el formato. El orquestador consulta veredictos de producción en otro ticket; se declara y se registra en tasks.md.

### D12. Qué NO cambia

`regimen_llm.py`, `routes/classify_ep.py`, `services/review.py`, `correccion_nativa.py`, `estudio_esquema.py`, `traza_ciega.py`, `routes/estudio.py`, `apps/web-teacher`, ai-gateway, api-gateway. `routes/estudio_trabajo.py` cambia solo por D3 (sin cambio de comportamiento); `main.py`, `models/__init__.py` y `config.py` del classifier registran router, modelos y la lista permitida.

### D13. Qué le va a pedir T-002 a este diseño (sin construirlo)

- Una **migración propia** que agregue el camino a la muestra (`muestra_item_id`, un `modo` explícito, y `config_id` obligatorio en la corrida de muestra). Este change no deja ese camino latente.
- Comparar al arrancar el `prompt_sha256` (que ya cubre armado de mensajes y `parametros`), `contenido_sha256`, `validador_version`, modelo, `parametros` y `proveedores_respondieron` de la config contra los del código vigente y la ruta efectiva, y negarse si difieren (el mismo nombre de modelo puede ir por OpenRouter o nativo según las keys).
- Un **firewall inverso** propio (la muestra se lee solo con una config congelada) y una **aprobación humana nueva**.
- Un **mecanismo de ejecución a escala**: 150 x repeticiones son ~450 llamadas; el paso a paso de un par por request sirve para 15, no para 450. T-002 decidirá su ejecutor (con el patrón de `evaluation-service` y su reconciliador) y su estimación de costo.
- Decidir cómo se muestra `raw_llm_output` para auditoría sin sacarlo por la API general.
- Esta config no incluye validación de contenido contra humanos: lo que se mide en T-002 es precisamente eso, sin ajuste previo, con la salvedad de los números de ajuste de la config (D8).
- Leer `regimen_propuesto` como canal ausente del juez (D7, decisión 9).

## Consumidores verificados

| Consumidor | Qué usa | Verificación |
|---|---|---|
| `routes/classify_ep.py` | `regimen_llm.clasificar_regimen_llm` | No se toca; `test_regimen_llm.py` y `test_classify_ep_regimen_llm_read.py` verdes sin modificar |
| `services/review.py` | `features['regimen_llm']` | No se toca |
| `correccion_nativa.py` (F15) | solo un comentario menciona `regimen_llm.py` | `test_correccion_nativa.py` verde |
| `routes/estudio_trabajo.py::traza_ciega` | pasa a usar `estudio_traza.py` | `test_estudio_traza_db.py` y `test_estudio_separacion_db.py` verdes sin editar |
| `routes/estudio.py` exportación y `GET /progreso` | `estudio_etiqueta*` | No leen ni escriben tablas del juez (test estático, 5.3) |
| Archivos que hacen `create_all` de `classifier_service.models` sobre SQLite | metadata | Siguen pasando (2.1) |
| Futuro T-002 | `estudio_juez_config` | D13 |

## Risks / Trade-offs

- [Cuenta lectora del CTR bajo identidad de usuario] -> membresía de investigador, ítems solo del estudio, `extra="forbid"`, 403 uniforme; solo 5 episodios ya vistos por los codificadores. Residual: el contenido de esos 5 va al proveedor externo (decisión 2).
- [Firewall] -> D5; superposición imposible por dos escrituras existentes, más guard fresco por par y re-chequeo al congelar; mutantes de orden y de falso positivo.
- [Prompt o modelo ajustados con la coincidencia a la vista] -> `motivo` obligatorio para ambos, hashes en cada corrida, `corridas_previas` y contadores en la config, historial git. El código no lo impide, solo lo hace visible: límite declarado en D8 y en proposal.
- [El contrato de salida no llega al modelo] -> viaja en el prompt en todos los proveedores y entra al hash (D7, D8); lo prueban 3.4 y 3.5 antes del recorrido real.
- [Criterio cumplido repitiendo corridas] -> `corridas_previas` en la config y regla del paper (D8); sin tope por decisión de Juani.
- [Corrida arruinada por una falla transitoria] -> un `llm_caido` o `ctr_no_disponible` ocupa el par y la corrida sigue gastando hasta el final; se declara, y `corridas_previas` guarda las condiciones falladas para separar estas corridas de las que fallan por contenido.
- [N chico] -> 5 anclas x 3 repeticiones prueban formato y estabilidad técnica, NO validez de contenido; el paper no puede decir que el juez fue validado. Se declara en proposal.
- [`res.model` es eco] -> D7, límite declarado.
- [Paso perdido por deploy] -> se repite; no hay zombis; runbook.
- [Gasto duplicado por pasos concurrentes] -> acotado a 15 pares; 409 `par_ya_procesado`.
- [CI no corre integración de classifier] -> ver Migration Plan; DEUDA nombrada. Si queda como DEUDA, las garantías que viven solo en `tests/integration/` (acceso, firewall, inmutabilidad, RLS, persistencia de abortos) NO tienen red ante regresiones futuras: 8.3 y los mutantes prueban solo la revisión entregada. Lo que sí queda en CI: las funciones puras (motor, criterio, resumen, gramática, armado) viven en `tests/unit/`, que CI corre.
- [Token de Clerk de vida corta durante 15 pasos] -> SUPOSICIÓN no verificada; la corrida es reanudable, el cliente puede refrescar el token y seguir.
- [Esquema mal cargado] -> responsabilidad de `cibse-codificacion-ciega`; verificar a mano contra §4 antes de la primera corrida.

## Migration Plan

1. Verificación en la rama (NO en CI): ver tasks 8.3. CI hoy corre `test-unit`, lint y typecheck; no corre `apps/classifier-service/tests/integration/`, ni `make check-rls` sobre `classifier_db`, y `migrations-dry-run` no migra classifier. Por eso el constructor debe correr localmente los tests de integración con `CLASSIFIER_TEST_DB_URL` (el conftest no soporta testcontainers) con **0 skipped** en los archivos del juez, `scripts/check-rls.py` y `python3 scripts/check-claude-md.py`, y registrar salida. Agregar un job de integración de classifier a CI es alcance nuevo: decisión 7 de Juani; por defecto queda como DEUDA con dueño Juani.
2. Deploy solo de classifier-service (un servicio por vez). El `ENTRYPOINT` arranca aunque falle `alembic upgrade`; `verificar_esquema_juez` falla cerrado.
3. Verificación post-deploy (persona con acceso a la base): `alembic current` en `0008`; triggers `estudio_inmutable` y de TRUNCATE en las 3 tablas (consulta a `pg_trigger`); `make check-rls`.
4. Prerrequisitos del investigador: codebook vigente congelado con esquema; exactamente 5 anclas cargadas con enunciados revisados; lista permitida de modelos configurada; key del proveedor resuelta por tenant o env; **verificación humana de `contenido_md` (tarea 8.0, D8)**: `sha256` del texto devuelto por `GET .../codebook/vigente` contra el archivo elegido, registrado en el ADR. Sin eso no se crea la primera corrida.
5. Ejecución: `POST /corridas`, 15 `POST .../siguiente`, lectura del resumen, `POST /configuraciones` si el criterio técnico se cumple (una sola configuración por versión de codebook). Runbook con obtención del Bearer (SUPOSICIÓN: copiado de la sesión del web-teacher; de vida corta).
6. Ambiente del recorrido humano (I10): decisión 6 de Juani.
7. Rollback: revertir código; `alembic downgrade` solo si las tablas están vacías.

## Open Questions

Todas las que cambian alcance, nivel o criterio están en `proposal.md`, "Decisiones pendientes para Juani".
