# Informe: propose-1-plan-reviewer - juez-estudio-codebook-v1

Autor: role-plan-reviewer (subagente nativo de Claude Code, modelo Claude Opus 5.5; ejecutor declarado por el orquestador, sin tabla "Role executors" en el proyecto). Misma familia de modelo que el planner (Claude): la independencia es de rol y de contexto, no de proveedor.
Revisión: worktree `agent-a377c2107a7f2b43a`, HEAD `178c343bac96be4f71ac1da4e2bc2b770365d72f`; artefactos del change sin commitear (carpeta `openspec/changes/juez-estudio-codebook-v1/` untracked, leída el 2026-11-06 ~14:05-14:10 -03).
Intento: 1.

## Veredicto

**VUELVE AL PLANNER** (CORRECCIONES). 4 BLOQUEANTES, 8 IMPORTANTES, 6 MENORES.
La sección `## Aprobación` de proposal.md está vacía (solo el comentario reservado): correcto, no es hallazgo. Este informe no reemplaza la aprobación humana fechada que exige HIGH.

## EVIDENCIA

Todas las corridas el 2026-11-06, sobre HEAD `178c343`.

- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (14:08:44): `"valid": true`, 0 issues. `openspec status --change juez-estudio-codebook-v1 --json`: los 4 artefactos presentes. Alcance: valida formato, no contenido.
- E2 `services/estudio_esquema.py` (lectura, líneas 272-509): existen `PedidoInvalidoError(status, errores)`, `Evaluacion`, `derivar_regimen(esquema, respuestas)`, `evaluar_pedido(esquema, pedido)`, `faltantes_cierre(esquema, ev)`, además de `errores_respuesta_esperada` y `motivos_ancla_para_congelar`. Hechos relevantes: `evaluar_pedido` está pensado para guardados PARCIALES: con `regimen=None` devuelve `regimen = regimen_regla`, que puede ser `None` (línea 422-423) sin error; la exigencia de cita (`cita_requerida_si`) y de notas/confianza vive SOLO en `faltantes_cierre` (líneas 497-508), no en `evaluar_pedido`. Claves de pedido admitidas: `respuestas, regimen, regimen_propuesto, es_frontera, confianza, notas` (línea 266).
- E3 `services/traza_ciega.py`: `filtrar_traza(events, seq_tope)` existe con esa firma. Tipos con `k`: `lectura, mensaje_alumno, codigo, ejecucion, prueba, nota`; `respuesta_tutor` hereda el turno; `inicio, copia, pegado, fin_*` sin `k`; todo elemento tiene `n` global. `episodio_abierto` está en `TIPOS_INCLUIDOS` (tipo `inicio`).
- E4 `services/clients.py::AIGatewayClient.complete(messages, model, feature, tenant_id, materia_id=None, temperature=0.7, max_tokens=2048, response_format=None) -> CompleteResult(content, model, provider, feature, input_tokens, output_tokens, cost_usd, cache_hit)`. Temperatura 0 y modelo explícito son pasables. `CompleteFn` (Protocol) está en `services/regimen_llm.py:598`, no en `clients.py` como dice proposal.md "Impact".
- E5 `apps/ai-gateway/src/ai_gateway/routes/complete.py` (líneas 405-494): (a) caché por request (`cache.get/set`), devuelve `cache_hit=True` y el `model` cacheado; (b) `_resolve_provider_and_model`: sin key openrouter strippea el namespace y cae a provider nativo; sin ninguna key, `get_provider()` (mock en dev, `LLM_PROVIDER=mock`); (c) ante error del primario reintenta y luego **cambia a `settings.llm_fallback_model`** si está configurado. Conclusión verificada por lectura: pasar `model=` NO garantiza que responda ese modelo.
- E6 `services/regimen_llm.py:644-653`: el juez de producción persiste `model_used=model` (el pedido), no `res.model`. El plan dice copiar "el mismo principio" (D10).
- E7 `routes/estudio_trabajo.py:155-191` (`traza_ciega`): antes de `filtrar_traza` hace `require_membresia`, `_item_del_estudio`, chequeo `traza_version` (409), `_enunciado_del_item` (409 `enunciado_pendiente`), `EpisodioInexistenteError -> events=[]`, y chequeo de evidencia fija `seq_tope/chain_hash_tope` (409 `evidencia_alterada`). `_item_del_estudio`, `_enunciados_revisados`, `_enunciado_del_item`, `vigente_congelada`, `esquema_vigente` son funciones del módulo de RUTAS (varias privadas), no de servicios.
- E8 `services/ctr_lectura.py`: `CTRLector.episodio(tenant_id, episode_id)` por HTTP al ctr-service con la cuenta `ESTUDIO_LECTOR_SERVICE_USER_ID` y firma con `gateway_shared_secret`. Un script fuera del servicio necesita ese secreto y la URL interna del CTR.
- E9 `models/estudio.py`: `EstudioAncla` tiene `uso` (`ejemplo`/`practica`), `episode_id`, `seq_tope`, `chain_hash_tope`, `respuesta_esperada` (JSONB), `TenantMixin` (`tenant_id`). `CodebookVersion` tiene `estado`, `contenido_sha256`.
- E10 Migración `alembic/versions/20261104_0007_estudio_codificacion.py`: `SELECT apply_tenant_rls('<tabla>')` por tabla (línea 344), triggers `BEFORE UPDATE/DELETE` con `RAISE EXCEPTION 'estudio_inmutable: ...'` y trigger aparte `BEFORE TRUNCATE` (líneas 512-517). Patrón factible para 0008.
- E11 `apps/classifier-service/Dockerfile`: `ENTRYPOINT ... python -m alembic upgrade head || echo 'WARN: alembic failed, continuing'; exec uvicorn ...`. Una migración que falla NO frena el deploy.
- E12 Chequeo de firewall por ID (14:0x, `python3` leyendo SOLO la columna `episode_id` de `muestra_150.csv` y el JSON de anclas): `muestra ids: 150`, `n anclas: 5`, `anclas en muestra: 0`. No se leyó ninguna otra columna ni contenido de episodios. Alcance: el JSON en disco, no las anclas cargadas en la base.
- E13 `anclas_v1.json` (campos `resp.respuestas`): las citas consensuadas por los humanos son `"mensaje 1"`, `"mensaje 4 y ejecución 1"`, `"ejecuciones 2 y 3"`, `"ejecuciones 7 a 9"`, `"mensajes 1, 3 y 5"`. Dos de las cinco anclas tienen `es_frontera: true` (las dos superficiales, confianza `media`); ninguna es de evidencia insuficiente. Distribución: 2 reflexiva, 2 superficial, 1 pasiva.
- E14 Codebook v1 (rg): línea 30 "Cada marca necesita al menos una cita: el número de turno del chat o el evento (por ejemplo, "ejecución 4")"; línea 149 cita de ejemplo "ejecuciones 3 y 4 y la edición entre ellas"; línea 89 "intentos de copiar" como marcador de pasiva (el elemento `copia` no tiene `k`).
- E15 `correccion_nativa.py`: los hits de `regimen_llm`/`classifier` son comentarios/docstrings (líneas 29, 362, 379), sin import. Confirma la afirmación del plan.
- E16 `tests/integration/test_estudio_separacion_db.py`: es un test de FLUJO (corre el estudio y verifica que las tablas del piloto no se tocan); no es un chequeo estático de quién lee qué tabla.
- E17 `uv run pytest <suites de regimen_llm, classify_ep_regimen_llm_read, correccion_nativa> -q` (14:09:58): NO EJECUTADO: `error: Failed to spawn: pytest` (el entorno del worktree no tiene pytest). No hay baseline de regresión de este revisor. `git status --short` posterior: sin cambios en archivos versionados.
- E18 Lecciones L-NNN: `rg "L-0[0-9]{2}"` sobre `docs/` y `openspec/` del worktree: sin resultados. Ausencia confirmada con comando propio (el planner la había adoptado sin reverificar).

## Hallazgos

### B1. BLOQUEANTE - La gramática de citas del plan contradice las citas reales del codebook y de las anclas

- Fuente: design.md D4 (regex `turno \d+`, `código \d+`, `ejecución \d+`, ... ; "si ningún token reconocido aparece ... la cita es inválida"); spec codificación "Cita con localizador válido"; E13, E14, E3.
- Observación: las cinco anclas consensuadas citan con `mensaje k`, plurales (`ejecuciones 2 y 3`), rangos (`7 a 9`) y listas (`mensajes 1, 3 y 5`). Ninguna de esas formas entra en la gramática de D4 salvo "ejecución 1" de una sola ancla. El codebook pide "turno del chat o el evento" y su propio ejemplo cita "ejecuciones 3 y 4 y la edición". Además la regla no define qué pasa con citas multi-token (una válida y otra inexistente), con elementos sin `k` (`copia`, `pegado`, `fin`, que el codebook usa como marcador de pasiva) ni si se acepta el localizador global `n`.
- Impacto: un juez que cite como citan los humanos termina en `cita_invalida` en todas las anclas y el criterio de congelado es inalcanzable; o se fuerza al LLM a un formato de cita distinto del humano, lo que rompe "codificador más con el mismo formulario". La validación sería asimétrica (los humanos no la tienen).
- Criterio incumplido: restricción 3 (citas validadas contra localizadores reales) aplicada de forma que sea satisfacible y coherente con el codebook; spec "Entrada idéntica / mismo formulario".
- Corrección verificable: definir una gramática cerrada derivada de los localizadores que efectivamente muestra la UI del estudio (incluyendo `mensaje`/`turno`, singular/plural, listas, rangos, y decidir `n`, `copia`, `pegado`), con política explícita para multi-token (todos deben existir, por ejemplo) y para citas a elementos sin `k`. Agregar a 2.2 un test parametrizado con las cinco citas literales de `anclas_v1.json` contra trazas fixture donde existen (deben validar) y variantes con un número inexistente (deben fallar). Si el formato de cita se le impone al LLM en el framing, declararlo como diferencia con el codificador humano en design.md.

### B2. BLOQUEANTE - "Modelo pinneado" no está garantizado por el ai-gateway y el plan registra el modelo pedido, no el que respondió

- Fuente: design.md D10, spec codificación "Reproducibilidad registrada por veredicto", tasks 2.5; E4, E5, E6.
- Observación: el ai-gateway puede responder con `llm_fallback_model`, con el modelo strippeado de namespace, con el provider mock si no hay key, o desde caché. D10 dice "modelo pasado explícito" y copia el principio de `regimen_llm.py`, que persiste el modelo pedido.
- Impacto: una configuración puede congelarse como "modelo X" habiendo respondido el fallback o el mock, y T-002 heredaría esa mentira. Es exactamente el tipo de error silencioso que invalida el acuerdo humano-juez del paper.
- Criterio incumplido: restricción 2 (modelo pinneado registrado por resultado).
- Corrección verificable: el veredicto persiste `CompleteResult.model`, `provider` y `cache_hit` tal como vuelven; si `model` devuelto difiere del pinneado o `provider == "mock"`, el veredicto queda en un estado propio (por ejemplo `modelo_no_pinneado`) que cuenta como no-ok para el criterio. Test RED/GREEN con un `complete` falso que devuelve otro `model`. Declarar en design la política de caché (registrar `cache_hit`; decidir si la calibración debe evitarla). No requiere tocar ai-gateway.

### B3. BLOQUEANTE - Vía de acceso del script a datos de alumnos indefinida y contradictoria; pone en duda la premisa de la clasificación HIGH

- Fuente: proposal.md "Impact" ("usando la sesión de investigador existente (misma autenticación que ya usan los endpoints)"), design.md D8 paso 1 ("vía `GET /{clave}/codebook/{etiqueta}/anclas` con la membresía investigador"), tasks 4.1 ("funciones de servicio existentes ... sin HTTP"), proposal "Clasificación" ("no agrega una superficie de acceso nueva, reusa la existente"); CLAUDE.md del repo, invariantes de ADR-063; E7, E8.
- Observación: un script batch no tiene `User` firmado por el gateway, así que no puede pasar por `require_membresia`. Si va directo a la base y al `CTRLector`, (a) lee tablas `estudio_*` fuera de `routes/estudio.py`/`estudio_trabajo.py`, contra el invariante "solo las leen endpoints del estudio"; (b) usa la cuenta de servicio del CTR sin un "caller" cuyo estudio acote los `episode_id`; (c) necesita `gateway_shared_secret`, credenciales de `classifier_db` y red interna, en un proceso nuevo. Eso ES una superficie de acceso nueva, aunque reuse piezas.
- Impacto: el límite de datos sensibles queda sin dueño; la justificación de HIGH (no CRITICAL) se apoya en una premisa que el propio plan no cumple. La pregunta abierta 3 tiene un default declarado que no es implementable.
- Criterio incumplido: restricción 6 (tablas `estudio_*` solo por endpoints del estudio; lector del CTR solo con IDs resueltos desde el estudio del caller); regla de clasificación (sensitive-data boundary).
- Corrección verificable: el planner define una sola vía (por ejemplo: el script recibe `--clave` y un `--investigador-user-id`, resuelve la membresía investigador activa de ese estudio en la base y falla si no existe; los `episode_id` salen solo de `EstudioAncla` de la vigente congelada de ESE estudio; dónde corre y de dónde salen secreto y credenciales, sin exponerlos), agrega el test correspondiente (sin membresía -> aborta antes de leer CTR; con un `episode_id` que no viene de anclas -> imposible por firma), y propone la enmienda al invariante de CLAUDE.md (no solo un APPEND sobre las tablas nuevas). Reabrir la clasificación con esa vía explícita para que el humano decida HIGH o CRITICAL; el revisor no la cambia.

### B4. BLOQUEANTE - Contradicción sobre qué veredictos se persisten; las corridas de calibración fallidas no dejan rastro

- Fuente: spec codificación "Persistencia de un veredicto" ("WHEN se produce cualquier veredicto, en cualquier estado THEN se guarda en una tabla propia"); design D8 paso 6 ("Si no se cumple, no se persiste nada"); D9 (`config_id` FK a una config que solo existe congelada); tasks 4.3.
- Observación: los artefactos se contradicen. Con D9 tal como está es imposible guardar un veredicto sin una configuración congelada.
- Impacto: además de la contradicción, el ciclo "ajustar PROMPT_VERSION y repetir hasta 5/5" no deja registro de cuántas variantes se probaron ni de sus resultados. Para un paper que reporta acuerdo humano-juez, eso es un garden of forking paths no auditable.
- Criterio incumplido: coherencia entre spec y design; reproducibilidad/auditabilidad (restricción 2).
- Corrección verificable: o se cambia la spec, o (recomendado) se agrega persistencia append-only de cada corrida de calibración (config candidata no congelada, o tabla de corridas) con sus veredictos y reporte, y el congelado marca cuál corrida lo justificó. Test: una corrida que no cumple el criterio deja sus filas y no crea config congelada.

### I1. IMPORTANTE - El criterio de congelado sobre 5 anclas es medible pero engañoso tal como está

- Fuente: design D8 pasos 4-5, proposal pregunta 2, spec calibración "Congelar exige un criterio medible superado"; E13.
- Observación: (a) se ajusta el framing contra las mismas 5 anclas con las que se decide congelar: no hay conjunto separado, el 5/5 mide ajuste, no generalización; (b) 2 de 5 son `es_frontera` con confianza media: exigir 100% ahí premia sobreajustar casos que los propios humanos marcan dudosos; (c) ninguna ancla ejercita evidencia insuficiente ni consultas administrativas; (d) una sola corrida a temperatura 0 no mide estabilidad, y la caché del gateway (E5) puede hacer que una repetición devuelva lo mismo sin llamar al modelo; (e) las dimensiones son "solo informativas"; (f) D6 remite a "D8 sobre si entran como few-shot" y D8 no lo trata: si las anclas entran al prompt, el 5/5 es trivial.
- Impacto: un 5/5 se puede presentar como validación del juez cuando no lo es.
- Criterio incumplido: criterio de aceptación no engañoso; pregunta 2 sin la información que el humano necesita para decidir.
- Corrección verificable: el plan deja explícito y testeable: anclas nunca en el prompt (test que lo afirma sobre el prompt armado); repeticiones N>1 sin caché o con `cache_hit` registrado y exigido falso; reporte por dimensión obligatorio en el criterio o justificación de por qué no; tope o pre-registro de iteraciones (ligado a B4); y la recomendación de un conjunto de retención con etiquetas consensuadas fuera de la muestra presentada al humano como opción en la pregunta 2. El umbral lo decide el humano.

### I2. IMPORTANTE - El firewall no falla cerrado ante una lista de exclusión vacía o mal leída, y el mutante propuesto es débil

- Fuente: design D7, spec calibración "Calibración restringida...", tasks 3.1-3.2.
- Observación: no se especifica qué pasa si el CSV no existe, no tiene columna `episode_id`, tiene BOM, mayúsculas, espacios, o trae una cantidad distinta de 150. Firma `set[UUID]` contra strings del CSV: una comparación sin normalizar nunca coincide y el guard pasa en silencio. El mutante "invertir la condición" lo mata cualquier test; no prueba nada sobre las fallas probables. Además el CSV vive en `~/Documentos`, fuera de cualquier contenedor donde corra el script; la tabla `estudio_muestra` del mismo estudio ya tiene los `episode_id` y no se considera como fuente.
- Impacto: el riesgo que el propio proposal llama "el más parecido a CRITICAL" queda cubierto por un guard que puede aprobar todo sin avisar.
- Criterio incumplido: restricción 1 como requisito verificable; "guard demostrable con test y mutante".
- Corrección verificable: requisito y escenarios nuevos: archivo ausente / sin columna / IDs no parseables / conteo distinto del esperado -> error y no se lee nada; comparación por `UUID` normalizado. Mutantes obligatorios: (1) guard reemplazado por `return`, (2) comparación str vs UUID sin normalizar, (3) lista de exclusión vacía aceptada. Decidir fuente (CSV, `estudio_muestra.episode_id`, o ambas con chequeo cruzado) y dónde corre. Spec: el guard corre antes de leer el CTR (no solo "antes de llamar al LLM"; y "antes de la base" es imposible porque las anclas salen de la base).

### I3. IMPORTANTE - El flujo D2 no aplica la validación de completitud: un veredicto incompleto o sin cita requerida quedaría `ok`

- Fuente: design D2 (solo `evaluar_pedido`), D3 (`regimen` opcional), D4 ("cada dimensión cuya cita no está vacía"); proposal (dice reutilizar `faltantes_cierre`); E2.
- Observación: `evaluar_pedido` admite pedidos parciales; con `regimen` omitido y una dimensión sin valor devuelve `regimen=None` sin error. Una dimensión `presente` con cita vacía pasa `evaluar_pedido` y D4 la saltea. Solo `faltantes_cierre` lo detecta, y el diseño no la llama ni tiene un estado para eso.
- Impacto: veredictos `ok` sin régimen o sin la cita que el codebook exige.
- Criterio incumplido: spec "Régimen derivado por la misma regla y validación de completitud"; codebook línea 30.
- Corrección verificable: D2 llama `faltantes_cierre` tras `evaluar_pedido` y mapea no-vacío a un estado (por ejemplo `incompleto`, no-ok para el criterio); escenarios y tests RED/GREEN para dimensión faltante, cita requerida vacía y régimen omitido con dimensiones incompletas. Decidir cómo el juez cumple `notas` si el esquema las exige para un régimen o frontera (hoy el output tiene `justificacion_global`, no `notas` ni `es_frontera`).

### I4. IMPORTANTE - "Misma fuente que el humano" sin las validaciones del endpoint; reutilizar helpers de rutas choca con el alcance

- Fuente: spec codificación "Entrada idéntica"; design D8 paso 3 ("llamada directa a `filtrar_traza` + al lector del CTR"); proposal "Fuera de alcance" (no cambiar `estudio_trabajo.py`); E7.
- Observación: el endpoint humano verifica `traza_version`, enunciado revisado, evidencia fija (`seq_tope`/`chain_hash_tope`) y trata el episodio inexistente. D8 no lo menciona y no hay estados para esos casos. Las funciones que habría que reutilizar están en `routes/estudio_trabajo.py` (varias privadas): o se importan desde rutas, o se mueven (tocando un archivo fuera de alcance), o se duplican (segunda implementación de la fuente).
- Impacto: el juez podría codificar sobre evidencia alterada o con otro enunciado que el humano.
- Criterio incumplido: spec "mismo filtro y la misma fuente"; invariante ADR-063 (evidencia fija, falla cerrada).
- Corrección verificable: decidir y documentar la vía (recomendado: extraer a un servicio puro sin cambio de comportamiento, con los tests existentes de `test_estudio_traza_db.py` en verde, y declararlo como cambio de alcance aprobable); agregar estados/abortos para `evidencia_alterada`, `traza_version_distinta`, `enunciado_pendiente`, episodio inexistente y `CTRNoDisponibleError`, con tests.

### I5. IMPORTANTE - Hash de prompt ausente y reproducibilidad por veredicto inconsistente entre D6 y D9

- Fuente: restricción 2 del encargo ("hash de codebook y prompt registrados por resultado"); design D6 ("`contenido_sha256` denormalizado" en cada veredicto) vs D9 (columnas de `estudio_juez_veredicto` sin `modelo`, `prompt_version`, hash); spec "Reproducibilidad registrada por veredicto".
- Observación: no hay hash del framing ni del prompt armado; `PROMPT_VERSION` depende de disciplina manual. CLAUDE.md ya registra que tests de "determinismo" no detectan cambios y que solo un golden literal lo hace.
- Impacto: T-002 no puede comprobar que el código que corre sobre los 150 es el framing congelado.
- Criterio incumplido: restricción 2.
- Corrección verificable: persistir `prompt_sha256` (framing + JSON Schema de salida) en la config y en cada veredicto, junto con `modelo` devuelto, `prompt_version`, `codebook_version_id`, `contenido_sha256` y `traza_version`; test golden que fija el sha del framing para el `PROMPT_VERSION` vigente (falla si se cambia el texto sin bump). Alinear D6, D9 y spec.

### I6. IMPORTANTE - Garantías de la migración no verificadas en deploy ni por `check-rls`

- Fuente: design D9, Migration Plan, tasks 1.2 y 6.5; E10, E11.
- Observación: el ENTRYPOINT sigue arrancando si `alembic upgrade` falla, así que la inmutabilidad (triggers) puede no existir en producción sin aviso. Tasks no incluye `make check-rls` ni el trigger `TRUNCATE` del patrón 0007; D9 no lista `tenant_id` explícito (se infiere de `apply_tenant_rls`).
- Impacto: "config congelada inmutable" podría ser falso en la base real.
- Criterio incumplido: restricción 6 (RLS en toda tabla con `tenant_id`); spec "Configuración congelada es inmutable".
- Corrección verificable: D9 lista `tenant_id` (TenantMixin); 1.2 incluye trigger TRUNCATE; 6.5 suma `make check-rls`; Migration Plan agrega verificación post-deploy (`alembic current` = 0008 y existencia de los triggers) antes de correr la calibración.

### I7. IMPORTANTE - Escenarios de spec sin tarea que los pruebe

- Fuente: spec codificación "Ítem de ancla..." (prompt sin `episode_id` ni campos de etiqueta/clasificación, con enunciado y `contenido_md`), "Codebook vigente sin congelar"; spec calibración "Recalibración con otro modelo".
- Observación: tasks 2.4 no afirma el contenido del prompt; ninguna tarea cubre la vigente sin congelar ni la recalibración que crea fila nueva.
- Impacto: la propiedad central de ceguera ("el juez nunca ve episode_id ni etiquetas") queda sin test.
- Corrección verificable: tests explícitos: el `messages` capturado por el mock no contiene el `episode_id`, `item_id`, ni claves/valores de `estudio_etiqueta`/`classifications`/`respuesta_esperada`, y sí contiene enunciado y `contenido_md`; vigente en borrador -> rechazo sin llamar al LLM; segunda calibración -> nueva fila, la anterior intacta.

### I8. IMPORTANTE - Sin baseline de regresión ejecutado

- Fuente: tasks 5.1-5.2 ("mismo verde que antes del change"); E17.
- Observación: el revisor no pudo correr las suites (pytest ausente en el entorno del worktree). No hay "antes" registrado.
- Corrección verificable: el constructor corre y registra el baseline de 5.1/5.2 antes de tocar código (ya lo exige su contrato); el plan lo nombra como paso 0.

### M1. MENOR - `sin_contenido` casi nunca se dispara

`filtrar_traza` incluye `episodio_abierto` como `inicio` (E3), así que una traza con tope fijo no queda vacía en la práctica; "episodio sin chat" va al LLM. Definir el disparador sobre ausencia de elementos con contenido (por ejemplo, sin `mensaje_alumno`, `codigo`, `ejecucion`, `prueba`, `nota`) o declarar que el caso lo resuelve el LLM.

### M2. MENOR - El test de separación propuesto no puede probar lo que afirma

1.3 pide "confirmar que ningún endpoint fuera de este módulo lee estas tablas" con "el mismo patrón" que `test_estudio_separacion_db.py`, que es de flujo (E16). Usar un test estático (AST o búsqueda de `EstudioJuezConfig`/`EstudioJuezVeredicto`/nombres de tabla en `src/` con lista permitida).

### M3. MENOR - Contradicción sobre candidatos de calibración

proposal "What Changes" admite "otros episodios del segundo semestre fuera de la muestra"; D7 dice que el script solo acepta anclas. Alinear (sin etiqueta consensuada esos episodios no sirven para el criterio).

### M4. MENOR - Lógica en un archivo con guiones

`scripts/calibrar-juez-estudio.py` no es importable por nombre; poner guard, reporte y congelado en un módulo de servicio y dejar el script como envoltorio.

### M5. MENOR - Detalles del contrato con el LLM sin fijar

`feature` para el budget, `max_tokens` y truncado (el juez de producción documenta que reintentar a temperatura 0 repite el mismo corte), y la definición de "reintentos configurados" de la spec. Fijarlos en D6/D10.

### M6. MENOR - Referencias inexactas

`CompleteFn` vive en `regimen_llm.py`, no en `clients.py` (E4): importarlo desde ahí acopla el módulo nuevo al juez de producción; conviene un Protocol propio. El planner declaró sin reverificar la ausencia de L-NNN; este revisor la confirmó (E18).

## JUICIO

- (role-plan-reviewer, comparación plan vs código real y datos del estudio, confianza alta) B1, B2, I3, I4 y I6 se apoyan en lectura directa de código y datos (E2-E7, E10-E14), no en inferencia: son verificables por cualquiera con los mismos archivos.
- (role-plan-reviewer, confianza alta) La decisión central del plan (no reimplementar la regla, tablas propias, juez de producción intacto, F15 sin acoplamiento) es correcta y está bien justificada; los defectos están en los bordes: citas, modelo efectivo, vía de acceso, persistencia de intentos y fallas cerradas.
- (role-plan-reviewer, confianza media) B3 puede llevar a reclasificar a CRITICAL (nuevo proceso con secreto del gateway, credenciales de base y cuenta de servicio del CTR leyendo datos de alumnos). No lo decido: lo eleva el orquestador al humano.
- (role-plan-reviewer, confianza media) Sobre el criterio: es medible y binario, pero con N=5, sin retención y con iteración libre sobre el mismo conjunto, es insuficiente y puede ser engañoso si se reporta como validación. El umbral es decisión humana; el plan debe darle al humano esa información y dejar rastro de las iteraciones.
- (role-plan-reviewer, confianza alta) El guard del firewall es demostrable con test y mutante, a condición de I2: con los mutantes listados ahí, un test bien hecho los mata; con "invertir la condición" solo, no demuestra la falla realista.

## SUPOSICIÓN

- No verifiqué el `esquema_formulario` ni las anclas cargadas en una base real (no hay acceso ni debe tocarse); asumo, como el planner, que corresponden al codebook v1 y a `anclas_v1.json`. E12 cubre solo el JSON en disco.
- No verifiqué cómo la UI del codificador rotula los localizadores más allá de `helpContent.tsx:807` ("turno k, codigo k, ejecucion k, prueba k, nota k, lectura k") y de que las anclas citan "mensaje k"; la gramática exacta a adoptar requiere mirar la vista de la traza.
- No verifiqué el valor de `llm_fallback_model` en producción; B2 vale igual porque el código lo permite.
- No probé comportamiento de código nuevo (no existe). Toda afirmación sobre el juez futuro es análisis del plan.

## Fuentes leídas

proposal.md, design.md, tasks.md, specs/juez-estudio-codificacion/spec.md, specs/juez-estudio-calibracion/spec.md, informes/propose-1-planner.md, informes/LEEME.md (todos completos). Código: `services/estudio_esquema.py` (260-510), `services/traza_ciega.py` (completo), `services/clients.py` (completo), `services/ctr_lectura.py` (completo), `services/regimen_llm.py` (596-735), `routes/estudio_trabajo.py` (95-219, 859-958 y mapa de funciones), `models/estudio.py` (mapa + 200-235), `alembic/versions/20261104_0007_estudio_codificacion.py` (rg de RLS/triggers), `apps/ai-gateway/src/ai_gateway/routes/complete.py` (340-509), `apps/classifier-service/Dockerfile`, `correccion_nativa.py` (rg), `tests/integration/test_estudio_separacion_db.py` (rg), `config.py` (rg). Datos: `codebook_v1_para_codificadores.md` (rg), `anclas_v1.json` (episode_id y `resp`), `muestra_150.csv` (SOLO columna `episode_id`). CLAUDE.md global, del proyecto y del repo (del contexto).

## Contaminación por otros informes

Leí `propose-1-planner.md` completo, por encargo. Lo usé como mapa de qué afirmaba el planner; cada hallazgo se verificó contra código o datos con comandos propios (EVIDENCIA). No consulté informes de otros changes ni Engram.

## Chequeos no ejecutados

- Suites de regresión (E17): pytest ausente en el entorno.
- `make check-rls`, `alembic upgrade/downgrade`: requieren base; prohibido tocar bases en este encargo.
