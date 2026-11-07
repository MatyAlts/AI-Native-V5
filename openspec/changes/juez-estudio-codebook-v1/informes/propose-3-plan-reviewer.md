# Informe: propose-3-plan-reviewer - juez-estudio-codebook-v1

Autor: role-plan-reviewer, subagente nativo de Claude Code, modelo Claude Opus 5.5 (sin tabla "Role executors" en el proyecto). Misma familia que el planner (Claude) y mismo rol y modelo que los informes de los intentos 1 y 2: la independencia es de rol y contexto, no de proveedor.
Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343bac96be4f71ac1da4e2bc2b770365d72f`, artefactos sin commitear leídos el 2026-11-06 entre 21:13 y 21:22 -03. sha256 (16 primeros): proposal `25620d4f819ea767`, design `608565b399577f3b`, tasks `0aab7b815bafe244`, spec acceso `c95decb38cbaa7eb`, spec codificación `a438949ac9ff57b1`, spec congelado `aa3b1bbd0461e9b0`.
Intento: 3 de 3 de la compuerta de plan.

## Veredicto

**VUELVE AL PLANNER** (CORRECCIONES). 1 BLOQUEANTE, 10 IMPORTANTES, 12 MENORES.

No es APTO PARA APROBACIÓN HUMANA todavía. `## Aprobación` sigue vacía, que es lo correcto. Ningún visto bueno de este informe reemplaza la firma de Juani.

Aviso de compuerta: es el tercer intento. El contrato prohíbe un cuarto automático: el orquestador tiene que frenar y ofrecerle a Juani nuevo alcance aprobado, deuda aceptada o parar el change, y sin respuesta escrita en tasks.md nada avanza.

Dato para esa decisión (JUICIO, no decisión mía): el rediseño es bueno. Los tres bloqueantes del intento 2 quedaron resueltos o desaparecieron de verdad. El bloqueante nuevo no pide rediseño: se corrige con unas pocas líneas en D7, D8, D11, la spec de entrada y las tareas 3.1 y 3.4. Los importantes tampoco piden alcance nuevo, salvo I4 e I5, que necesitan una respuesta de Juani.

## EVIDENCIA

Todo el 2026-11-06, sobre HEAD `178c343`. Salvo que se indique, es lectura de código.

Ejecutado:
- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (21:13:33): `"valid": true`, `issues: []`. `openspec status`: 4 artefactos `done`. Alcance: formato, no contenido.
- E2 Script propio (21:20:34; `python3 -I`, importa solo `services/estudio_esquema.py`, lee solo `codebook/esquema_v1.json`, sin datos de episodios ni bases). Salida:
  - A `regimen=reflexiva` con dimensiones omitidas: `PedidoInvalidoError 422 "regimen: con dimensiones incompletas solo se admite un régimen exento"`.
  - B `regimen=None` y dimensiones vacías: no levanta; `faltantes=['regimen','dimension:d1_verbalizacion',...]`.
  - C `evidencia_insuficiente` sin dimensiones, con `notas` y `confianza`: `faltantes=[]`.
  - D ídem sin `confianza`: `faltantes=['confianza']`.
  - E ídem sin `notas`: `faltantes=['notas']`.
  - Claves del esquema: dimensiones `d1_verbalizacion, d2_verificacion, d3_justificacion, d4_autonomia`; `regimenes_exentos: ['evidencia_insuficiente']`; `confianza.valores: alta, media, baja`, obligatoria.
- E3 `rg -c` sobre el texto del codebook (21:21:01; conteos, sin volcar contenido): `d1_verbalizacion|d2_...|d3_...|d4_...` aparece 0 veces en `codebook_v1.md` y en `codebook_v1_para_codificadores.md`. La carpeta tiene los dos archivos, con 11 y 10 encabezados de nivel 1 o 2.
- E4 Cálculo propio (21:19:51). P(15 de 15 `ok`) según p por llamada: 0,99 -> 0,86; 0,98 -> 0,74; 0,95 -> 0,46; 0,90 -> 0,21. Si 2 anclas tienen probabilidad q de dar su régimen modal por repetición, P(ambas estables en 3): q=0,95 -> 0,74; 0,90 -> 0,53; 0,80 -> 0,27. Si una corrida pasa con P=0,2, P(al menos una en 5 corridas)=0,67. Supuestos: independencia; ilustrativo, sin medir ningún modelo.
- E5 Búsqueda de em dashes con `rg -c` sobre proposal, design, tasks y specs: sin resultados. `rg -l "L-[0-9]{3}" docs`: sin resultados. Lecciones L-NNN: ausentes.

Leído:
- E6 `routes/estudio_trabajo.py:232-296` `cargar_muestra`: bajo `investigador_con_estudio_bloqueado`, cuenta anclas con `estudio_id == estudio.id` y `episode_id IN (...)` de TODAS las versiones, 409 `episodio_es_ancla`. `:950-1012` `crear_ancla`: mismo lock, cuenta `EstudioMuestra` con `estudio_id == estudio.id`, 409 `episodio_en_muestra`. `routes/estudio.py:516-563` `crear_version` clona anclas de una versión del mismo estudio bajo el mismo lock, sin episodios nuevos. `AnclaEdicion` no cambia `episode_id` (`estudio_trabajo.py:1016-1040`). Ninguna constraint de base cruza las dos tablas.
- E7 `routes/estudio.py:251-254`: crear un estudio exige rol admin. Unicidad por `(tenant_id, clave)`: un tenant puede tener varios estudios. `EstudioMuestra` es única por `(estudio_id, episode_id)`.
- E8 `routes/estudio.py:634-680` `congelar_version`: exige texto, esquema y anclas válidas; NO exige cantidad mínima de anclas. `:682-710` `fijar_vigente`: bloquea el cambio de vigente solo si hay etiquetas.
- E9 `services/estudio_codebook.py:37-46`: `contenido_sha256 = sha256(json({contenido_md, esquema, anclas}))`. No es el hash del texto.
- E10 `db/__init__.py:47-61`: `tenant_session` fija el tenant con `set_config(..., true)` (alcance de transacción), hace `commit` al salir y `rollback` ante excepción.
- E11 `services/clients.py`: `AIGatewayClient.complete` admite todos los parámetros de D7, `raise_for_status`, un solo `httpx` timeout. `services/ctr_lectura.py:38`: `TIMEOUT_SEGUNDOS = 15.0`. Proxy: 120 s (intento 2, E3). Producción usa `AIGatewayClient` con el default de 60 s (`routes/classify_ep.py:188`).
- E12 `apps/ai-gateway/.../providers/base.py`: `response_format` se reenvía solo en líneas 180-181 (Mistral), 266-267 (OpenAI) y 500-501 (OpenRouter). Gemini (384-389) solo pone `response_mime_type`, el comentario dice que no traduce el esquema. Anthropic (79-145) no lo usa.
- E13 `routes/complete.py:325-350`: un modelo con namespace va a OpenRouter si hay key; si no, se le quita el namespace y va al proveedor nativo (`google/gemini-2.5-flash` -> gemini). `classifier config.py:51`: `eje_fino_model = "google/gemini-2.5-flash"`.
- E14 `services/regimen_llm.py:452-478`: el juez de producción describe la salida en el propio prompt ("SALIDA - devolvé EXCLUSIVAMENTE el JSON con la estructura pedida...") además de mandar el esquema. `:147-210`: el esquema pone todas las claves en `required` y no usa `strict`. `:668-677`: comentario del incidente por contrato de salida que no viajaba. `:622-627`: Gemini 2.5 consume "thinking" del mismo presupuesto de salida.
- E15 `routes/complete.py:396-402`: el único 429 de `/complete` es presupuesto. `:461-495`: error del proveedor tras reintentos da 502. La regla "429 = presupuesto" de D7 es correcta.
- E16 `.venv/.../openai/lib/_pydantic.py:57` (SDK instalado en el checkout principal): su armado de esquema estricto pone `required = [todas las properties]`. Evidencia indirecta de la regla de `strict`; no probé contra el proveedor.
- E17 `infrastructure/postgres/init-dbs.sql:44-54`: `apply_tenant_rls` hace ENABLE, FORCE y CREATE POLICY.
- E18 `tests/integration/conftest.py:25-60`: base por `CLASSIFIER_TEST_DB_URL` o localhost, chequeo de socket y skip. Sin testcontainers. Los archivos de test que citan las tareas 0.2, 0.3 y 5.1 existen. `scripts/check-rls.py` cubre `classifier_db` por `CLASSIFIER_DB_URL`.
- E19 `rg "filtrar_traza|seq_tope|tope" tasks.md`: solo la tarea 1.1, sobre `comprobar_evidencia`. Ninguna tarea ni mutante prueba que `siguiente` filtre la traza.
- E20 `rg "regimen_propuesto"` en proposal, design, tasks y specs: sin resultados. En código es parte del pedido humano (`estudio_esquema.py:266-268`) y se persiste y exporta (`routes/estudio_trabajo.py:659, 722, 1299, 1359`).
- E21 `rg` de residuos: "calibra", "ajuste", "variante", "partición", "sorteo" solo aparecen en negaciones y en el historial, salvo `design.md:105` ("no solo de variantes") y `tasks.md:55` ("Refrescar: congelar dos veces crea dos filas").
- E22 `rg "D2 del motor|D2 motor"`: `design.md:79,88` y `tasks.md:44`. Esa sección no existe en el design v3 (D2 es la vía de acceso). `design.md:177` cita "tasks 8.6", que no existe. La tabla de mutantes tiene 40 filas, no las 37 de `propose-3-planner.md`.
- E23 `proposal.md:87-89`: `## Aprobación` solo con el comentario reservado.
- No ejecutado: tests, `alembic`, `make check-rls`, gateway real. No hay comportamiento runtime probado: el juez no existe.

## Estado de los hallazgos del intento 2

| Hallazgo | Estado verificado | Comprobación |
|---|---|---|
| B-N1 calibración inconstruible | **Desapareció de verdad** | Sin tabla, registro ni sorteo (E21). Las anclas sí entran en `requeridos` y `_item_del_estudio` (intento 2, E4 y E5) |
| B-N2 firewall con foto | **Resuelto dentro del estudio** | Lectura fresca y re-chequeo al congelar. Prescindir del lock es aceptable (E6). Residual entre estudios: I2 |
| B-N3 congelado sin medir | **Resuelto en sus tres puntos**, con dos residuales | Repeticiones fijas, sin rerun silencioso por decisión humana, `sin_contenido` no suma. Residuales: I3 (cantidad de anclas), I5 |
| I1 preflight | Resuelto | D6. Residual en M3 |
| I2 evidencia insuficiente | **Parcial** | C, D, E de E2 funcionan como dice el plan; el orden de la spec choca con A (ver I1) |
| I3 corrida única y UNIQUE | Resuelto | Residuales en I6 y M4 |
| I4 referencia por intento | Resuelto | D7, spec, mutantes C6, C7 |
| I5 registro y `raw_llm_output` | Resuelto | Registro eliminado; schemas explícitos, C4, C5 |
| I6 cita humana | Desapareció | D4, sin preflight de citas humanas |
| I7 modelos, `materia_id`, 429, costo | Resuelto | 429 confirmado (E15). `materia_id=None` es decisión declarada |
| I8 CI | Resuelto como plan honesto | Residual M1 y M2 |
| I9 mutantes | **Parcial** | Ver I9 de este informe |
| I10 Clerk | Pasó a decisión 6, legítimo | Opciones y consecuencia declaradas |
| M1, M2, M3, M5, M6, M7, M8, M9, M10, M11 | Resueltos o desaparecidos | Comprobados contra artefactos |
| M4 contrato LLM | **Parcial** | Sobre fijado; deja el bloqueante B1 |
| R1 a R5 | Tomados | Sin observación |

## Hallazgos

### B1. BLOQUEANTE - El contrato de salida no llega al modelo, y donde llega está mal armado

- Fuente: design D7 ("el esquema se envía igual, la garantía la da el validador local"), D8 (`FRAMING` item b), D11 y tasks 3.4 (`armar_mensajes(framing, contenido_md, enunciado, elementos, referencia)`), tasks 3.1 (dimensión NO requerida), spec codificación "Entrada idéntica"; E3, E12, E13, E14, E16.
- Observación:
  (a) `armar_mensajes` no recibe el esquema, y la spec enumera lo que compone el prompt sin nombrarlo. El `FRAMING` es una constante que solo dice "JSON del esquema". D7 admite que Gemini y Anthropic no aplican `response_format`. En esos proveedores el modelo nunca ve las claves `respuestas`, `valor`, `cita`, ni `d1_verbalizacion`, que además tienen 0 apariciones en el codebook (E3), ni los enums. El validador local solo puede rechazar: las 15 respuestas darían `respuesta_malformada`. Es la ruta que toma `google/gemini-2.5-flash` si no hay key de OpenRouter (E13). El juez de producción no tiene ese problema porque describe la salida en el prompt (E14).
  (b) Donde el esquema sí viaja (OpenAI, OpenRouter), D7 pide `"strict":true` y 3.1 deja las dimensiones fuera de `required`. Según la regla de OpenAI, que el SDK refleja (E16), un esquema estricto lleva todas las claves en `required`. No lo probé contra el proveedor: es SUPOSICIÓN. Producción no usa `strict` (E14). Si el proveedor lo rechaza, llega como 502 y `llm_caido` en todos los pares (E15).
- Por qué no lo atrapan los tests: `complete` es falso en las secciones 3 y 4, y devuelve JSON armado por el test. Se descubriría en el recorrido real de 8.5, después de breaker y auditor.
- Lectura alternativa considerada: el constructor podría escribir las claves a mano dentro del `FRAMING`. Sería una segunda fuente del esquema, sin test contra `esquema_formulario`, y roza "solo instrucciones" y "sin ejemplos". El plan no lo pide.
- Impacto: la condición 4 del criterio (15 de 15 `ok`) queda inalcanzable en parte de los proveedores que la decisión 2 deja abiertos, y no existe congelado. También falla "misma salida": el humano ve el formulario con sus opciones; el modelo no.
- Criterio incumplido: viabilidad de dependencias; "misma entrada, misma salida"; criterio capaz de cumplirse.
- Corrección verificable: (1) el esquema de salida, derivado de `construir_json_schema(esquema)`, entra en los mensajes (parámetro de `armar_mensajes`) y en la spec de entrada. (2) Test en 3.4 con el `esquema` de la fixture: las claves de dimensión, valores y regímenes aparecen en `messages`, y el mutante correspondiente lo mata. (3) Resolver `strict`: quitarlo como hace producción, o `required` con todas las claves y valor nulo, separando el esquema enviado del criterio local para no perder "omitida -> `incompleto`". (4) Agregar a la decisión 2 la ruta del proveedor (E13). Esto no toca la ceguera: el esquema no trae datos de ítems.

### I1. IMPORTANTE - El orden de evaluación de la spec contradice su propio escenario, y el flujo citado no existe

- Fuente: spec codificación "Régimen y completitud" ("en este orden... coherencia... completitud") y "Dimensión faltante con régimen no exento"; tasks 3.3 (`inconsistente` = 422 de `evaluar_pedido`); `design.md:79,88`, `tasks.md:44`; E2, E22.
- Observación: en el orden declarado, una dimensión omitida con régimen no exento llega a `evaluar_pedido`, que da 422 (E2 caso A), y 3.3 mapea ese 422 a `inconsistente`. El escenario exige `incompleto` y "no `inconsistente`". La sección "D2 del motor", que debía fijar el flujo, se perdió en la reescritura.
- Impacto: el constructor elige un orden sin autoridad; arriesga duplicar la regla que la spec prohíbe duplicar. No imposibilita: E2 caso B muestra una salida sin segunda implementación.
- Corrección verificable: agregar a design el flujo numerado. Por ejemplo, evaluar primero con `regimen=None` y `faltantes_cierre` para detectar `dimension:*`, y recién después con el régimen afirmado. Test con el esquema real como fixture. Los escenarios de evidencia insuficiente deben incluir `confianza`, que es obligatoria (E2 casos C y D).

### I2. IMPORTANTE - La superposición es imposible dentro de un estudio, no entre estudios

- Fuente: design D5 ("La superposición es imposible"), spec acceso "La muestra de 150 no se procesa", proposal ("Nunca lee contenido de los 150"); E6, E7.
- Observación: verifiqué las escrituras. Dentro de un estudio la afirmación es cierta: dos chequeos bajo el mismo lock, y el clonado no introduce episodios. Pero ambos filtran por `estudio_id`, y `ancla_en_muestra(session, estudio_id, ...)` también. Un segundo estudio del mismo tenant puede tener como ancla un episodio de la muestra de `cibse-2027`, y el guard pasa. Requiere un admin que cree el estudio y un investigador en él, así que es poco probable y no silencioso.
- Impacto: el contenido de un episodio de los 150 llega al proveedor, y lo que el plan llama "imposible" no lo es. El test F3 tampoco lo cubre.
- Corrección verificable: consultar `estudio_muestra` por `episode_id` a nivel tenant, sin filtro de estudio (RLS ya acota el tenant), o acotar el juez a la clave del estudio por configuración. Test: muestra de otro estudio del mismo tenant aborta. Corregir la redacción de D5.

### I3. IMPORTANTE - El criterio se cumple con una sola ancla

- Fuente: design D6 ("al menos un ancla"), D8 condición 3 (`n_items * REPETICIONES_V1`, con `n_items` tomado de la propia corrida), proposal ("5 anclas x 3"); E8.
- Observación: nada exige 5. `congelar_version` no tiene mínimo, así que 3 llamadas sobre un ancla cumplen todas las condiciones. Este es el caso de "cumplir sin medir" que quedaba: repeticiones, caché y `sin_contenido` están bien cerrados.
- Corrección verificable: constante `N_ANCLAS_V1`, comparada en `POST /corridas` y en la condición 3, más fila de mutantes. Test: 4 anclas no congelan.

### I4. IMPORTANTE - "Sin ajuste por resultados": el límite no está donde firma Juani, y el rastro tiene dos agujeros

- Fuente: proposal "Decisión humana" y "Consecuencia para el método del paper"; design D8 ("Límite honesto"), D9 (`corrida_id` UNIQUE); spec congelado "Volver a congelar"; tasks 4.5; E21.
- Observación:
  (a) El límite está en D8 y Risks, no en proposal. Proposal dice "no se ajusta" y le hace decir al paper "prompt fijado a priori", mientras cada corrida muestra la coincidencia antes de congelar y el prompt se puede cambiar después con un `motivo` de texto libre.
  (b) `motivo` y `n_prompts_previos` cubren el prompt, no el modelo. Con dos modelos en la lista se puede elegir por coincidencia sin motivo y sin que la config lo cuente. Las filas de corrida sí lo registran.
  (c) Nada distingue un cambio técnico de uno de contenido, aunque hay un dato objetivo: si la corrida anterior cumplió todas las condiciones técnicas, no había falla técnica que corregir.
  (d) "Una vez congelada... no se ajusta" contra "Volver a congelar": se admite una segunda config con otro prompt, sin definir cuál rige. D13 no lo dice y T-002 va a tener que elegir. La frase "Refrescar: congelar dos veces crea dos filas" es residuo de la calibración y, con la misma corrida, choca con `UNIQUE(corrida_id)` (error sin mapear).
- Impacto: Juani firmaría una garantía más fuerte que la que existe. No es imposible de construir ni silencioso: por eso no lo marco bloqueante.
- Corrección verificable: (1) copiar el límite a proposal y al ADR, con la regla para el paper: si `n_prompts_previos > 0` o hubo más de un modelo, se declara. (2) La config guarda `n_modelos_previos`, y cuántos cambios de prompt siguieron a una corrida sin falla técnica. (3) Definir qué config rige. Decisión para Juani: una sola por versión de codebook (409) o reemplazo con motivo. (4) Congelar dos veces la misma corrida responde 409 con test.

### I5. IMPORTANTE - La decisión 3 no tiene la información para tomarse, y falta qué se hace si falla la estabilidad

- Fuente: proposal decisión 3; design D7, D8 ("Reruns"); `propose-1-plan-reviewer.md` E13; E4.
- Respuesta a lo pedido: `ESTABILIDAD_MIN_V1 = 1.0` es coherente como exigencia, porque con 5 anclas cualquier valor menor deja pasar una inestable, pero es frágil, y el plan no lo dice donde Juani decide:
  (a) Dos de las cinco anclas son `es_frontera` (intento 1, sin reverificar): son donde más se espera variación.
  (b) La `referencia` cambia en cada repetición, así que no son entradas idénticas: se mide sensibilidad al nonce más no determinismo. Es aceptable, pero hay que decirlo.
  (c) La condición 4 exige además 15 de 15 `ok`, con cualquier `cita_invalida`, `incompleto` o `llm_caido`, incluida una caída transitoria (E4: con p=0,95, 46%).
  (d) Sin tope de corridas, la barrera se pasa repitiendo (E4). Es la decisión de Juani de dejar rastro, y no la discuto, pero el criterio informa "pasó una vez", no "es estable".
  (e) Si un ancla de frontera oscila, las únicas salidas son repetir hasta que pase o tocar el prompt, y lo segundo es un ajuste de contenido, lo que la opción B prohíbe. Hoy eso solo está en el JUICIO del planner.
- `sin_contenido`: se trata bien. Falla la condición 4 y el aviso está en la decisión 3. Es improbable: cada cita consensuada apunta a mensajes o ejecuciones, y ninguna ancla es de evidencia insuficiente (intento 1, E13, sin reverificar). Costo máximo: una corrida.
- Corrección verificable: agregar a la decisión 3 los puntos (a) a (d) y una regla para (e): qué hacer ante inestabilidad sin tocar el prompt. La config debe mostrar cuántas corridas previas de la misma variante no cumplieron. El valor lo decide Juani.

### I6. IMPORTANTE - `siguiente` no define sus transacciones, y con `tenant_session` el aborto se pierde

- Fuente: design D6 ("si difiere: aborta y 409"; "inserta el veredicto en su transacción"), spec acceso "Versión de traza distinta", spec codificación "Persistencia"; E10, E11.
- Respuesta a lo pedido:
  - Reanudación: correcta, sale de los veredictos persistidos.
  - Dos llamadas al mismo paso: `UNIQUE` resuelve; la segunda gasta una llamada y da 409. Costo acotado, razonable.
  - Tiempo: peor caso 15 (CTR) + 40 + 40 = 95 s, contra 120 s. Entra. D6 dice 80 s y omite el CTR; el resultado no cambia.
- Observación: `tenant_session` hace rollback ante excepción (E10). Levantar el 409 dentro del bloque deshace el aborto. Además el tenant dura lo que la transacción, así que "su propia transacción" exige otro bloque, y mantener una sesión abierta durante la llamada al LLM deja hasta 80 s una transacción colgada y expone el veredicto a un fallo del cierre. `traza_ciega` ya muestra el patrón: sesión, lectura afuera (`estudio_trabajo.py:162-175`).
- Corrección verificable: declarar en D6 las fases: sesión 1 (carga, guard, abortos con commit), sin sesión (CTR y LLM), sesión 2 (veredicto), sesión 3 (cierre). Fijar el HTTP de cada aborto, hoy solo definido para `traza_version`. Test: tras un aborto con 409 la corrida figura `abortada` leída con otra sesión; fallo del cierre no pierde el veredicto.

### I7. IMPORTANTE - `prompt_sha256` no cubre todo lo que define la entrada

- Fuente: design D8 (`prompt_sha256` de `{framing, json_schema}`, golden de `sha256(FRAMING)`), D13, condición 2.
- Observación: el armado de `armar_mensajes` (cómo se serializan elementos y enunciado, orden, plantilla) queda afuera del hash y del golden. La condición 2 tampoco compara `parametros`. Cambiar la serialización de la traza o `max_tokens` deja el hash igual, y la comparación que D13 le pide a T-002 pasa. Es la trampa que CLAUDE.md describe para `test_pipeline_reproducibility.py`: determinismo no es invariancia.
- Corrección verificable: incluir una `ARMADO_VERSION` y `parametros` en el hash, o un golden del `messages` completo sobre una fixture; comparar `parametros` en la condición 2. Mutante: cambiar el orden del armado rompe el golden.

### I8. IMPORTANTE - La verificación de `contenido_md` no se puede hacer como está escrita

- Fuente: design D8 ("comparar `contenido_sha256` contra el archivo"), proposal ("secciones 1 a 9"); E3, E9.
- Observación: `contenido_sha256` cubre texto, esquema y anclas: nunca va a coincidir con el hash de un archivo. Tampoco es una duda teórica: hay dos textos candidatos (E3). No hay tarea ni prerrequisito en Migration Plan paso 4. Es la entrada central de la opción B, y `explicacion_md` podría estar adentro. El aviso de 3.4 corre sobre fixtures, no sobre el dato real.
- Corrección verificable: en Migration Plan 4 y en una tarea: comparar `sha256(contenido_md)`, leído por `GET .../codebook/vigente`, contra el archivo elegido, y registrar cuál es. Lo ejecuta una persona antes de la primera corrida.

### I9. IMPORTANTE - Tabla de mutantes: mejor, pero con huecos en aserciones de datos

- Fuente: tabla CRITICAL del workflow; tasks 2.3, 4.3, 5.1, 5.2, 8.1; E17, E19; memoria `aserciones-que-pasan-sin-medir.md`.
- Observación: F1 a F5 son reales, incluido el de orden. Faltan o fallan:
  (a) **Filtro de traza:** spec acceso exige el mismo filtro, y ninguna tarea ni mutante prueba que `siguiente` use `filtrar_traza` con `seq_tope`. Un mutante que pase eventos posteriores al tope o sin lista blanca sobrevive, porque `armar_mensajes` se prueba con elementos ya dados. Es la frontera de datos más directa del change.
  (b) **P12 vacuo:** con FORCE (E17), quitar la policy deja default-deny en Postgres. "Otro tenant no ve filas" sigue verde, y el insert del test falla por setup, que no cuenta. Se necesita afirmar que el tenant propio sí ve sus filas, y mutar con `NO FORCE` o una policy permisiva.
  (c) `episode_id` en respuestas (5.2) no tiene mutante: C4 mira solo `raw_llm_output`.
  (d) `comprobar_evidencia` omitida en `siguiente`, `enunciado_pendiente` y `sin_contenido` llamando al modelo: sin mutante. P15 solo cubre la unidad.
  (e) A1 y A2 no dicen en qué ruta. 5.1 debe parametrizar las 6 rutas, con guarda de lista no vacía, y el mutante aplicarse por ruta.
  (f) Condiciones 1, 2 (modelo en lista, `validador_version`) sin fila propia.
- CI: lo no cubierto por CI es acceso, firewall, inmutabilidad y RLS. Decisión 7 es legítima y tiene la información necesaria. Si queda DEUDA, las garantías CRITICAL no tienen red ante regresiones: 8.3 y los mutantes prueban solo la revisión entregada, y el plan debe decirlo así. Sin alcance nuevo: las funciones puras de 4.4 y 4.5 pueden vivir en `tests/unit/`, que sí corre en CI.
- Corrección verificable: agregar filas para (a), (c), (d), (e), (f), con test de integración que capture `messages` con un evento posterior al tope; rehacer P12.

### I10. IMPORTANTE - "Misma salida": el juez no tiene `regimen_propuesto`, y nadie lo decidió

- Fuente: objetivo del change; design D7; tasks 3.1; E20.
- Observación: el humano puede discrepar de la regla con `regimen_propuesto`, que se persiste y se exporta. El plan no lo menciona. Con `additionalProperties:false`, un juez que quiera discrepar no tiene canal: da `inconsistente` o `respuesta_malformada`, y eso cuenta contra la condición 4.
- Corrección verificable: declarar la exclusión con su porqué en D7 y en el ADR, o incluir el campo nulo en el contrato, con test. La decisión afecta la comparación de T-002 y no es del revisor.

### Menores

- **M1** `design.md:177` cita tasks 8.6 (es 8.3). `design.md:78` cita D9 para la lista de modelos (es D10). D8 llama "decisión 3 de Juani" a una frase de la opción B, y la decisión 3 de proposal es otra. Proposal cita "Lo que T-002 le pide" y el título de D13 es otro.
- **M2** Tasks 0.3 y Migration Plan 1 ofrecen "testcontainers", y el conftest no lo soporta (E18).
- **M3** Spec acceso "Versión de traza distinta" dice "la corrida queda `abortada`", cierto en `siguiente` pero no en `POST /corridas`, donde no hay fila (D6). Separar.
- **M4** Doble cierre: dos `siguiente` tras una caída entre veredicto y cierre. El trigger rechazaría el segundo. Exigir `UPDATE ... WHERE estado='en_curso'`, sin error si afecta 0 filas.
- **M5** La spec "Traza sin contenido" no lista copia ni pegado en el requisito, y su escenario "Solo copias o pegados" dice lo contrario. Agregar esos tipos al requisito.
- **M6** `siguiente` no compara `prompt_sha256` del código con el de la corrida: reanudar tras un deploy mezcla prompts. El criterio mira el hash de la corrida, no el de cada veredicto. Agregar 409 o una condición por veredicto.
- **M7** `siguiente` debe tomar las anclas de `corrida.codebook_version_id`, no de la vigente, que puede cambiar si aún no hay etiquetas (E8).
- **M8** "`FRAMING` sin ejemplos" no dice qué afirma el test. Definirlo, por ejemplo: no contiene valores ni nombres de régimen del esquema. Cuidar la subcadena corta (memoria citada).
- **M9** El timeout de 40 s es menor que los 60 s de producción, con hasta 6000 tokens y "thinking" (E11, E14), sin medir. Fallo visible (`llm_caido`), no silencioso. El costo de un intento cortado no entra en `cost_usd`; `referencia` guarda solo el último intento: declararlo.
- **M10** Un `llm_caido` o `ctr_no_disponible` transitorio ocupa el par y arruina la corrida, que sigue gastando hasta el final. Declararlo, o cortar temprano, y separar esas corridas en `n_corridas_previas`.
- **M11** `proveedor` no se fija: el mismo nombre de modelo puede ir por OpenRouter o nativo según las keys (E13). La config guarda `proveedores_respondieron`, pero D13 no lo compara.
- **M12** Residuo de redacción en `design.md:105` ("no solo de variantes"). `propose-3-planner.md` dice 37 filas y son 40 (E22). `motivo` solo con espacios debería dar 422.

## Respuesta al punto 3: defecto del plan o decisión humana

Decisión legítima, no defecto: 1 (vía y nivel), 4 (extracción), 5 (T-002), 6 (ambiente de Clerk), 7 (CI), 8 (operación sin UI). Tienen información suficiente.
Decisión legítima con información faltante, y por eso hay defecto: 2 (falta la ruta y el contrato por proveedor, B1) y 3 (I5).
Decisiones nuevas que este informe abre para Juani: qué config rige tras un re-congelado (I4), y si el juez puede proponer régimen (I10).
Clasificación: CRITICAL sigue justificada. Cuenta lectora más proveedor externo, aun con 5 episodios. HIGH es decisión de Juani. Mostrar la coincidencia y no topar corridas son decisiones de Juani que respeto: lo que pido es que el rastro y el texto que firma las reflejen.

## JUICIO

- (role-plan-reviewer, plan contra código, confianza alta) Lo central de la opción B quedó bien: alcance chico, sin calibración real residual, paso a paso más simple y más testeable que el fondo, firewall correcto dentro del estudio.
- (role-plan-reviewer, confianza alta en el hecho, media-alta en la severidad) B1 (a) sale de lectura directa y E3. Lo marco bloqueante porque el criterio queda inalcanzable en proveedores que el plan deja abiertos y ningún test previsto lo ve. Si el modelo elegido pasara por un proveedor que aplica el esquema y `strict` se corrigiera, el daño se reduciría; pero hoy esa elección no está hecha, y el plan no la condiciona.
- (role-plan-reviewer, confianza media) I4 (d) estuvo cerca de bloqueante: no lo es porque el límite está declarado en design y nada queda silencioso.
- (role-plan-reviewer, confianza media) I2 es poco probable, pero la corrección es barata y el change es CRITICAL.
- (role-plan-reviewer, confianza media) Con E4 ilustrativo: el criterio técnico sirve para detectar un contrato roto; no certifica estabilidad.

## SUPOSICIÓN

- No probé `strict` contra ningún proveedor: la regla sale de conocimiento general y de E16.
- No sé qué keys hay en producción, así que no sé por qué ruta iría un modelo (E13).
- No consulté ninguna base: no sé cuántas anclas hay cargadas, ni qué texto tiene `contenido_md`, ni si hay etiquetas o más de un estudio.
- Que Postgres aplique default-deny con FORCE y sin policy sale de su documentación, no de una prueba propia.
- `es_frontera` de dos anclas y la distribución de regímenes vienen de `propose-1-plan-reviewer.md` E13, sin reverificar.
- Latencias sin medir (I6, M9). E4 asume independencia.
- Todo lo dicho sobre el juez futuro es análisis de plan, no comportamiento observado.

## Fuentes leídas

Completos: `proposal.md`, `design.md`, `tasks.md`, los tres `specs/*/spec.md`, `informes/propose-2-plan-reviewer.md`, `informes/propose-3-planner.md`, `informes/LEEME.md`. De `propose-1-plan-reviewer.md`, solo E13 y E14 (rg).
Código en la revisión indicada: `routes/estudio_trabajo.py` (125-300, 925-1035, rg), `routes/estudio.py` (245-275, 515-710, rg), `models/estudio.py` (40-106 y modelos de muestra, codebook y ancla), `db/__init__.py` (28-70), `services/clients.py`, `services/ctr_lectura.py` (1-110), `services/estudio_esquema.py` (320-515), `services/estudio_codebook.py` (19-46), `services/regimen_llm.py` (144-152, 620-700, rg), `config.py` (rg), `routes/classify_ep.py` (rg); `apps/ai-gateway/.../routes/complete.py` (60-130, 325-350, 388-505, rg), `providers/base.py` (79-112, 368-396, 480-505, rg); `alembic/versions/20261104_0007` (rg), `20260902_0002` (rg), `infrastructure/postgres/init-dbs.sql` (44-72), `scripts/check-rls.py` (1-60, rg), `tests/integration/conftest.py` (25-95), `test_estudio_separacion_db.py` (1-90), listados de `tests/`. CLAUDE.md global, de proyecto y de repo; memoria `aserciones-que-pasan-sin-medir.md`.
Datos: `codebook/esquema_v1.json` (cargado para E2), `codebook_v1.md` y `codebook_v1_para_codificadores.md` solo por conteos con `rg -c` (E3), y `anclas/propuesta_anclas_v1.md` también solo por conteo, que entró en el bucle de E3 sin que yo volcara su contenido.
**Firewall:** no abrí contenido, trazas, etiquetas humanas ni veredictos de producción de los 150. No abrí `analisis_produccion/` ni `muestra_150.csv`. No toqué bases.
Lecciones L-NNN: ausentes (ruta buscada `docs/`, E5).

## Contaminación por otros informes

Leí por encargo `propose-2-plan-reviewer.md` y `propose-3-planner.md`. Usé la disposición del planner como lista de afirmaciones a comprobar y reverifiqué lo central contra código. Hechos de código que reuso del intento 2 sin reverificar: proxy de 120 s, caché del gateway, `res.model` como eco, CI (E14 de ese informe). De E13 del intento 1 dependo sin reverificar. Soy el mismo rol y modelo que los dos informes previos: no es una segunda opinión independiente. No consulté Engram ni informes de otros changes.

## Chequeos no ejecutados

- Suites y baseline, `alembic`, `make check-rls`, `make test-rls`: requieren entorno o base, fuera del encargo.
- Prueba contra ai-gateway o proveedor real: fuera de alcance.
- Lectura de `anclas_v1.json` y de la base: no necesarias para los hallazgos, y el encargo no las pedía.
