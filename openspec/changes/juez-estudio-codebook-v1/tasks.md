# Tasks: juez-estudio-codebook-v1

## Estado de orquestación

- Rol activo: planner, intento 4 ACOTADO (autorizado por Juani el 06/11/2026, ver "Decisión humana 06/11/2026") terminado; siguiente: plan-reviewer, que controla solo las correcciones de `informes/propose-3-plan-reviewer.md` y regresiones directas. Intento de la compuerta de plan: 4 (vuelta extra autorizada; no hay un quinto sin nueva respuesta escrita de Juani). Rama `feat/juez-estudio-codebook-v1`, base `origin/main` 178c343 (código de `cibse-codificacion-ciega` en `main`, su change de OpenSpec sin archivar).
- Clasificación propuesta: **CRITICAL** (proposal.md, "Clasificación", reevaluada con la superficie reducida). La decide Juani.
- Ejecutores: sin tabla "Role executors" en el proyecto; subagentes nativos de Claude para los cinco roles salvo indicación del orquestador.
- Informes: `informes/propose-1-*`, `informes/propose-2-*`, `informes/propose-3-*`, `informes/propose-4-planner.md` (disposición hallazgo por hallazgo del informe del revisor del intento 3). Índice en `informes/LEEME.md`.
- Bloqueos para construir: (1) aprobación humana fechada en `proposal.md` `## Aprobación`, con respuesta a las diez decisiones de "Decisiones pendientes"; (2) plan-reviewer intento 4 sin bloqueantes.
- Decisión de trabajo SUPOSICIÓN: la vía de acceso (D2). Si Juani elige otra, el plan vuelve al planner.
- Decisión humana vigente (06/11/2026): opción B, sin calibración (proposal.md).
- Firewall del estudio (vigente): ningún rol de este change abre contenido, trazas, etiquetas humanas ni veredictos de producción de los 150, ni nada bajo `analisis_produccion/`. Correr el juez sobre los 150 no es parte de este change. El orquestador consulta veredictos de producción en otro ticket; nada de eso entra en los briefs de este change, en particular en el del constructor que redacte el `FRAMING` (aislamiento del autor del prompt, design D11).
- Próxima acción: plan-reviewer, control acotado del intento 4.

## Reglas para el constructor (resumen de contrato)

- TDD por comportamiento: RED por aserción (no por error de setup), GREEN mínimo, refactor. CRITICAL: un mutante por cada aserción de seguridad/datos (sección 8). Registrar bajo cada tarea comando, timestamp, revisión y salida relevante.
- Ningún test ni comando lee contenido de los 150. Si hace falta saber si un ID está en la muestra, se hace contra una fixture o contra `estudio_muestra` de una base de TEST creada por el propio test (insertando filas directamente: `cargar_muestra` rechazaría la superposición, por eso el test inserta sin pasar por ella).
- El `FRAMING` se redacta SOLO desde el codebook y el formato (design D8): sin ejemplos, sin resultados. Fixtures de esquema: construidas a mano con las mismas claves del esquema v1 (4 regímenes, `dimensiones_opcionales_si_regimen`, `notas_obligatorias_si_regimen`, `notas_obligatorias_si_frontera`, `confianza.obligatoria`); no se copian datos de episodios.
- Paso 0 obligatorio antes de tocar código: preparar entorno y registrar baseline.
- Dónde viven los tests: todo lo puro (motor, gramática, armado, hash, criterio, resumen, `evaluar_item`) en `apps/classifier-service/tests/unit/`, que CI corre; solo lo que necesita Postgres (acceso, firewall, inmutabilidad, RLS, persistencia de abortos) en `tests/integration/`, que CI NO corre (decisión 7).
- Un `complete` falso que devuelve un JSON armado por el test NO prueba que el modelo conozca el formato: las pruebas de contrato (3.4) usan un falso que lee el formato de los `messages` recibidos.

## 0. Baseline

- [ ] 0.1 `uv sync --all-packages` en el worktree; verificar `uv run pytest --version`. Registrar comando y salida.
- [ ] 0.2 Baseline unitario antes de cambiar nada: `uv run pytest apps/classifier-service/tests/unit -q`, y por separado `test_regimen_llm.py`, `test_classify_ep_regimen_llm_read.py`, `test_traza_ciega.py` y `apps/evaluation-service/tests/unit/test_correccion_nativa.py`. Registrar conteos y fallos preexistentes.
- [ ] 0.3 Baseline de integración con Postgres real (`CLASSIFIER_TEST_DB_URL`; el conftest salta si no hay base y no soporta testcontainers): `test_estudio_traza_db.py`, `test_estudio_separacion_db.py`, `test_estudio_inmutabilidad_db.py`, `test_estudio_anclas_db.py`. Registrar conteo de pasados y de **skipped**. Sin base el constructor no avanza a las secciones 1, 2, 4 y 5.

## 1. Extracción mínima de la fuente de enunciado y evidencia (D3)

- [ ] 1.1 Crear `apps/classifier-service/src/classifier_service/services/estudio_traza.py` con `enunciados_revisados`, `enunciado_del_item` (movidos sin cambio de lógica desde `routes/estudio_trabajo.py`) y `comprobar_evidencia(eventos, seq_tope, chain_hash_tope)` que levanta `EvidenciaAlteradaError`. `_item_del_estudio` NO se mueve. RED en `tests/unit/test_estudio_traza.py`: evidencia que coincide no levanta; tope inexistente y `chain_hash` distinto levantan; enunciado sin revisar da `None`; ejercicio sin revisar da `None`. Consumidor: `traza_ciega`.
- [ ] 1.2 `routes/estudio_trabajo.py::traza_ciega` y los demás usos internos llaman al servicio. Prueba: `test_estudio_traza_db.py` y `test_estudio_separacion_db.py` verdes SIN editarlos (comparar con 0.3); `git diff` de esos tests vacío. Si la decisión 4 fue "no", esta sección se reemplaza y vuelve al planner.

## 2. Esquema de datos (D9)

- [ ] 2.1 `models/estudio_juez.py` con `EstudioJuezCorrida`, `EstudioJuezVeredicto`, `EstudioJuezConfig` (`TenantMixin`), importadas desde `models/__init__.py`. Test unitario: las 3 en `Base.metadata.tables` con `tenant_id`; ninguna columna ni FK hacia `estudio_muestra`; `UNIQUE(corrida_id, ancla_item_id, repeticion)` y las `UNIQUE` de la config declaradas; corrida con `corrida_anterior_id`, `prompt_sha256_anterior`, `modelo_anterior`; config con `n_modelos_previos`, `n_cambios_tras_cumplir`, `corridas_previas`; los archivos de otros paquetes que hacen `create_all` de `classifier_service.models` sobre SQLite siguen pasando.
- [ ] 2.2 Migración `alembic/versions/2026110X_0008_estudio_juez.py` en DOS tramos de commit/ejecución para que cada RED sea por aserción y no por error de setup: (a) tablas, `apply_tenant_rls`, `UNIQUE` (incluidas `UNIQUE(estudio_id, codebook_version_id)` y `UNIQUE(corrida_id)` de la config) y claves foráneas; (b) triggers `BEFORE UPDATE/DELETE` con `estudio_inmutable` en veredicto y config, trigger de cierre único en corrida (solo `en_curso -> cerrada|abortada`, cambiando únicamente `estado`, `cerrada_at`, `motivo_aborto`, `resumen`) y trigger de SENTENCIA `BEFORE TRUNCATE` por tabla. Ciclo `upgrade -> downgrade -> upgrade` contra Postgres real.
- [ ] 2.3 `tests/integration/test_estudio_juez_modelos_db.py` (Postgres real, rol `classifier_user` no superuser del conftest). Con (a) aplicado y sin (b): RED por aserción de UPDATE/DELETE de veredicto y config, TRUNCATE de cada tabla, segunda modificación de una corrida cerrada, modificación de campos no permitidos en el cierre; GREEN al aplicar (b). Más: `UNIQUE` de veredicto (segundo insert del mismo par falla); RLS con DOS aserciones (el tenant B no ve la fila del tenant A, Y el tenant A sí ve su propia fila; sin la segunda, una policy quitada con FORCE da default-deny y la primera pasa vacía), más `UNIQUE(estudio_id, codebook_version_id)` y `UNIQUE(corrida_id)` de la config (segunda config de la misma versión falla). Salida de `uv run python scripts/check-rls.py` registrada.
- [ ] 2.4 `verificar_esquema_juez(session)` (Postgres: `to_regclass` de las 3 tablas; SQLite: no-op). Test de integración: tabla ausente en una base de test -> `EsquemaJuezIncompletoError` (503 `esquema_juez_incompleto` en la ruta).

## 3. Motor del juez (puro, sin DB ni red): `services/juez_estudio.py`

- [ ] 3.1 `construir_json_schema(esquema)` = `esquema_salida` (fuente única del formato, D7) y `validar_forma(schema, obj)` propio: dimensión `{valor: enum|null, cita: string|null}` NO requerida (la presencia es el paso 2 de D7b), `regimen` requerido, `confianza`/`es_frontera`/`notas` según esquema, `additionalProperties:false`, sin `regimen_propuesto`, sin `strict`. RED con esquema fixture de 2 dimensiones y 2 regímenes: clave ajena (incluida `regimen_propuesto`), régimen ausente, enum inválido y tipo erróneo rechazados. No se agrega `jsonschema`. Consumidores: 3.3, 3.4 (mensaje), 3.5 (`response_format`), 3.6 (hash). Tests en `tests/unit/test_juez_estudio_esquema.py`.
- [ ] 3.2 Gramática de citas (D4): `parsear_citas`, `resolver_citas`. Test parametrizado con las CINCO citas literales (`mensaje 1`, `mensaje 4 y ejecución 1`, `ejecuciones 2 y 3`, `ejecuciones 7 a 9`, `mensajes 1, 3 y 5`) contra una traza fixture donde existen (forma canónica esperada) y la variante con número inexistente (falla); tildes y mayúsculas; `#n` y copia/pegado sin `k`; rango invertido y de más de 200; cita requerida sin localizador; cita no requerida con texto libre; **`turno k` con mensaje del alumno y respuesta del tutor compartiendo `k` guarda todos los elementos**; **prosa "la lectura 3 veces" valida `lectura 3` o es `cita_invalida` si no existe**.
- [ ] 3.3 `evaluar_item(esquema, elementos, raw)` en el orden único de D7b (sin llamada al modelo dentro; tests en `tests/unit/test_juez_estudio_evaluar.py` con una fixture de esquema hecha a mano con las claves del esquema v1: 4 dimensiones, 4 regímenes, `regimenes_exentos`, `dimensiones_opcionales_si_regimen`, `notas_obligatorias_si_regimen`, `confianza.obligatoria`, `reglas_regimen`). Un RED/GREEN por estado: `ok`; **`evidencia_insuficiente` sin dimensiones, con `notas` Y `confianza` -> `ok`; sin `notas` -> `incompleto`; sin `confianza` -> `incompleto`**; **dimensión omitida con régimen no exento -> `incompleto` con `dimension:*` (caso que `evaluar_pedido` solo rechazaría con 422; el test lo verifica con la fixture y falla si el orden es otro)**; cita requerida vacía (`cita:*`), `notas`/`confianza` exigidas ausentes -> `incompleto`; `cita_invalida`; `inconsistente` (422 de `evaluar_pedido`, dimensiones completas y régimen distinto del derivado); 400 de `evaluar_pedido` (p. ej. `es_frontera` sin marca en el esquema) -> `respuesta_malformada`; `respuesta_malformada` (JSON inválido, truncado, régimen omitido, clave ajena, `regimen_propuesto`). Importa `evaluar_pedido` y `faltantes_cierre`; test estático: el módulo no define su propia regla de régimen. `sin_contenido` se decide en una función aparte `hay_contenido(elementos)` (sin `raw`), con test: solo `inicio/lectura/fin` -> sin contenido; solo copias/pegados -> con contenido.
- [ ] 3.4 `armar_mensajes(framing, contenido_md, esquema_salida, enunciado, elementos, referencia)` y ceguera (D11). Tests en `tests/unit/test_juez_estudio_mensajes.py`, todos ANTES de cualquier trabajo de la sección 4: (a) **ceguera**: `complete` falso captura `messages`; con los valores completos de la fixture (UUID de 36 caracteres) ausencia de `episode_id`, `item_id`, claves y valores de `respuesta_esperada` y `explicacion_md`; presencia de enunciado TP y ejercicio, `contenido_md`, `n`/`k`; la firma no recibe ancla ni etiqueta; aviso si una `explicacion_md` está contenida en `contenido_md`. (b) **contrato presente (B1)**: cada clave de dimensión, cada valor permitido, cada régimen y las claves `respuestas`, `valor`, `cita`, `regimen`, `confianza`, `es_frontera`, `notas` del esquema fixture figuran en el mensaje de sistema; el contrato del mensaje es el mismo dict que `construir_json_schema`. (c) **el modelo solo sabe lo que está en el mensaje**: un `complete` falso que arma su respuesta ÚNICAMENTE extrayendo del `messages` recibido las claves y los valores del contrato; con el contrato omitido no puede responder y el test falla por aserción; con el contrato presente su respuesta pasa por `validar_forma` y `evaluar_item` y termina `ok`. (d) **respuesta real de formato esperado**: fixtures en texto escritas a mano (régimen no exento con las cuatro dimensiones; evidencia insuficiente con dimensiones omitidas, `notas` y `confianza`) que parsean y evalúan `ok`; y una envuelta en ```json que da `respuesta_malformada` (decisión declarada en D7). (e) **`FRAMING` sin ejemplos**: no contiene ningún valor de dimensión ni clave de régimen de la fixture por palabra completa (valores de la fixture de al menos 6 caracteres, guarda de lista no vacía).
- [ ] 3.5 `clasificar_con_juez_estudio(...)` con `JuezCompleteFn` propio (D7); tests en `tests/unit/test_juez_estudio_llamada.py`: RED/GREEN con `complete` falso: parámetros (`temperature=0.0`, `max_tokens=6000`, `feature="estudio_juez"`, `materia_id=None` capturado, `response_format` = sobre `json_schema` **sin la clave `strict`** y con el mismo `esquema_salida` que viaja en los mensajes); otro `model` -> `modelo_no_pinneado` (guarda ambos); `provider="mock"`; `cache_hit=True` -> `respuesta_de_cache`; excepción de red con 1 reintento -> `llm_caido` con `modelo_respondio` nulo; JSON inválido y truncado sin reintento (el falso cuenta las llamadas); HTTP 429 -> aborta sin reintento (el falso cuenta); `mismo_modelo` con prefijo de namespace; `referencia` aleatoria distinta en cada intento incluido el reintento, sin `item_id`/`episode_id`.
- [ ] 3.6 Reproducibilidad (I7): `prompt_sha256` según D8 (cubre `FRAMING`, `armar_mensajes` sobre `ENUNCIADO_REF`/`ELEMENTOS_REF` y `PARAMETROS_LLAMADA`); tests en `tests/unit/test_juez_estudio_hash.py`: golden con literal para `sha256(FRAMING)` del `PROMPT_VERSION`; golden con literal del `messages` completo de `armar_mensajes` sobre una fixture fija; el hash cambia si se altera `max_tokens` o la temperatura de `PARAMETROS_LLAMADA`, o si `armar_mensajes` cambia el orden de los mensajes o la serialización de un elemento (monkeypatch); cada veredicto en cualquier estado trae modelo pedido y respondido (nulo si no hubo llamada), `prompt_version`, `prompt_sha256`, `validador_version`, `codebook_version_id`, `contenido_sha256`, `traza_version`, `referencia`, `cost_usd`. Test de logging: salida cruda y contenido de la traza no aparecen en `caplog` en ningún estado.

## 4. Corrida y congelado: `services/juez_corrida.py`

- [ ] 4.1 Firewall (D5): `ancla_en_muestra(session, episode_id)` sin filtro de estudio. Integración con Postgres (`test_estudio_juez_firewall_db.py`): ancla en la muestra del MISMO estudio (fila insertada directo) -> el paso aborta `firewall_muestra` con un `CTRLector` y un `complete` que **fallan si se los llama** (orden: antes del CTR); **ancla en la muestra de OTRO estudio del mismo tenant (estudio creado por el test) -> también aborta**; muestra con otros episodios y muestra vacía -> procede; recarga insertada entre dos pasos -> el segundo aborta (lectura fresca); la consulta selecciona solo `episode_id` y no tiene `estudio_id` en el WHERE (inspección del SQL emitido). El aborto queda persistido leído desde otra sesión y la respuesta es 409 `firewall_muestra`.
- [ ] 4.2 Resolución de ítems y fase síncrona de `POST /corridas` (D6): anclas solo de `estudio_ancla` con `estudio_id` y `codebook_version_id` vigente (otro estudio y otra versión no aportan); versión sin congelar o sin anclas -> 409; **cantidad de anclas distinta de `N_ANCLAS_V1` (4, 6) -> 409 `anclas_distintas_de_lo_previsto`**; versión con configuración congelada -> 409 `ya_congelada`; modelo fuera de la lista -> 422, lista vacía -> 503; `traza_version` distinta -> 409 sin fila; `motivo` obligatorio cuando el `prompt_sha256` **o el modelo** difieren de los de la corrida anterior de la misma versión (la última creada, en cualquier estado); 422 sin motivo y con motivo de solo espacios; la corrida guarda `corrida_anterior_id`, `prompt_sha256_anterior` y `modelo_anterior`. Ningún rechazo crea fila ni llama al CTR o al modelo.
- [ ] 4.3 `siguiente(...)` en las fases de D6 (sesión 1 / sin sesión / sesión 2 / sesión 3); `test_estudio_juez_paso_db.py`. Orden determinista `(repeticion, item_id)`; anclas tomadas de `corrida.codebook_version_id` aunque la vigente haya cambiado (M7); **filtro de traza**: con un `CTRLector` falso que devuelve un evento con `seq` posterior al `seq_tope` y un evento con un campo fuera de la lista blanca, el `messages` capturado por el `complete` falso no los contiene; casos de entrada sin LLM (`evidencia_alterada`, `enunciado_pendiente`, `episodio_inexistente`, `ctr_no_disponible` -> `entrada_no_disponible`; `sin_contenido`) con un `complete` que **falla si se lo llama**; veredicto en su transacción; cierre con `resumen` al último par, con `UPDATE ... WHERE estado='en_curso'` y 0 filas afectadas sin error (dos `siguiente` seguidos tras una caída entre veredicto y cierre); **fallo forzado en la sesión 3 no pierde el veredicto y el siguiente `siguiente` cierra**; `par_ya_procesado` por `UNIQUE` (409 levantado fuera de la sesión); reanudación tras interrupción (se descarta el servicio y se vuelve a llamar); corrida `cerrada`/`abortada` -> 409 `corrida_no_en_curso`; **abortos que persisten aunque la respuesta sea 409, leídos desde otra sesión: `firewall_muestra`, `traza_version_distinta`, `prompt_distinto`, `presupuesto_excedido`** (este último sin veredicto del par); excepción no prevista en un paso deja la corrida `en_curso` y sin veredicto parcial. Todo con `complete` y `CTRLector` falsos y concurrencia 1 (determinista).
- [ ] 4.4 Resumen e informativo (`tests/unit/test_juez_estudio_resumen.py`): `calcular_resumen(veredictos, anclas, criterio)` con conteos por estado, regímenes por ancla y repetición, `estable`, costo, `criterio.cumple_tecnico` con las condiciones falladas, y bloque `informativo` (coincidencia de régimen y por dimensión contra `respuesta_esperada`, rotulado). Fixtures: todo estable y coincidente; estable y NO coincidente (el criterio sigue cumplido); ancla inestable.
- [ ] 4.5 `evaluar_criterio_tecnico(corrida, veredictos, vigentes)` (D8, condiciones 1 a 7; función pura en `tests/unit/test_juez_estudio_criterio.py`) y `congelar(...)`: recalcula desde veredictos persistidos. Un RED/GREEN por condición: corrida abierta/abortada/de otro estudio; hashes, `validador_version` o `parametros` distintos de los vigentes; `prompt_sha256` de un veredicto distinto del de la corrida; modelo no permitido; `repeticiones` menor que la constante (no se puede degradar a 1); **menos de `N_ANCLAS_V1` anclas (una sola ancla con 3 repeticiones, 4 anclas) no congela**; veredictos menos que `N_ANCLAS_V1 x REPETICIONES_V1` (14 de 15 falla); un `sin_contenido` o `entrada_no_disponible` no suma; estado no `ok`; `mock`; `cache_hit`; modelo distinto; proporción de anclas estables menor que `ESTABILIDAD_MIN_V1` (con el valor que decida Juani; la prueba parametriza 1.0 y 0.8); ancla pasada a la muestra tras el cierre, también de otro estudio del tenant (409 `firewall_muestra`). Config guarda hashes, modelo, `proveedores_respondieron`, parámetros, `criterio`, `coincidencia_informativa`, `n_corridas_previas`, `n_prompts_previos`, `n_modelos_previos`, `n_cambios_tras_cumplir` y `corridas_previas` (probado con una secuencia de 3 corridas con un cambio de prompt tras una corrida que cumplía). **Congelar dos veces la misma corrida, o otra corrida de la misma versión, responde 409 `ya_congelada`** (el `IntegrityError` de `UNIQUE(corrida_id)` y `UNIQUE(estudio_id, codebook_version_id)` mapeado, sin 500). Integración Postgres: UPDATE/DELETE sobre la config creada (ejercita el trigger).

## 5. Endpoints: `routes/estudio_juez.py` y registro

- [ ] 5.1 Bodies con `extra="forbid"` (`{modelo, motivo?}` y `{corrida_id}`) y rutas de D2 con `require_membresia(..., (INVESTIGADOR,))` dentro del handler. Registrar el router en `main.py` con un comentario sobre la premisa de ruteo (`/api/v1/interrater` -> classifier-service, `proxy.py:64`). Tests de integración (`test_estudio_juez_acceso_db.py`, patrón de `test_estudio_acceso_db.py`) **parametrizados sobre las seis rutas** (`POST corridas`, `POST corridas/{id}/siguiente`, `GET corridas`, `GET corridas/{id}`, `POST configuraciones`, `GET configuraciones`) con guarda de que la lista tiene 6 elementos: sin membresía, codificador, revocada, otro estudio y estudio inexistente -> 403 de cuerpo idéntico con `CTRLector`/`complete` que fallan si se los llama; **no miembro con body inválido -> 422 sin revelar el estudio**; investigador activo -> 201; body con `episode_id`/`item_id`/`items`/`repeticiones`/`criterio`/`modo` -> 422 y ninguna corrida creada; corrida de otro estudio con membresía propia -> 404.
- [ ] 5.2 Lectura: `GET .../corridas` y `/{id}` y `GET .../configuraciones` con schemas de respuesta explícitos; ni `episode_id` ni `raw_llm_output` en ninguna respuesta. Test que recorre las respuestas de TODAS las rutas (incluidas `POST corridas`, `POST siguiente` y `POST configuraciones`, y todos los estados de veredicto) buscando, como cadena completa y a cualquier profundidad del JSON, el UUID de `episode_id` de la fixture y la clave `raw_llm_output`; con guarda de que se recorrió al menos una respuesta por ruta. `item_id` opaco del ancla sí.
- [ ] 5.3 Separación estática: test que recorre `src/` (AST o búsqueda de nombres) y falla si `EstudioJuez*` o `estudio_juez_*` aparecen fuera de la lista permitida (`models/estudio_juez.py`, `models/__init__.py`, `services/juez_corrida.py`, `services/juez_estudio.py`, `routes/estudio_juez.py`, `alembic/`); y que `routes/estudio.py`, `routes/estudio_trabajo.py` y `routes/classify_ep.py` no los referencian. El juez no importa ni escribe `classifications`, `interrater_ratings`, `classification_reviews`, `estudio_etiqueta*`.
- [ ] 5.4 Config: `settings.juez_modelos_permitidos` (env `JUEZ_MODELOS_PERMITIDOS`, vacía por defecto) en `config.py`; test de parseo.

## 6. No regresión y cableado

- [ ] 6.1 Rerun del baseline 0.2/0.3 sobre la revisión final: mismos conteos; `git diff --stat` sobre `tests/` solo agrega archivos nuevos.
- [ ] 6.2 Búsqueda de imports: `juez_estudio` y `juez_corrida` no importados desde `routes/classify_ep.py`, `services/review.py`, `regimen_llm.py`, `apps/web-teacher`, `apps/evaluation-service`; `regimen_llm` no importado desde los módulos nuevos.
- [ ] 6.3 Cableado: el router está en `app.routes` y los endpoints aparecen en la lista de rutas de la app (test).

## 7. Documentación y base de conocimiento

- [ ] 7.1 `docs/servicios/classifier-service.md`: REWRITE de tablas y endpoints; APPEND del runbook (obtener el Bearer de un investigador, crear corrida, 15 pasos con refresco de token y reanudación, leer el resumen, congelar; no deployar classifier-service con un paso en vuelo) y de la verificación post-deploy (`alembic current`, triggers, `make check-rls`).
- [ ] 7.2 `CLAUDE.md`: REWRITE de los dos invariantes ADR-063 y de «63 ADRs» a 64; APPEND del invariante del juez y de `PROMPT_VERSION`/`prompt_sha256` golden. Verificar que no se tocó otra sección y correr `python3 scripts/check-claude-md.py` (esperado `[OK]`).
- [ ] 7.3 `docs/adr/064-juez-estudio-codebook-v1.md` con las decisiones de design.md y la opción B con su consecuencia para el paper. Incluye el límite de "sin ajuste por resultados", la exclusión de `regimen_propuesto` (o su inclusión, según la decisión 9), la configuración única por versión y el resultado de 8.0 (qué archivo y qué recorte es `contenido_md`). No tocar `docs/adr/README.md`.
- [ ] 7.4 `docs/SESSION-LOG.md`: APPEND. `knowledge-base-report.md` del change al cierre (REWRITTEN/APPENDED/PENDING).

## 8. Mutantes, verificación y cierre (CRITICAL)

Cada mutante se aplica temporalmente, se observa que el test indicado falle por aserción, se revierte y se registra comando y salida. Ninguno se entrega. La frase "cada uno debe matar al menos un test" se reemplaza por esta tabla aserción -> mutante -> test que lo mata.

- [ ] 8.0 **Prerrequisito humano, antes de la primera corrida real** (lo hace una persona, no un agente): comparar `sha256(contenido_md.encode("utf-8"))` del texto devuelto por `GET /{clave}/codebook/vigente` con el `sha256` del archivo del codebook elegido (`codebook_v1.md` o `codebook_v1_para_codificadores.md`, leído tal cual), registrar en el ADR cuál es y qué recorte (secciones 1 a 9) se cargó, y confirmar que ninguna `explicacion_md` de las anclas figura copiada en `contenido_md`. Si no coinciden, se lee la diferencia y se decide antes de correr nada. Precede a 8.5.
- [ ] 8.1 Tabla de mutantes (cada fila es una tarea de ejecución; las filas de acceso se aplican por separado a cada una de las seis rutas de 5.1):

| # | Aserción | Mutante | Test que debe fallar |
|---|---|---|---|
| A1 | Solo miembros del estudio, en cada ruta | `require_membresia` -> solo `get_current_user`, una ruta por vez (x6) | 5.1 sin membresía -> 403 en esa ruta |
| A2 | Solo investigador, en cada ruta | rol ampliado a `ROLES_ESTUDIO`, una ruta por vez (x6) | 5.1 codificador -> 403 en esa ruta |
| A3 | Ítems solo del estudio | quitar filtro `estudio_id` en la consulta de anclas | 4.2 ancla de otro estudio no aporta |
| A4 | Solo versión vigente | quitar filtro `codebook_version_id` | 4.2 otra versión no aporta |
| A5 | Mismo 403 | cuerpo distinto por motivo | 5.1 cuerpo idéntico |
| A6 | Pedido sin campos ajenos | quitar `extra="forbid"` | 5.1 body con `episode_id` -> 422 |
| A7 | Corrida del estudio | detalle/paso sin filtro `estudio_id` | 5.1 corrida de otro estudio -> 404 |
| A8 | Lista permitida | aceptar modelo fuera de lista | 4.2 modelo fuera -> 422 |
| F1 | Guard de muestra | `ancla_en_muestra` -> `False` siempre | 4.1 ancla en muestra aborta |
| F2 | Guard ANTES del CTR (orden) | mover la lectura del CTR antes del guard | 4.1 con `CTRLector` que falla si se llama |
| F3 | Guard sin falso positivo | `EXISTS` sin igualar `episode_id` (bloquea con cualquier fila) | 4.1 muestra con otros episodios procede |
| F4 | Lectura fresca por par | muestra leída una vez al inicio y reusada | 4.1 recarga entre dos pasos aborta |
| F5 | Re-chequeo al congelar | quitar firewall de `congelar` | 4.5 ancla pasada a la muestra -> 409 |
| F6 | Sin FK a la muestra | agregar columna `muestra_item_id` | 2.1 sin columna ni FK hacia la muestra |
| F7 | Guard a nivel tenant (I2) | agregar `estudio_id == estudio.id` al `EXISTS` | 4.1 muestra de otro estudio del mismo tenant aborta |
| F8 | Aborto persistido (I6) | levantar la excepción HTTP dentro del `tenant_session` del aborto | 4.3 la corrida figura `abortada` desde otra sesión (firewall, traza, prompt, presupuesto) |
| F9 | Veredicto no se pierde (I6) | mismo `tenant_session` para veredicto y cierre | 4.3 fallo forzado del cierre conserva el veredicto |
| F10 | Cierre único (M4) | `UPDATE` de cierre sin `WHERE estado='en_curso'` | 4.3 dos `siguiente` seguidos tras caída |
| T1 | `siguiente` filtra con tope | no pasar `seq_tope` a `filtrar_traza` (o pasar `None`) | 4.3 evento posterior al tope ausente de `messages` |
| T2 | `siguiente` filtra con lista blanca | pasar los eventos crudos sin `filtrar_traza` | 4.3 campo fuera de la lista blanca ausente de `messages` |
| T3 | Evidencia verificada en el paso | omitir `comprobar_evidencia` en `siguiente` | 4.3 cadena alterada -> `entrada_no_disponible` sin llamada |
| T4 | Enunciado pendiente sin LLM | llamar al modelo con enunciado sin revisar | 4.3 con `complete` que falla si se llama |
| T5 | `sin_contenido` sin LLM | ignorar `hay_contenido` y llamar al modelo | 4.3 con `complete` que falla si se llama |
| C1 | Ceguera | `episode_id` agregado al prompt | 3.4(a) |
| C2 | Ceguera | `item_id` agregado al prompt | 3.4(a) |
| C3 | Ceguera | `explicacion_md`/`respuesta_esperada` al prompt | 3.4(a) |
| C4 | `raw_llm_output` fuera de la API | agregarlo al schema de respuesta | 5.2 |
| C5 | Sin log de salida cruda | salida cruda a un log | 3.6 caplog |
| C6 | Referencia sin ids | `referencia` derivada de `item_id`/ordinal | 3.5 |
| C7 | Referencia distinta por intento | misma referencia en el reintento | 3.5 |
| C8 | `episode_id` fuera de la API | agregar `episode_id` al schema de una respuesta (detalle, `siguiente`, `POST corridas`) | 5.2 recorrido de todas las rutas |
| B1a | Contrato en el prompt (B1) | `armar_mensajes` sin la sección de contrato de salida | 3.4(b) y 3.4(c) |
| B1b | Sin `strict` | agregar `"strict": true` al `response_format` | 3.5 |
| B1c | Un solo esquema | `response_format` con un esquema distinto del de los mensajes | 3.5 |
| B1d | Contrato en el hash | `prompt_sha256` sin `mensajes_referencia` | 3.6 golden del `messages` |
| H1 | Armado en el hash (I7) | cambiar el orden de los mensajes en `armar_mensajes` | 3.6 golden del `messages` |
| H2 | Parámetros en el hash (I7) | `prompt_sha256` sin `parametros` | 3.6 |
| H3 | Parámetros en el criterio (I7) | omitir la comparación de `parametros` en la condición 2 | 4.5 |
| E1 | Orden de evaluación (I1) | evaluar coherencia (`evaluar_pedido` con régimen afirmado) antes de la presencia de dimensiones | 3.3 dimensión omitida -> `incompleto` |
| E2 | `regimen_propuesto` fuera (decisión 9) | admitir `regimen_propuesto` en el esquema de salida | 3.1 y 3.3 |
| M1 | Sin caché | omitir chequeo de `cache_hit` | 3.5 y 4.5 |
| M2 | Modelo efectivo | omitir `mismo_modelo` | 3.5 y 4.5 |
| M3 | Sin mock | omitir chequeo de `provider == "mock"` | 3.5 y 4.5 |
| M4 | 429 aborta | tratar 429 como error de infraestructura con reintento | 3.5 y 4.3 |
| P1 | Inmutabilidad | quitar trigger de veredicto/config | 2.3 |
| P2 | Un veredicto por par | quitar `UNIQUE` | 2.3 y 4.3 |
| P3 | Separación | escribir en `classifications`/`estudio_etiqueta` | 5.3 |
| P4 | Criterio del servidor | tomar el criterio de un campo del body | 5.1 body con `criterio` -> 422 y 4.5 |
| P5 | Mínimo de repeticiones | aceptar `repeticiones < REPETICIONES_V1` | 4.5 |
| P6 | Conteo de pares | quitar la comparación `count == N_ANCLAS_V1 x R` | 4.5 (14 de 15) |
| P7 | Llamada real | contar `sin_contenido` como éxito | 4.5 |
| P8 | Estabilidad | comparar solo dos repeticiones | 4.5 |
| P9 | Corrida cerrada | congelar una `abortada` o `en_curso` | 4.5 |
| P10 | Hashes vigentes | omitir comparación de `prompt_sha256`/`contenido_sha256` | 4.5 |
| P11 | Motivo de cambio de prompt o modelo | no exigir `motivo`, o exigirlo solo para el prompt | 4.2 (cambio de prompt y de modelo, motivo vacío y de espacios) |
| P12a | RLS: otro tenant no ve filas | policy permisiva (`USING (true)`) en la base de test | 2.3 el tenant B no ve la fila del tenant A |
| P12b | RLS: el tenant propio sí ve | policy quitada (con FORCE: default-deny) en la base de test | 2.3 el tenant A VE su fila (aserción positiva; sin ella el caso anterior pasa vacío) |
| P13 | Esquema en runtime | `verificar_esquema_juez` -> no-op | 2.4 |
| P14 | Regla única | reemplazar `evaluar_pedido` por una regla local | 3.3 (test estático y de valores) |
| P15 | Extracción | `comprobar_evidencia` sin chequear `chain_hash` | 1.1 |
| P16 | Cantidad exacta de anclas (I3) | condición 3 con `n_items >= 1` (o tomada de la propia corrida) | 4.5 una ancla y 4 anclas no congelan |
| P17 | `validador_version` vigente | omitir su comparación | 4.5 |
| P18 | Modelo en lista en el criterio | omitir la condición de lista permitida | 4.5 |
| P19 | Una configuración por versión (I4) | quitar `UNIQUE(estudio_id, codebook_version_id)` / el mapeo a 409 | 4.5 segundo congelado -> 409 `ya_congelada` |
| P20 | Rastro de cambios (I4) | `n_cambios_tras_cumplir` calculado sin mirar `cumple_tecnico` de la anterior | 4.5 secuencia de 3 corridas |
| P21 | `prompt_distinto` al reanudar (M6) | omitir la comparación en `siguiente` | 4.3 |

**Garantías sin red si la integración de CI queda como DEUDA (decisión 7)**: acceso (A1 a A8), firewall (F1 a F10), filtro de traza en el paso (T1 a T5), inmutabilidad y RLS (P1, P2, P12a, P12b, P13), persistencia de abortos (F8, F9) y `ya_congelada` (P19) viven en `tests/integration/` y NO corren en CI: ninguna regresión posterior a la revisión entregada las detecta. Lo que sí corre en CI porque vive en `tests/unit/`: ceguera y contrato (C1 a C3, B1a a B1d), hash (H1, H2), orden de evaluación (E1, E2), criterio y resumen (P4 a P11, P16 a P18, P20), llamada (M1 a M4, C6, C7). Esto se registra en el informe del auditor como límite, no se oculta.

- [ ] 8.2 Breaker: rondas hasta limpio (foco: firewall y orden, ítems solo del servidor, citas, modelo efectivo, caché, rastro de corridas, criterio técnico). Auditor: chequeos independientes sobre la revisión entregada.
- [ ] 8.3 Checks del repo sobre la revisión final: `uv run ruff check apps/classifier-service`, `uv run ruff format --check apps/classifier-service`, `uv run mypy apps/classifier-service/src`, `uv run pytest apps/classifier-service -q`, `python3 scripts/check-claude-md.py`. Más, por no correr en CI: `uv run pytest apps/classifier-service/tests/integration -q` con base real y **0 skipped** en los archivos del juez (registrar conteos), `uv run python scripts/check-rls.py` con salida, y `make test-rls` si hay `CTR_STORE_URL_FOR_RLS_TESTS` (no cubre `classifier_db`; no se presenta como evidencia del juez). Registrar comando, timestamp y resultado; los no disponibles, declarados.
- [ ] 8.4 Smoke E2E: no se agrega. Justificación: con `LLM_PROVIDER=mock` el juez rechaza por diseño (`modelo_no_pinneado`), así que un smoke con mock no ejercita el camino real; lo cubre el recorrido humano (8.5). Se registra como DEUDA nombrada.
- [ ] 8.5 **Recorrido humano real con Clerk** antes de archivar (requisito CRITICAL; ambiente según decisión 6): un investigador real crea una corrida, ejecuta los pasos y lee el resumen; un usuario sin membresía de investigador recibe 403. Lo hace Juani o quien él designe; no lo reemplaza ningún agente. Precede 8.0 (verificación humana de `contenido_md`). Envía contenido real de las 5 anclas al proveedor (depende de la decisión 2). Lo que el recorrido real no debe ser es la primera vez que se detecta que el modelo no ve el contrato de salida: eso lo prueban 3.4 y 3.5. SUPOSICIÓN: el Bearer sale de la sesión del web-teacher y es de vida corta (no verificado). Caminos no recorridos (congelado, firewall en base real) son DEUDA con nombre.

## Workflow follow-up

- Plan-reviewer revisa SOLO las correcciones del intento 4 (hallazgos B1, I1 a I10 y menores de `informes/propose-3-plan-reviewer.md`) y regresiones directas. Si no pasa, el contrato obliga a frenar de nuevo y ofrecer a Juani las tres opciones; no hay un quinto intento automático.
- Aprobación humana fechada en `proposal.md` `## Aprobación` (la firma solo Juani), con respuesta a las diez decisiones.
- Construcción solo sobre tareas aprobadas; breaker y auditor antes de archivar.
- T-002 (correr el juez congelado sobre los 150) es un change nuevo, posterior al archivo de este (design D13).
- Archivar solo con informes completos, checks vigentes, deuda explícita y APROBADO del auditor.
- DEUDA nombrada candidata: CI no corre integración de classifier (dueño Juani; garantías sin red listadas en 8.1); sin smoke E2E del juez; recorrido humano de caminos no cubiertos.

## Historial de orquestación

- 06/11/2026 propose intento 1: planner -> `informes/propose-1-planner.md`; plan-reviewer -> `informes/propose-1-plan-reviewer.md` (VUELVE AL PLANNER: B1-B4, I1-I8, M1-M6).
- 06/11/2026: Juani pidió seguir sin elegir B3; se planificó la opción recomendada (acceso por el estudio, membresía de investigador) como SUPOSICIÓN.
- 06/11/2026 propose intento 2: planner -> `informes/propose-2-planner.md`; plan-reviewer -> `informes/propose-2-plan-reviewer.md` (VUELVE AL PLANNER: 3 bloqueantes B-N1 a B-N3, 10 importantes, 11 menores).
- 06/11/2026 decisión humana (Juani, en el chat): opción B. Prompt fijado de antemano desde el codebook v1, sin calibración; las 5 anclas solo como prueba técnica.
- 06/11/2026 propose intento 3: planner (role-planner, Claude Sonnet 5.5, subagente nativo) -> `informes/propose-3-planner.md`. Reescritura del plan alrededor de la opción B: se eliminó la calibración (tabla de ítems de calibración, particiones, sorteo, umbrales de acuerdo, variantes, `MAX_VARIANTES`, `MIN_ITEMS_PRUEBA`), el proceso de fondo, `corrida_ajuste_id`, la sección 5.6 y el registro de calibración; se redujo la extracción y `verificar_esquema_juez`. Pendiente: plan-reviewer intento 3.

### Compuerta 06/11/2026: propose intento 3 sin aprobar

- planner intento 3 -> `informes/propose-3-planner.md`; plan-reviewer intento 3 -> `informes/propose-3-plan-reviewer.md`. Veredicto: VUELVE AL PLANNER (1 bloqueante B1, 10 importantes, 12 menores).
- Tres intentos agotados: no se lanza un cuarto automático. Se ofrecen a Juani tres opciones: nuevo alcance aprobado, deuda justificada aceptada, o parar el change. Nada avanza sin su respuesta escrita acá.

### Decisión humana 06/11/2026 (Juani, en el chat)

- Eligió la opción 1 de la compuerta: nuevo alcance aprobado, una vuelta extra ACOTADA. El planner corrige sólo los hallazgos de `informes/propose-3-plan-reviewer.md`, sin rediseñar; el revisor controla sólo esas correcciones y regresiones directas.
- Activo: planner intento 4 (autorizado por humano).

### Planner intento 4 acotado (06/11/2026)

- role-planner (Claude Sonnet 5.5, subagente nativo) -> `informes/propose-4-planner.md`, con la tabla hallazgo por hallazgo. Corrigió B1 (contrato de salida en el prompt y en el hash), I1 a I10 y los menores de texto, sin rediseñar ni abrir decisiones tomadas (opción B, acceso por el estudio, paso a paso, 3 tablas, firewall mínimo).
- Decisiones nuevas para Juani (proposal.md, ahora diez): estabilidad (1.0 propuesta, 0.8 recomendada) y regla ante ancla de frontera inestable (decisión 3), `regimen_propuesto` (9), y una sola configuración por versión (10). `## Aprobación` sigue vacía.
- Pendiente: plan-reviewer, control acotado.

### Estado 06/11/2026: propose apto, esperando a Juani

- planner intento 4 -> `informes/propose-4-planner.md`; plan-reviewer intento 4 -> `informes/propose-4-plan-reviewer.md`. Veredicto: APTO PARA APROBACIÓN HUMANA, 0 bloqueantes, 12 menores (N1 a N12).
- La revisión no es independiente: mismo rol y modelo que escribió los hallazgos que cierra.
- Bloqueo: `## Aprobación` vacía y 10 decisiones sin responder. No se construye hasta la firma de Juani.
- Obligatorio en el brief del constructor: N3 (cierre de corrida y condición 1: `cumple_tecnico` no puede dar siempre falso; afecta la regla del paper) y N1 (pasiva con cita vacía debe dar `incompleto`). El resto de los menores viaja como notas.

### Estado 06/11/2026: aprobado por Juani

- `## Aprobación` firmada por Juani el 06/11/2026. Construcción habilitada dentro de ese alcance. La corrida sobre los 150 NO está aprobada (T-002).
- Constructor previsto: Neyen, con el flujo de cinco roles. Siguiente: apply.
